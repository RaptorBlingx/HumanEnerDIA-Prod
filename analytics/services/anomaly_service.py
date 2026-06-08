"""
EnMS Analytics Service - Anomaly Service
=========================================
Business logic for anomaly detection and management.

Author: EnMS Team
Phase: 3 - Analytics & ML
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from uuid import UUID
import logging

from models.anomaly_detector import AnomalyDetector
from models.baseline import BaselineModel
from database import (
    db,
    get_machine_by_id,
    get_machine_data_combined,
    get_active_baseline_model,
    save_anomaly
)
from config import settings
from services.event_publisher import event_publisher  # Phase 4 Session 5

logger = logging.getLogger(__name__)


class AnomalyService:
    """Service for anomaly detection and management."""
    
    @staticmethod
    async def detect_anomalies(
        machine_id: UUID,
        start_time: datetime,
        end_time: datetime,
        contamination: Optional[float] = None,
        use_baseline: bool = True
    ) -> Dict[str, Any]:
        """
        Detect anomalies for a machine over a time period.
        
        Args:
            machine_id: Machine UUID
            start_time: Start of detection period
            end_time: End of detection period
            contamination: Expected proportion of anomalies (0.0-0.5)
            use_baseline: Whether to use baseline deviation as a feature
            
        Returns:
            Detection results with list of anomalies
        """
        logger.info(
            f"Detecting anomalies for machine {machine_id}: "
            f"{start_time} to {end_time}"
        )
        
        # Validate machine
        machine = await get_machine_by_id(machine_id)
        if not machine:
            raise ValueError(f"Machine not found: {machine_id}")
        
        # Fetch data
        data = await get_machine_data_combined(
            machine_id=machine_id,
            start_time=start_time,
            end_time=end_time,
            include_machine_status=True,
            aggregate_interval='15min'  # Use finer granularity for recent detection
        )
        
        if not data:
            raise ValueError("No data available for anomaly detection")

        # Fit the detector on a broader recent history so the current window
        # is compared against a meaningful baseline instead of fitting on itself.
        reference_data = await get_machine_data_combined(
            machine_id=machine_id,
            start_time=start_time - timedelta(hours=24),
            end_time=start_time,
            include_machine_status=True,
            aggregate_interval='15min'
        )
        
        # Get baseline predictions if requested
        baseline_predictions = None
        reference_baseline_predictions = None
        baseline_model_version = None
        
        if use_baseline:
            try:
                model_record = await get_active_baseline_model(machine_id)
                if model_record:
                    # Load baseline model
                    model_path = settings.MODEL_STORAGE_PATH + \
                                 f"/baseline_{machine_id}_v{model_record['model_version']}.joblib"
                    baseline_model = BaselineModel.load(model_path)
                    
                    # Generate predictions
                    baseline_predictions = baseline_model.predict_batch(data)
                    if reference_data:
                        reference_baseline_predictions = baseline_model.predict_batch(reference_data)
                    baseline_model_version = model_record['model_version']
                    
                    logger.info(f"Using baseline model v{baseline_model_version}")
            except Exception as e:
                logger.warning(f"Could not load baseline model: {e}")
        
        # Create and run detector
        detector = AnomalyDetector(contamination=contamination)
        if len(reference_data) >= 8:
            detector.fit(
                data=reference_data,
                baseline_predictions=reference_baseline_predictions
            )
        else:
            logger.warning(
                "Not enough reference data to fit anomaly detector for %s. "
                "Falling back to unsupervised mode with %d samples.",
                machine['name'],
                len(reference_data)
            )

        detected_anomalies = detector.detect(
            data=data,
            baseline_predictions=baseline_predictions
        )
        
        # Save anomalies to database
        saved_anomalies = []
        for anomaly in detected_anomalies:
            # Check machine status before saving
            # Don't save anomalies during maintenance/fault modes
            machine_status = await _get_machine_status(machine_id)
            if machine_status and machine_status.get('current_mode') in ['maintenance', 'fault']:
                logger.debug(
                    f"Skipping anomaly during {machine_status['current_mode']} mode"
                )
                continue
            
            # Prepare anomaly data
            anomaly_data = {
                'machine_id': machine_id,
                'detected_at': anomaly['detected_at'],
                'anomaly_type': anomaly['anomaly_type'],
                'severity': anomaly['severity'],
                'metric_name': anomaly.get('metric_name'),
                'metric_value': anomaly.get('metric_value'),
                'expected_value': anomaly.get('expected_value'),
                'deviation_percent': anomaly.get('deviation_percent'),
                'deviation_std_dev': anomaly.get('deviation_std_dev'),
                'detection_method': anomaly.get('detection_method'),
                'confidence_score': anomaly.get('confidence_score')
            }
            
            # Save to database
            anomaly_id = await save_anomaly(anomaly_data)
            anomaly_data['id'] = anomaly_id
            saved_anomalies.append(anomaly_data)
            
            # Phase 4 Session 5: Publish real-time anomaly event
            try:
                await event_publisher.publish_anomaly_detected(
                    machine_id=str(machine_id),
                    metric=anomaly_data.get('metric_name', anomaly_data['anomaly_type']),
                    value=anomaly_data.get('metric_value', 0.0),
                    anomaly_score=anomaly_data.get('deviation_std_dev', 1.0),
                    severity=anomaly_data['severity'],
                    timestamp=anomaly_data['detected_at']
                )
                logger.debug(f"Published anomaly event for anomaly {anomaly_id}")
            except Exception as e:
                logger.error(f"Failed to publish anomaly event: {e}")
        
        logger.info(f"✓ Saved {len(saved_anomalies)} anomalies to database")
        
        return {
            'machine_id': str(machine_id),
            'machine_name': machine['name'],
            'detection_period': {
                'start': start_time.isoformat(),
                'end': end_time.isoformat()
            },
            'baseline_model_version': baseline_model_version,
            'total_data_points': len(data),
            'anomalies_detected': len(detected_anomalies),
            'anomalies_saved': len(saved_anomalies),
            'contamination': contamination or settings.ANOMALY_CONTAMINATION,
            'anomalies': [
                {
                    'id': str(a['id']),
                    'detected_at': a['detected_at'].isoformat(),
                    'anomaly_type': a['anomaly_type'],
                    'severity': a['severity'],
                    'metric_name': a['metric_name'],
                    'metric_value': a['metric_value'],
                    'expected_value': a['expected_value'],
                    'deviation_percent': a['deviation_percent'],
                    'confidence_score': a['confidence_score']
                }
                for a in saved_anomalies
            ]
        }
    
    @staticmethod
    async def create_anomaly_manual(
        machine_id: UUID,
        detected_at: datetime,
        anomaly_type: str,
        severity: str,
        metric_name: Optional[str] = None,
        metric_value: Optional[float] = None,
        expected_value: Optional[float] = None,
        deviation_percent: Optional[float] = None,
        confidence_score: float = 0.85,
        is_resolved: bool = False
    ) -> Dict[str, Any]:
        """
        Manually create an anomaly record (for development/testing).
        
        Args:
            machine_id: Machine UUID
            detected_at: Detection timestamp
            anomaly_type: Type (spike, drop, drift, unknown)
            severity: Severity (critical, high, medium, low, normal)
            metric_name: Optional metric name
            metric_value: Optional actual value
            expected_value: Optional expected value
            deviation_percent: Optional deviation percentage
            confidence_score: Confidence score (0-1)
            is_resolved: Whether already resolved
            
        Returns:
            Created anomaly record
        """
        logger.info(f"Manually creating anomaly for machine {machine_id}")
        
        # Validate machine exists
        machine = await get_machine_by_id(machine_id)
        if not machine:
            raise ValueError(f"Machine not found: {machine_id}")
        
        # Validate severity (alert_level enum in database)
        valid_severities = ['critical', 'warning', 'normal']
        if severity not in valid_severities:
            raise ValueError(f"Invalid severity: {severity}. Must be one of {valid_severities}")
        
        # Validate anomaly type
        valid_types = ['spike', 'drop', 'drift', 'unknown']
        if anomaly_type not in valid_types:
            raise ValueError(f"Invalid anomaly type: {anomaly_type}. Must be one of {valid_types}")
        
        # Build anomaly record
        anomaly_data = {
            'machine_id': machine_id,
            'detected_at': detected_at,
            'anomaly_type': anomaly_type,
            'severity': severity,
            'metric_name': metric_name,
            'metric_value': metric_value,
            'expected_value': expected_value,
            'deviation_percent': deviation_percent,
            'confidence_score': confidence_score,
            'is_resolved': is_resolved
        }
        
        # Save to database
        anomaly_id = await save_anomaly(anomaly_data)
        
        # Publish WebSocket event (if not resolved)
        if not is_resolved:
            try:
                await event_publisher.publish_anomaly({
                    'id': str(anomaly_id),
                    'machine_id': str(machine_id),
                    'machine_name': machine['name'],
                    'machine_type': machine['type'],
                    'detected_at': detected_at.isoformat(),
                    'anomaly_type': anomaly_type,
                    'severity': severity,
                    'metric_name': metric_name,
                    'metric_value': metric_value,
                    'expected_value': expected_value,
                    'confidence_score': confidence_score
                })
                logger.info(f"Published WebSocket event for manually created anomaly {anomaly_id}")
            except Exception as e:
                logger.warning(f"Failed to publish WebSocket event: {e}")
        
        logger.info(f"Successfully created anomaly {anomaly_id} for machine {machine['name']}")
        
        return {
            'success': True,
            'anomaly_id': str(anomaly_id),
            'machine_name': machine['name'],
            'machine_type': machine['type'],
            'detected_at': detected_at.isoformat(),
            'severity': severity,
            'anomaly_type': anomaly_type,
            'websocket_published': not is_resolved
        }
    
    @staticmethod
    @staticmethod
    async def search_anomalies(
        machine_id: Optional[UUID] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        severity: Optional[str] = None,
        is_resolved: Optional[bool] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search anomalies with flexible filtering.
        
        Args:
            machine_id: Optional machine filter
            start_date: Start of search period
            end_date: End of search period
            severity: Optional severity filter
            is_resolved: Optional resolution status filter
            limit: Maximum number of results
            
        Returns:
            List of anomaly records
        """
        from datetime import timedelta
        
        # Default date range: last 30 days
        if not start_date and not end_date:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
        elif not start_date:
            start_date = end_date - timedelta(days=30)
        elif not end_date:
            end_date = datetime.now()
        
        query = """
            SELECT 
                a.id, a.machine_id, a.detected_at, a.anomaly_type,
                a.severity, a.metric_name, a.metric_value, a.expected_value,
                a.deviation_percent, a.confidence_score, a.is_resolved,
                a.resolved_at, a.resolution_notes,
                m.name as machine_name, m.type as machine_type
            FROM anomalies a
            JOIN machines m ON a.machine_id = m.id
            WHERE a.detected_at >= $1 AND a.detected_at <= $2
        """
        
        params = [start_date, end_date]
        param_count = 3
        
        if machine_id:
            query += f" AND a.machine_id = ${param_count}"
            params.append(machine_id)
            param_count += 1
        
        if severity:
            query += f" AND a.severity = ${param_count}"
            params.append(severity)
            param_count += 1
        
        if is_resolved is not None:
            query += f" AND a.is_resolved = ${param_count}"
            params.append(is_resolved)
            param_count += 1
        
        query += f" ORDER BY a.detected_at DESC LIMIT ${param_count}"
        params.append(limit)
        
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]

    @staticmethod
    async def get_recent_anomalies(
        machine_id: Optional[UUID] = None,
        severity: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get recent anomalies with optional custom date range.
        
        Args:
            machine_id: Optional machine filter
            severity: Optional severity filter ('warning', 'critical')
            start_time: Optional start of date range (defaults to 7 days ago)
            end_time: Optional end of date range (defaults to now)
            limit: Maximum number of results
            
        Returns:
            List of anomaly records
        """
        # Set default date range if not provided (last 7 days)
        if start_time is None:
            start_time = datetime.now() - timedelta(days=7)
        if end_time is None:
            end_time = datetime.now()
        
        query = """
            SELECT 
                a.id, a.machine_id, a.detected_at, a.anomaly_type,
                a.severity, a.metric_name, a.metric_value, a.expected_value,
                a.deviation_percent, a.confidence_score, a.is_resolved,
                m.name as machine_name, m.type as machine_type
            FROM anomalies a
            JOIN machines m ON a.machine_id = m.id
            WHERE a.detected_at >= $1 AND a.detected_at <= $2
        """
        
        params = [start_time, end_time]
        param_count = 3
        
        if machine_id:
            query += f" AND a.machine_id = ${param_count}"
            params.append(machine_id)
            param_count += 1
        
        if severity:
            query += f" AND a.severity = ${param_count}"
            params.append(severity)
            param_count += 1
        
        query += f" ORDER BY a.detected_at DESC LIMIT ${param_count}"
        params.append(limit)
        
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]
    
    @staticmethod
    async def get_active_anomalies(
        machine_id: Optional[UUID] = None
    ) -> List[Dict[str, Any]]:
        """
        Get unresolved anomalies.
        
        Args:
            machine_id: Optional machine filter
            
        Returns:
            List of active anomaly records
        """
        query = """
            SELECT 
                a.id, a.machine_id, a.detected_at, a.anomaly_type,
                a.severity, a.metric_name, a.metric_value, a.expected_value,
                a.deviation_percent, a.confidence_score,
                m.name as machine_name, m.type as machine_type
            FROM anomalies a
            JOIN machines m ON a.machine_id = m.id
            WHERE a.is_resolved = FALSE
        """
        
        params = []
        if machine_id:
            query += " AND a.machine_id = $1"
            params.append(machine_id)
        
        query += " ORDER BY a.severity DESC, a.detected_at DESC"
        
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]
    
    @staticmethod
    async def resolve_anomaly(
        anomaly_id: UUID,
        resolution_notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Mark an anomaly as resolved.
        
        Args:
            anomaly_id: Anomaly UUID
            resolution_notes: Optional notes about resolution
            
        Returns:
            Updated anomaly record
        """
        query = """
            UPDATE anomalies
            SET is_resolved = TRUE,
                resolved_at = NOW(),
                resolution_notes = $2
            WHERE id = $1
            RETURNING id, machine_id, anomaly_type, severity, 
                      detected_at, resolved_at
        """
        
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(query, anomaly_id, resolution_notes)
            
            if not row:
                raise ValueError(f"Anomaly not found: {anomaly_id}")
            
            logger.info(f"✓ Anomaly resolved: {anomaly_id}")
            return dict(row)


# Helper function
async def _get_machine_status(machine_id: UUID) -> Optional[Dict[str, Any]]:
    """Get current machine status."""
    query = """
        SELECT machine_id, is_running, current_mode, current_power_kw, last_updated
        FROM machine_status
        WHERE machine_id = $1
    """
    
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(query, machine_id)
        return dict(row) if row else None


# Global service instance
anomaly_service = AnomalyService()