"""
Model Performance Tracking API Routes
======================================
Track, monitor, and analyze ML model performance over time.

Features:
- Record performance metrics
- Detect model drift
- Trigger auto-retraining
- A/B testing between models
- Performance alerts

Author: EnMS Team
Date: October 14, 2025
Phase 4, Session 4
"""

from fastapi import APIRouter, Query, Body, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from uuid import UUID
import logging
import json

from database import db
from services.event_publisher import event_publisher  # Phase 4 Session 5

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/model-performance")


# ============================================================================
# DATA MODELS
# ============================================================================

class PerformanceMetric(BaseModel):
    """Single performance metric record"""
    id: str
    model_id: str
    model_type: str
    machine_id: str
    model_version: int
    evaluation_date: datetime
    
    # Metrics
    r_squared: Optional[float] = None
    rmse: Optional[float] = None
    mae: Optional[float] = None
    mape: Optional[float] = None
    
    # Drift
    drift_detected: bool
    drift_score: Optional[float] = None
    
    # Sample info
    sample_count: int
    data_completeness: float


class PerformanceTrend(BaseModel):
    """Performance trend over time"""
    model_type: str
    machine_id: str
    machine_name: str
    metrics: List[PerformanceMetric]
    trend_direction: str  # 'improving', 'stable', 'degrading'
    degradation_rate: Optional[float] = None  # % per day


class DriftDetectionResult(BaseModel):
    """Drift detection result"""
    drift_detected: bool
    drift_score: float
    drift_type: str  # 'data_drift', 'concept_drift', 'no_drift'
    recommendation: str
    threshold: float
    current_performance: Dict[str, float]
    baseline_performance: Dict[str, float]


class TrainingTrigger(BaseModel):
    """Training trigger result"""
    triggered: bool
    trigger_type: str
    reason: str
    training_job_id: Optional[str] = None
    estimated_completion: Optional[datetime] = None


class ABTestResult(BaseModel):
    """A/B test result"""
    test_id: str
    test_name: str
    model_a_version: int
    model_b_version: int
    winner: Optional[str] = None  # 'model_a', 'model_b', 'no_winner'
    confidence: float
    model_a_metrics: Dict[str, float]
    model_b_metrics: Dict[str, float]
    recommendation: str


class ModelAlert(BaseModel):
    """Model performance alert"""
    id: str
    alert_type: str
    severity: str
    model_type: str
    machine_id: str
    machine_name: str
    alert_message: str
    alert_timestamp: datetime
    is_resolved: bool
    auto_action_taken: bool


class ModelSummary(BaseModel):
    """Summary of actual trained model from energy_baselines"""
    model_id: str
    machine_id: str
    machine_name: str
    model_type: str
    model_version: int
    is_active: bool
    r_squared: Optional[float] = None
    rmse: Optional[float] = None
    mae: Optional[float] = None
    training_samples: Optional[int] = None
    feature_names: Optional[List[str]] = None
    created_at: datetime
    has_model: bool = True


# ============================================================================
# MODEL SUMMARY ENDPOINT (Queries REAL baseline data)
# ============================================================================

@router.get("/summary")
async def get_model_summary(
    machine_id: str = Query(..., description="Machine UUID"),
    model_type: str = Query("baseline", description="Model type: baseline, anomaly, forecast_arima, forecast_prophet")
):
    """
    Get summary of actual trained models from energy_baselines table.
    
    This endpoint queries REAL model data, not the model_performance_metrics table.
    Use this for displaying current model status.
    """
    try:
        pool = db.pool
        machine_uuid = UUID(machine_id)
        
        async with pool.acquire() as conn:
            # Get machine info
            machine_row = await conn.fetchrow("""
                SELECT id, name, type FROM machines WHERE id = $1
            """, machine_uuid)
            
            if not machine_row:
                raise HTTPException(status_code=404, detail="Machine not found")
            
            if model_type == "baseline":
                # Query energy_baselines table for real baseline models
                model_row = await conn.fetchrow("""
                    SELECT 
                        id, machine_id, model_version, model_name,
                        r_squared, rmse, mae, training_samples,
                        feature_names, is_active, created_at
                    FROM energy_baselines
                    WHERE machine_id = $1 AND is_active = true
                    ORDER BY created_at DESC
                    LIMIT 1
                """, machine_uuid)
                
                if not model_row:
                    # No model trained yet
                    return {
                        "has_model": False,
                        "model_id": None,
                        "machine_id": str(machine_uuid),
                        "machine_name": machine_row['name'],
                        "model_type": model_type,
                        "model_version": 0,
                        "is_active": False,
                        "r_squared": None,
                        "rmse": None,
                        "mae": None,
                        "training_samples": None,
                        "feature_names": None,
                        "created_at": None,
                        "message": "No baseline model trained for this machine. Train one in the Baseline page."
                    }
                
                # Get all versions for history
                all_versions = await conn.fetch("""
                    SELECT 
                        id, model_version, r_squared, rmse, mae, 
                        training_samples, is_active, created_at
                    FROM energy_baselines
                    WHERE machine_id = $1
                    ORDER BY model_version DESC
                    LIMIT 10
                """, machine_uuid)
                
                return {
                    "has_model": True,
                    "model_id": str(model_row['id']),
                    "machine_id": str(machine_uuid),
                    "machine_name": machine_row['name'],
                    "model_type": model_type,
                    "model_version": model_row['model_version'],
                    "is_active": model_row['is_active'],
                    "r_squared": float(model_row['r_squared']) if model_row['r_squared'] else None,
                    "rmse": float(model_row['rmse']) if model_row['rmse'] else None,
                    "mae": float(model_row['mae']) if model_row['mae'] else None,
                    "training_samples": model_row['training_samples'],
                    "feature_names": model_row['feature_names'],
                    "created_at": model_row['created_at'].isoformat() if model_row['created_at'] else None,
                    "versions": [
                        {
                            "id": str(v['id']),
                            "version": v['model_version'],
                            "r_squared": float(v['r_squared']) if v['r_squared'] else None,
                            "rmse": float(v['rmse']) if v['rmse'] else None,
                            "is_active": v['is_active'],
                            "created_at": v['created_at'].isoformat() if v['created_at'] else None
                        }
                        for v in all_versions
                    ]
                }
            
            elif model_type in ["forecast_arima", "forecast_prophet"]:
                # Check filesystem for forecast models
                import os
                model_subtype = "arima" if model_type == "forecast_arima" else "prophet"
                model_path = f"/app/models/{model_subtype}_{machine_id}.pkl"
                
                if os.path.exists(model_path):
                    import pickle
                    from datetime import datetime as dt
                    
                    stat = os.stat(model_path)
                    modified = dt.fromtimestamp(stat.st_mtime)
                    
                    return {
                        "has_model": True,
                        "model_id": f"{model_subtype}_{machine_id}",
                        "machine_id": str(machine_uuid),
                        "machine_name": machine_row['name'],
                        "model_type": model_type,
                        "model_version": 1,
                        "is_active": True,
                        "r_squared": None,  # Forecast models don't store R²
                        "rmse": None,
                        "mae": None,
                        "training_samples": None,
                        "feature_names": None,
                        "created_at": modified.isoformat(),
                        "versions": []
                    }
                else:
                    return {
                        "has_model": False,
                        "model_id": None,
                        "machine_id": str(machine_uuid),
                        "machine_name": machine_row['name'],
                        "model_type": model_type,
                        "model_version": 0,
                        "is_active": False,
                        "message": f"No {model_subtype.upper()} model trained. Train one in the Forecast page."
                    }
            
            elif model_type == "anomaly":
                # Query anomalies table to check if anomaly detection is configured
                # Count recent anomalies to verify detection is working
                anomaly_stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total_anomalies,
                        COUNT(CASE WHEN detected_at > NOW() - INTERVAL '30 days' THEN 1 END) as recent_anomalies,
                        MAX(detected_at) as last_detected,
                        COUNT(DISTINCT detection_method) as detection_methods
                    FROM anomalies
                    WHERE machine_id = $1
                """, machine_uuid)
                
                if not anomaly_stats or anomaly_stats['total_anomalies'] == 0:
                    return {
                        "has_model": False,
                        "model_id": None,
                        "machine_id": str(machine_uuid),
                        "machine_name": machine_row['name'],
                        "model_type": model_type,
                        "message": "No anomaly detection history found. Configure in the Anomaly page."
                    }
                
                return {
                    "has_model": True,
                    "model_id": str(machine_uuid),  # Use machine_id as identifier
                    "machine_id": str(machine_uuid),
                    "machine_name": machine_row['name'],
                    "model_type": model_type,
                    "model_version": 1,
                    "is_active": True,
                    "total_anomalies": int(anomaly_stats['total_anomalies']),
                    "recent_anomalies": int(anomaly_stats['recent_anomalies']),
                    "last_detected": anomaly_stats['last_detected'].isoformat() if anomaly_stats['last_detected'] else None,
                    "detection_methods": int(anomaly_stats['detection_methods']),
                    "created_at": anomaly_stats['last_detected'].isoformat() if anomaly_stats['last_detected'] else None,
                    "versions": []
                }
            
            else:
                raise HTTPException(status_code=400, detail=f"Unknown model type: {model_type}")
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting model summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/metrics/record")
async def record_performance_metric(
    model_id: str = Query(..., description="Model ID"),
    model_type: str = Query(..., description="Model type"),
    machine_id: str = Query(..., description="Machine ID"),
    evaluation_start: datetime = Query(..., description="Evaluation period start"),
    evaluation_end: datetime = Query(..., description="Evaluation period end"),
    metrics: Dict[str, float] = Body(..., description="Performance metrics")
):
    """
    Record performance metrics for a model.
    
    This endpoint is called after evaluating a model on recent data.
    It stores the metrics and checks for drift/degradation.
    """
    try:
        pool = db.pool
        
        # Convert string IDs to UUIDs
        model_uuid = UUID(model_id)
        machine_uuid = UUID(machine_id)
        
        async with pool.acquire() as conn:
            # Get model version
            model_row = await conn.fetchrow("""
                SELECT model_version FROM energy_baselines
                WHERE id = $1
            """, model_uuid)
            
            if not model_row:
                raise HTTPException(status_code=404, detail="Model not found")
            
            model_version = model_row['model_version']
            
            # Count samples in evaluation period
            sample_count = await conn.fetchval("""
                SELECT COUNT(*)
                FROM energy_readings
                WHERE machine_id = $1
                AND time >= $2 AND time <= $3
            """, machine_uuid, evaluation_start, evaluation_end)
            
            # Calculate data completeness
            expected_samples = int((evaluation_end - evaluation_start).total_seconds() / 600)  # 10-min intervals
            data_completeness = sample_count / expected_samples if expected_samples > 0 else 0
            
            # Check for drift
            drift_result = await detect_drift(
                conn, model_uuid, model_type, machine_uuid, metrics
            )
            
            # Insert performance metric
            metric_id = await conn.fetchval("""
                INSERT INTO model_performance_metrics (
                    model_id, model_type, machine_id, model_version,
                    evaluation_start, evaluation_end, sample_count,
                    metrics, r_squared, rmse, mae, mape,
                    drift_detected, drift_score, drift_threshold,
                    data_completeness
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                RETURNING id
            """,
                model_uuid, model_type, machine_uuid, model_version,
                evaluation_start, evaluation_end, sample_count,
                json.dumps(metrics),  # Convert dict to JSON string
                metrics.get('r_squared'), metrics.get('rmse'),
                metrics.get('mae'), metrics.get('mape'),
                drift_result['drift_detected'], drift_result['drift_score'],
                drift_result['threshold'], data_completeness
            )
            
            # Create alert if drift detected
            if drift_result['drift_detected']:
                await create_drift_alert(
                    conn, model_uuid, model_type, machine_uuid,
                    model_version, drift_result, metrics
                )
        
        return {
            "metric_id": str(metric_id),
            "drift_detected": drift_result['drift_detected'],
            "drift_score": drift_result['drift_score'],
            "recommendation": drift_result['recommendation']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording performance metric: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/trend", response_model=PerformanceTrend)
async def get_performance_trend(
    model_type: str = Query(..., description="Model type"),
    machine_id: str = Query(..., description="Machine ID"),
    days: int = Query(30, description="Number of days to analyze")
):
    """
    Get performance trend for a model over time.
    
    Analyzes metrics over the specified period and determines
    if performance is improving, stable, or degrading.
    """
    try:
        pool = db.pool
        machine_uuid = UUID(machine_id)
        start_date = datetime.utcnow() - timedelta(days=days)
        
        async with pool.acquire() as conn:
            # Get machine info
            machine_row = await conn.fetchrow("""
                SELECT name FROM machines WHERE id = $1
            """, machine_uuid)
            
            if not machine_row:
                raise HTTPException(status_code=404, detail="Machine not found")
            
            # Get metrics
            rows = await conn.fetch("""
                SELECT 
                    id, model_id, model_type, machine_id, model_version,
                    evaluation_date, r_squared, rmse, mae, mape,
                    drift_detected, drift_score, sample_count, data_completeness
                FROM model_performance_metrics
                WHERE model_type = $1 AND machine_id = $2
                AND evaluation_date >= $3
                ORDER BY evaluation_date ASC
            """, model_type, machine_uuid, start_date)
            
            if not rows:
                raise HTTPException(status_code=404, detail="No metrics found for this period")
            
            # Convert to PerformanceMetric objects
            metrics = [
                PerformanceMetric(
                    id=str(row['id']),
                    model_id=str(row['model_id']),
                    model_type=row['model_type'],
                    machine_id=str(row['machine_id']),
                    model_version=row['model_version'],
                    evaluation_date=row['evaluation_date'],
                    r_squared=float(row['r_squared']) if row['r_squared'] else None,
                    rmse=float(row['rmse']) if row['rmse'] else None,
                    mae=float(row['mae']) if row['mae'] else None,
                    mape=float(row['mape']) if row['mape'] else None,
                    drift_detected=row['drift_detected'],
                    drift_score=float(row['drift_score']) if row['drift_score'] else None,
                    sample_count=row['sample_count'],
                    data_completeness=float(row['data_completeness'])
                )
                for row in rows
            ]
            
            # Analyze trend
            trend_analysis = analyze_trend(metrics)
        
        return PerformanceTrend(
            model_type=model_type,
            machine_id=machine_id,
            machine_name=machine_row['name'],
            metrics=metrics,
            **trend_analysis
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting performance trend: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# DRIFT DETECTION ENDPOINTS
# ============================================================================

@router.post("/drift/check", response_model=DriftDetectionResult)
async def check_drift(
    model_id: str = Query(..., description="Model ID"),
    model_type: str = Query(..., description="Model type"),
    machine_id: str = Query(..., description="Machine ID")
):
    """
    Check for model drift.
    
    Compares current performance against baseline performance
    to detect data drift or concept drift.
    """
    try:
        pool = db.pool
        model_uuid = UUID(model_id)
        machine_uuid = UUID(machine_id)
        
        async with pool.acquire() as conn:
            # Get current performance
            current = await conn.fetchrow("""
                SELECT r_squared, rmse, mae, mape, evaluation_date
                FROM model_performance_metrics
                WHERE model_id = $1
                ORDER BY evaluation_date DESC
                LIMIT 1
            """, model_uuid)
            
            if not current:
                raise HTTPException(status_code=404, detail="No recent performance metrics found")
            
            # Get baseline performance (first 30 days after training)
            baseline = await conn.fetchrow("""
                SELECT 
                    AVG(r_squared) as avg_r_squared,
                    AVG(rmse) as avg_rmse,
                    AVG(mae) as avg_mae,
                    AVG(mape) as avg_mape
                FROM model_performance_metrics
                WHERE model_id = $1
                AND evaluation_date <= (
                    SELECT MIN(evaluation_date) + INTERVAL '30 days'
                    FROM model_performance_metrics
                    WHERE model_id = $1
                )
            """, model_uuid)
            
            # Calculate drift
            drift_result = calculate_drift_score(
                current_metrics={
                    'r_squared': float(current['r_squared']) if current['r_squared'] else 0,
                    'rmse': float(current['rmse']) if current['rmse'] else 0,
                    'mae': float(current['mae']) if current['mae'] else 0,
                    'mape': float(current['mape']) if current['mape'] else 0
                },
                baseline_metrics={
                    'r_squared': float(baseline['avg_r_squared']) if baseline['avg_r_squared'] else 0,
                    'rmse': float(baseline['avg_rmse']) if baseline['avg_rmse'] else 0,
                    'mae': float(baseline['avg_mae']) if baseline['avg_mae'] else 0,
                    'mape': float(baseline['avg_mape']) if baseline['avg_mape'] else 0
                }
            )
        
        return drift_result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking drift: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# AUTO-RETRAIN ENDPOINTS
# ============================================================================

@router.post("/retrain/trigger", response_model=TrainingTrigger)
async def trigger_retrain(
    background_tasks: BackgroundTasks,
    model_type: str = Query(..., description="Model type"),
    machine_id: str = Query(..., description="Machine ID"),
    trigger_type: str = Query("manual", description="Trigger type"),
    reason: str = Query(..., description="Reason for retraining")
):
    """
    Trigger model retraining.
    
    Can be triggered manually or automatically based on drift/degradation.
    Training happens in the background.
    """
    try:
        pool = db.pool
        machine_uuid = UUID(machine_id)
        
        async with pool.acquire() as conn:
            # Check if training already in progress
            in_progress = await conn.fetchval("""
                SELECT COUNT(*)
                FROM model_training_history
                WHERE model_type = $1 AND machine_id = $2
                AND training_status IN ('pending', 'running')
            """, model_type, machine_uuid)
            
            if in_progress > 0:
                return TrainingTrigger(
                    triggered=False,
                    trigger_type=trigger_type,
                    reason="Training already in progress"
                )
            
            # Create training job
            job_id = await conn.fetchval("""
                INSERT INTO model_training_history (
                    model_type, machine_id, training_start,
                    training_status, training_data_start, training_data_end,
                    trigger_type, triggered_by
                )
                VALUES ($1, $2, NOW(), 'pending', NOW() - INTERVAL '90 days', NOW(), $3, 'api')
                RETURNING id
            """, model_type, machine_uuid, trigger_type)
            
            # Schedule background training
            background_tasks.add_task(
                execute_training,
                str(job_id), model_type, str(machine_uuid)
            )
            
            # Publish training started event (Phase 4 Session 5)
            background_tasks.add_task(
                event_publisher.publish_training_started,
                job_id=job_id,
                machine_id=str(machine_uuid),
                model_type=model_type
            )
        
        estimated_completion = datetime.utcnow() + timedelta(minutes=5)
        
        return TrainingTrigger(
            triggered=True,
            trigger_type=trigger_type,
            reason=reason,
            training_job_id=str(job_id),
            estimated_completion=estimated_completion
        )
        
    except Exception as e:
        logger.error(f"Error triggering retrain: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# A/B TESTING ENDPOINTS
# ============================================================================

@router.post("/ab-test/start")
async def start_ab_test(
    test_name: str = Query(..., description="Test name"),
    model_type: str = Query(..., description="Model type"),
    machine_id: str = Query(..., description="Machine ID"),
    model_a_id: str = Query(..., description="Model A ID"),
    model_b_id: str = Query(..., description="Model B ID"),
    duration_hours: int = Query(24, description="Test duration in hours")
):
    """
    Start an A/B test between two model versions.
    
    Traffic will be split 50/50 between the two models.
    """
    try:
        pool = db.pool
        machine_uuid = UUID(machine_id)
        model_a_uuid = UUID(model_a_id)
        model_b_uuid = UUID(model_b_id)
        test_end = datetime.utcnow() + timedelta(hours=duration_hours)
        
        async with pool.acquire() as conn:
            # Get model versions
            model_a = await conn.fetchrow("""
                SELECT model_version FROM energy_baselines WHERE id = $1
            """, model_a_uuid)
            
            model_b = await conn.fetchrow("""
                SELECT model_version FROM energy_baselines WHERE id = $1
            """, model_b_uuid)
            
            if not model_a or not model_b:
                raise HTTPException(status_code=404, detail="One or both models not found")
            
            # Create AB test
            test_id = await conn.fetchval("""
                INSERT INTO model_ab_tests (
                    test_name, model_type, machine_id,
                    model_a_id, model_a_version,
                    model_b_id, model_b_version,
                    test_start, test_end, test_status,
                    created_by
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), $8, 'running', 'api')
                RETURNING id
            """,
                test_name, model_type, machine_uuid,
                model_a_uuid, model_a['model_version'],
                model_b_uuid, model_b['model_version'],
                test_end
            )
        
        return {
            "test_id": str(test_id),
            "status": "running",
            "test_end": test_end,
            "message": f"A/B test started. Will run for {duration_hours} hours."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting A/B test: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ab-test/{test_id}/results", response_model=ABTestResult)
async def get_ab_test_results(
    test_id: UUID
):
    """
    Get A/B test results.
    
    Compares performance metrics of both models and determines winner.
    """
    try:
        pool = db.pool
        
        async with pool.acquire() as conn:
            # Get test info
            test = await conn.fetchrow("""
                SELECT * FROM model_ab_tests WHERE id = $1
            """, test_id)
            
            if not test:
                raise HTTPException(status_code=404, detail="A/B test not found")
            
            # Get performance metrics for both models
            model_a_metrics = await get_model_metrics_during_test(
                conn, test['model_a_id'], test['test_start'], test['test_end']
            )
            
            model_b_metrics = await get_model_metrics_during_test(
                conn, test['model_b_id'], test['test_start'], test['test_end']
            )
            
            # Determine winner
            winner_analysis = determine_winner(model_a_metrics, model_b_metrics)
        
        return ABTestResult(
            test_id=str(test['id']),
            test_name=test['test_name'],
            model_a_version=test['model_a_version'],
            model_b_version=test['model_b_version'],
            winner=winner_analysis['winner'],
            confidence=winner_analysis['confidence'],
            model_a_metrics=model_a_metrics,
            model_b_metrics=model_b_metrics,
            recommendation=winner_analysis['recommendation']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting A/B test results: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ALERTS ENDPOINTS
# ============================================================================

@router.get("/alerts/active", response_model=List[ModelAlert])
async def get_active_alerts(
    machine_id: Optional[str] = Query(None, description="Filter by machine"),
    model_type: Optional[str] = Query(None, description="Filter by model type"),
    severity: Optional[str] = Query(None, description="Filter by severity")
):
    """
    Get active (unresolved) model performance alerts.
    """
    try:
        pool = db.pool
        
        async with pool.acquire() as conn:
            query = """
                SELECT 
                    ma.id, ma.alert_type, ma.severity, ma.model_type,
                    ma.machine_id, m.name as machine_name,
                    ma.alert_message, ma.alert_timestamp,
                    ma.is_resolved, ma.auto_action_taken
                FROM model_alerts ma
                JOIN machines m ON m.id = ma.machine_id
                WHERE ma.is_resolved = FALSE
            """
            
            params = []
            if machine_id:
                machine_uuid = UUID(machine_id)
                params.append(machine_uuid)
                query += f" AND ma.machine_id = ${len(params)}"
            if model_type:
                params.append(model_type)
                query += f" AND ma.model_type = ${len(params)}"
            if severity:
                params.append(severity)
                query += f" AND ma.severity = ${len(params)}"
            
            query += " ORDER BY ma.severity DESC, ma.alert_timestamp DESC"
            
            rows = await conn.fetch(query, *params)
        
        return [
            ModelAlert(
                id=str(row['id']),
                alert_type=row['alert_type'],
                severity=row['severity'],
                model_type=row['model_type'],
                machine_id=str(row['machine_id']),
                machine_name=row['machine_name'],
                alert_message=row['alert_message'],
                alert_timestamp=row['alert_timestamp'],
                is_resolved=row['is_resolved'],
                auto_action_taken=row['auto_action_taken']
            )
            for row in rows
        ]
        
    except Exception as e:
        logger.error(f"Error getting active alerts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def detect_drift(conn, model_id, model_type, machine_id, current_metrics):
    """Detect if model has drifted."""
    # Get baseline metrics
    baseline = await conn.fetchrow("""
        SELECT AVG(r_squared) as r2, AVG(rmse) as rmse
        FROM model_performance_metrics
        WHERE model_id = $1
        AND evaluation_date <= (
            SELECT MIN(evaluation_date) + INTERVAL '30 days'
            FROM model_performance_metrics
            WHERE model_id = $1
        )
    """, model_id)
    
    if not baseline or not baseline['r2']:
        return {
            'drift_detected': False,
            'drift_score': 0.0,
            'threshold': 0.1,
            'recommendation': 'Insufficient baseline data'
        }
    
    # Calculate drift score (normalized difference)
    r2_current = current_metrics.get('r_squared', 0)
    r2_baseline = float(baseline['r2'])
    
    drift_score = abs(r2_current - r2_baseline) / r2_baseline if r2_baseline > 0 else 0
    threshold = 0.1  # 10% degradation
    
    return {
        'drift_detected': drift_score > threshold,
        'drift_score': drift_score,
        'threshold': threshold,
        'recommendation': 'Retrain model' if drift_score > threshold else 'Model performing well'
    }


async def create_drift_alert(conn, model_id, model_type, machine_id, model_version, drift_result, metrics):
    """Create alert for detected drift."""
    await conn.execute("""
        INSERT INTO model_alerts (
            alert_type, severity, model_id, model_type,
            machine_id, model_version, alert_message,
            alert_details, current_metric_value, threshold_value
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
    """,
        'drift_detected',
        'warning',
        model_id,
        model_type,
        machine_id,
        model_version,
        f"Model drift detected (score: {drift_result['drift_score']:.4f})",
        metrics,
        drift_result['drift_score'],
        drift_result['threshold']
    )


def analyze_trend(metrics: List[PerformanceMetric]) -> Dict:
    """Analyze performance trend."""
    if len(metrics) < 2:
        return {
            'trend_direction': 'stable',
            'degradation_rate': 0.0
        }
    
    # Simple linear regression on R² values
    r2_values = [m.r_squared for m in metrics if m.r_squared is not None]
    
    if not r2_values:
        return {
            'trend_direction': 'stable',
            'degradation_rate': 0.0
        }
    
    # Calculate slope
    n = len(r2_values)
    x = list(range(n))
    x_mean = sum(x) / n
    y_mean = sum(r2_values) / n
    
    numerator = sum((x[i] - x_mean) * (r2_values[i] - y_mean) for i in range(n))
    denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
    
    slope = numerator / denominator if denominator != 0 else 0
    
    if slope < -0.001:
        direction = 'degrading'
    elif slope > 0.001:
        direction = 'improving'
    else:
        direction = 'stable'
    
    days = (metrics[-1].evaluation_date - metrics[0].evaluation_date).days
    degradation_rate = (slope * 100) / days if days > 0 else 0
    
    return {
        'trend_direction': direction,
        'degradation_rate': round(degradation_rate, 4)
    }


def calculate_drift_score(current_metrics: Dict, baseline_metrics: Dict) -> DriftDetectionResult:
    """Calculate comprehensive drift score."""
    # Weighted combination of metric differences
    r2_diff = abs(current_metrics['r_squared'] - baseline_metrics['r_squared'])
    rmse_diff = abs(current_metrics['rmse'] - baseline_metrics['rmse']) / baseline_metrics['rmse'] if baseline_metrics['rmse'] > 0 else 0
    
    drift_score = (r2_diff * 0.6) + (rmse_diff * 0.4)
    threshold = 0.1
    
    drift_detected = drift_score > threshold
    
    if drift_detected:
        drift_type = 'concept_drift' if r2_diff > 0.15 else 'data_drift'
        recommendation = 'Immediate retraining recommended'
    else:
        drift_type = 'no_drift'
        recommendation = 'Model performing within acceptable range'
    
    return DriftDetectionResult(
        drift_detected=drift_detected,
        drift_score=round(drift_score, 4),
        drift_type=drift_type,
        recommendation=recommendation,
        threshold=threshold,
        current_performance=current_metrics,
        baseline_performance=baseline_metrics
    )


async def get_model_metrics_during_test(conn, model_id, start, end) -> Dict[str, float]:
    """Get aggregated metrics for a model during test period."""
    result = await conn.fetchrow("""
        SELECT 
            AVG(r_squared) as r2,
            AVG(rmse) as rmse,
            AVG(mae) as mae,
            COUNT(*) as sample_count
        FROM model_performance_metrics
        WHERE model_id = $1
        AND evaluation_date >= $2
        AND evaluation_date <= $3
    """, model_id, start, end)
    
    return {
        'r_squared': float(result['r2']) if result['r2'] else 0,
        'rmse': float(result['rmse']) if result['rmse'] else 0,
        'mae': float(result['mae']) if result['mae'] else 0,
        'sample_count': result['sample_count']
    }


def determine_winner(model_a_metrics: Dict, model_b_metrics: Dict) -> Dict:
    """Determine A/B test winner."""
    # Compare R²
    r2_diff = model_b_metrics['r_squared'] - model_a_metrics['r_squared']
    
    # Simple winner determination (could use statistical tests)
    if abs(r2_diff) < 0.02:
        winner = 'no_winner'
        confidence = 0.5
        recommendation = 'Performance is similar. Consider other factors.'
    elif r2_diff > 0:
        winner = 'model_b'
        confidence = min(0.95, 0.5 + abs(r2_diff) * 5)
        recommendation = 'Model B shows better performance. Recommend promotion.'
    else:
        winner = 'model_a'
        confidence = min(0.95, 0.5 + abs(r2_diff) * 5)
        recommendation = 'Model A shows better performance. Recommend keeping current model.'
    
    return {
        'winner': winner,
        'confidence': round(confidence, 4),
        'recommendation': recommendation
    }


async def execute_training(job_id: str, model_type: str, machine_id: str):
    """
    Execute training in background.
    
    This is a mock implementation that simulates training completion.
    In production, this would call actual model training logic.
    """
    import asyncio
    
    logger.info(f"Background training started for job {job_id}")
    
    try:
        pool = db.pool
        job_uuid = UUID(job_id)
        machine_uuid = UUID(machine_id)
        
        # Update status to running
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE model_training_history
                SET training_status = 'running'
                WHERE id = $1
            """, job_uuid)
        
        logger.info(f"Training job {job_id} marked as running")
        
        # Publish progress updates (Phase 4 Session 5)
        await event_publisher.publish_training_progress(
            job_id=int(str(job_uuid).replace('-', '')[:8], 16),  # Convert UUID to int
            progress_pct=20,
            status='running',
            message='Training data prepared'
        )
        
        # Simulate training time (5-10 seconds)
        await asyncio.sleep(4)
        
        # Publish mid-training progress (Phase 4 Session 5)
        await event_publisher.publish_training_progress(
            job_id=int(str(job_uuid).replace('-', '')[:8], 16),
            progress_pct=60,
            status='running',
            message='Model training in progress'
        )
        
        await asyncio.sleep(4)
        
        # Mock training completion with simulated metrics
        async with pool.acquire() as conn:
            # Get the latest model version
            latest_version = await conn.fetchval("""
                SELECT COALESCE(MAX(model_version), 0)
                FROM model_training_history
                WHERE model_type = $1 AND machine_id = $2
                AND training_status = 'completed'
            """, model_type, machine_uuid)
            
            new_version = (latest_version or 0) + 1
            
            # Update job as completed
            await conn.execute("""
                UPDATE model_training_history
                SET training_status = 'completed',
                    training_end = NOW(),
                    model_version = $1,
                    training_duration_seconds = EXTRACT(EPOCH FROM (NOW() - training_start))::INTEGER,
                    training_samples = $2,
                    metadata = $3
                WHERE id = $4
            """, 
                new_version,
                1000,  # Mock 1000 training samples
                json.dumps({
                    'mock': True,
                    'training_method': 'simulated',
                    'performance_improvement': 5.2,
                    'hyperparameters': {
                        'learning_rate': 0.001,
                        'epochs': 100
                    }
                }),
                job_uuid
            )
            
            logger.info(f"Training job {job_id} completed successfully - Version {new_version}")
            
            # Record mock performance metrics
            await conn.execute("""
                INSERT INTO model_performance_metrics (
                    model_id, model_type, machine_id, model_version,
                    evaluation_date, evaluation_start, evaluation_end,
                    r_squared, rmse, mae, mape,
                    drift_detected, drift_score, sample_count, data_completeness
                ) VALUES ($1, $2, $3, $4, NOW(), NOW() - INTERVAL '7 days', NOW(), $5, $6, $7, $8, $9, $10, $11, $12)
            """,
                job_uuid,
                model_type,
                machine_uuid,
                new_version,
                0.85 + (new_version * 0.01),  # Improving R²
                15.0 - (new_version * 0.5),    # Decreasing RMSE
                10.0 - (new_version * 0.3),    # Decreasing MAE
                8.5 - (new_version * 0.2),     # Decreasing MAPE
                False,
                0.1,
                1000,
                0.95
            )
            
            logger.info(f"Performance metrics recorded for job {job_id}")
            
            # Publish training completed event (Phase 4 Session 5)
            await event_publisher.publish_training_completed(
                job_id=int(str(job_uuid).replace('-', '')[:8], 16),
                status='completed',
                metrics={
                    'version': new_version,
                    'r_squared': 0.85 + (new_version * 0.01),
                    'samples': 1000
                }
            )
    
    except Exception as e:
        logger.error(f"Training job {job_id} failed: {e}", exc_info=True)
        
        # Publish training failed event (Phase 4 Session 5)
        try:
            await event_publisher.publish_training_completed(
                job_id=int(str(job_uuid).replace('-', '')[:8], 16),
                status='failed',
                error_message=str(e)
            )
        except Exception as pub_error:
            logger.error(f"Failed to publish training failure event: {pub_error}")
        
        try:
            # Mark job as failed
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE model_training_history
                    SET training_status = 'failed',
                        training_end = NOW(),
                        error_message = $1
                    WHERE id = $2
                """, str(e), job_uuid)
        except Exception as update_error:
            logger.error(f"Failed to update job status: {update_error}")