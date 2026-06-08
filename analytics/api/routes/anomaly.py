"""
EnMS Analytics Service - Anomaly API Routes
============================================
REST API endpoints for anomaly detection.

Author: EnMS Team
Phase: 3 - Analytics & ML
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from uuid import UUID
import logging

from services.anomaly_service import anomaly_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================

class CreateAnomalyRequest(BaseModel):
    """Request model for manually creating an anomaly (dev/testing)."""
    machine_id: UUID = Field(..., description="Machine UUID")
    detected_at: datetime = Field(..., description="Detection timestamp (ISO 8601)")
    anomaly_type: str = Field(..., description="Type: spike, drop, drift, unknown")
    severity: str = Field(..., description="Severity: critical, warning, normal")
    metric_name: Optional[str] = Field(None, description="Metric name (e.g., temperature)")
    metric_value: Optional[float] = Field(None, description="Actual measured value")
    expected_value: Optional[float] = Field(None, description="Expected value")
    deviation_percent: Optional[float] = Field(None, description="Deviation percentage")
    confidence_score: float = Field(0.85, description="Confidence (0-1)", ge=0.0, le=1.0)
    is_resolved: bool = Field(False, description="Whether resolved")


class DetectAnomaliesRequest(BaseModel):
    """Request model for anomaly detection."""
    machine_id: UUID = Field(..., description="Machine UUID")
    start: datetime = Field(..., description="Detection period start (ISO 8601)")
    end: datetime = Field(..., description="Detection period end (ISO 8601)")
    contamination: Optional[float] = Field(
        None,
        description="Expected proportion of anomalies (0.0-0.5, default: 0.1)",
        ge=0.0,
        le=0.5
    )
    use_baseline: bool = Field(
        True,
        description="Whether to use baseline deviation as a feature"
    )


class ResolveAnomalyRequest(BaseModel):
    """Request model for resolving an anomaly."""
    resolution_notes: Optional[str] = Field(
        None,
        description="Notes about how the anomaly was resolved"
    )


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/anomaly/create", tags=["Anomaly"])
async def create_anomaly(request: CreateAnomalyRequest):
    """
    Manually create an anomaly record (for development/testing).
    
    ⚠️ **DEVELOPMENT TOOL** - Use for testing anomaly UI and features.
    
    **Purpose:**
    - Create test anomalies
    - Populate UI for development
    - Test notification systems
    
    **Fields:**
    - All fields from anomaly detection
    - Customizable timestamps (for historical data)
    - Manual severity and confidence scores
    
    **Returns:**
    - Created anomaly record with ID
    """
    try:
        result = await anomaly_service.create_anomaly_manual(
            machine_id=request.machine_id,
            detected_at=request.detected_at,
            anomaly_type=request.anomaly_type,
            severity=request.severity,
            metric_name=request.metric_name,
            metric_value=request.metric_value,
            expected_value=request.expected_value,
            deviation_percent=request.deviation_percent,
            confidence_score=request.confidence_score,
            is_resolved=request.is_resolved
        )
        return result
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating anomaly: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/anomaly/detect", tags=["Anomaly"])
async def detect_anomalies(request: DetectAnomaliesRequest):
    """
    Detect anomalies for a machine using Isolation Forest algorithm.
    
    **Detection Method:**
    - Isolation Forest (unsupervised ML)
    - Analyzes power, temperature, pressure, production metrics
    - Optional: Uses baseline deviation as a feature
    
    **Thresholds:**
    - **Warning**: 2σ deviation from expected
    - **Critical**: 3σ deviation from expected
    
    **Anomaly Types:**
    - `power_anomaly`: Unusual power consumption
    - `temperature_anomaly`: Temperature spike/drop
    - `pressure_anomaly`: Pressure deviation
    - `baseline_deviation`: Energy deviation from baseline model
    - `production_anomaly`: Throughput issues
    
    **Returns:**
    - List of detected anomalies
    - Severity classification (info, warning, critical)
    - Confidence scores
    - Metric values and deviations
    """
    try:
        result = await anomaly_service.detect_anomalies(
            machine_id=request.machine_id,
            start_time=request.start,
            end_time=request.end,
            contamination=request.contamination,
            use_baseline=request.use_baseline
        )
        return result
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error detecting anomalies: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/anomaly/search", tags=["Anomaly"])
async def search_anomalies(
    machine_id: Optional[UUID] = Query(None, description="Filter by machine"),
    start_date: Optional[datetime] = Query(None, description="Start date (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO 8601)"),
    severity: Optional[str] = Query(None, description="Filter by severity (warning, critical)"),
    is_resolved: Optional[bool] = Query(None, description="Filter by resolution status"),
    limit: int = Query(100, description="Maximum results", ge=1, le=500)
):
    """
    Search anomalies with flexible date range filtering.
    
    **NEW FEATURE** - Extends /anomaly/recent with custom date ranges.
    
    **Use Cases:**
    - "Show me all critical alerts from last week"
    - "What anomalies occurred in October?"
    - "Find unresolved warnings for Compressor-1"
    
    **Filters:**
    - `machine_id`: Filter by specific machine (optional)
    - `start_date`: Beginning of search period (ISO 8601, optional)
    - `end_date`: End of search period (ISO 8601, optional)
    - `severity`: Filter by severity level (optional: 'info', 'warning', 'critical')
    - `is_resolved`: Show only resolved (true) or unresolved (false) anomalies (optional)
    - `limit`: Maximum results (1-500, default: 100)
    
    **Date Behavior:**
    - If no dates provided: Returns last 30 days
    - If only start_date: From start to now
    - If only end_date: From 30 days before end to end
    - If both: Exact range
    
    **Returns:**
    - List of anomalies matching criteria
    - Total count and applied filters
    - Ordered by detection time (newest first)
    """
    try:
        anomalies = await anomaly_service.search_anomalies(
            machine_id=machine_id,
            start_date=start_date,
            end_date=end_date,
            severity=severity,
            is_resolved=is_resolved,
            limit=limit
        )
        return {
            'total_count': len(anomalies),
            'filters': {
                'machine_id': str(machine_id) if machine_id else None,
                'start_date': start_date.isoformat() if start_date else None,
                'end_date': end_date.isoformat() if end_date else None,
                'severity': severity,
                'is_resolved': is_resolved,
                'limit': limit
            },
            'anomalies': anomalies
        }
    
    except Exception as e:
        logger.error(f"Error searching anomalies: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/anomaly/recent", tags=["Anomaly"])
async def get_recent_anomalies(
    machine_id: Optional[UUID] = Query(None, description="Filter by machine"),
    severity: Optional[str] = Query(None, description="Filter by severity (warning, critical)"),
    start_time: Optional[datetime] = Query(None, description="Start of date range (ISO 8601, defaults to 7 days ago)"),
    end_time: Optional[datetime] = Query(None, description="End of date range (ISO 8601, defaults to now)"),
    limit: int = Query(50, description="Maximum results", ge=1, le=200)
):
    """
    Get recent anomalies with optional custom date range.
    
    **NEW:** Now supports flexible date ranges! Defaults to last 7 days if not specified.
    
    **Use Cases:**
    - Dashboard display
    - Alert monitoring
    - Real-time fault tracking
    - Historical anomaly analysis
    
    **Filters:**
    - `machine_id`: Filter by specific machine (optional)
    - `severity`: Filter by severity - 'warning', 'critical' (optional)
    - `start_time`: Custom start date (ISO 8601, optional, defaults to 7 days ago)
    - `end_time`: Custom end date (ISO 8601, optional, defaults to now)
    - `limit`: Maximum results (1-200, default: 50)
    
    **Returns:**
    - List of anomalies with machine info
    - Ordered by detection time (newest first)
    
    **Examples:**
    ```
    # Last 7 days (default)
    GET /anomaly/recent
    
    # Custom date range
    GET /anomaly/recent?start_time=2025-10-15T00:00:00Z&end_time=2025-10-20T00:00:00Z
    
    # Last week's critical alerts for specific machine
    GET /anomaly/recent?machine_id=...&severity=critical&start_time=2025-10-13T00:00:00Z
    ```
    """
    try:
        anomalies = await anomaly_service.get_recent_anomalies(
            machine_id=machine_id,
            severity=severity,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
        
        # Calculate time window for response
        if start_time and end_time:
            time_window = f"Custom range: {start_time.isoformat()} to {end_time.isoformat()}"
        else:
            time_window = "Last 7 days (default)"
        
        return {
            'total_count': len(anomalies),
            'filters': {
                'machine_id': str(machine_id) if machine_id else None,
                'severity': severity,
                'start_time': start_time.isoformat() if start_time else None,
                'end_time': end_time.isoformat() if end_time else None,
                'time_window': time_window
            },
            'anomalies': anomalies
        }
    
    except Exception as e:
        logger.error(f"Error retrieving recent anomalies: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/anomaly/active", tags=["Anomaly"])
async def get_active_anomalies(
    machine_id: Optional[UUID] = Query(None, description="Filter by machine")
):
    """
    Get all unresolved anomalies.
    
    **Use Cases:**
    - Maintenance dashboard
    - Fault tracking
    - Priority alerts
    
    **Returns:**
    - List of unresolved anomalies
    - Ordered by severity (critical first), then time
    """
    try:
        anomalies = await anomaly_service.get_active_anomalies(
            machine_id=machine_id
        )
        
        # Group by severity
        by_severity = {
            'critical': [a for a in anomalies if a['severity'] == 'critical'],
            'warning': [a for a in anomalies if a['severity'] == 'warning'],
            'normal': [a for a in anomalies if a['severity'] == 'normal'],
            'info': [a for a in anomalies if a['severity'] in ('info', 'normal')]
        }
        
        return {
            'total_count': len(anomalies),
            'by_severity': {
                'critical': len(by_severity['critical']),
                'warning': len(by_severity['warning']),
                'info': len(by_severity['info']),
                'normal': len(by_severity['normal'])
            },
            'anomalies': anomalies
        }
    
    except Exception as e:
        logger.error(f"Error retrieving active anomalies: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/anomaly/{anomaly_id}/resolve", tags=["Anomaly"])
async def resolve_anomaly(
    anomaly_id: UUID,
    request: ResolveAnomalyRequest
):
    """
    Mark an anomaly as resolved.
    
    **Use Cases:**
    - Close maintenance ticket
    - Document fix or false positive
    - Track resolution time
    
    **Process:**
    1. Sets `is_resolved = TRUE`
    2. Records `resolved_at` timestamp
    3. Stores resolution notes (optional)
    
    **Returns:**
    - Updated anomaly record
    - Resolution timestamp
    """
    try:
        result = await anomaly_service.resolve_anomaly(
            anomaly_id=anomaly_id,
            resolution_notes=request.resolution_notes
        )
        return result
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error resolving anomaly: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")