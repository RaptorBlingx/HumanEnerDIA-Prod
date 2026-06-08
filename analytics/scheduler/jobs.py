"""
Scheduled Job Definitions
==========================
Job functions executed by APScheduler.

Jobs:
1. retrain_baseline_models() - Weekly baseline retraining
2. detect_anomalies_hourly() - Hourly anomaly detection
3. calculate_kpis_daily() - Daily KPI pre-calculations
"""

from datetime import datetime, timedelta
import logging
import traceback

from database import db
from services.baseline_service import BaselineService
from services.anomaly_service import AnomalyService
from services.kpi_service import KPIService

logger = logging.getLogger(__name__)


async def retrain_baseline_models():
    """
    Weekly job: Retrain baseline models for all active machines.
    
    Schedule: Sundays 02:00 (when factory is typically idle)
    
    Process:
    1. Get list of active machines
    2. For each machine:
       - Query last 30 days of data
       - Train new baseline model
       - Save model if R² > threshold
    3. Log results
    """
    job_start = datetime.utcnow()
    logger.info("=" * 70)
    logger.info("Starting weekly baseline retraining job")
    logger.info(f"Job started at: {job_start}")
    logger.info("=" * 70)
    
    results = {
        "machines_processed": 0,
        "models_trained": 0,
        "models_failed": 0,
        "errors": []
    }
    
    try:
        # Get all active machines
        query = """
            SELECT DISTINCT m.id, m.name, m.type
            FROM machines m
            JOIN machine_status ms ON m.id = ms.machine_id
            WHERE ms.is_running = TRUE
            ORDER BY m.name
        """
        
        async with db.pool.acquire() as conn:
            machines = await conn.fetch(query)
        logger.info(f"Found {len(machines)} active machines")
        
        # Training date range: last 30 days
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=30)
        
        # Process each machine
        for machine in machines:
            machine_id = machine['id']
            machine_name = machine['name']
            results["machines_processed"] += 1
            
            try:
                logger.info(f"Training baseline for {machine_name} ({machine_id})...")
                
                # Train baseline with default drivers
                result = await BaselineService.train_baseline(
                    machine_id=machine_id,
                    start_date=start_date,
                    end_date=end_date,
                    drivers=[
                        'production_units',
                        'outdoor_temp_c',
                        'humidity_percent',
                        'is_weekend',
                        'shift',
                        'time_of_day'
                    ]
                )
                
                if result.get('meets_quality_threshold'):
                    results["models_trained"] += 1
                    logger.info(f"  ✓ Model trained successfully (R² = {result.get('r_squared', 0):.4f})")
                else:
                    results["models_failed"] += 1
                    logger.warning(f"  ⚠ Model quality below threshold (R² = {result.get('r_squared', 0):.4f})")
                
            except Exception as e:
                results["models_failed"] += 1
                error_msg = f"Failed to train {machine_name}: {str(e)}"
                results["errors"].append(error_msg)
                logger.error(f"  ✗ {error_msg}")
                logger.debug(traceback.format_exc())
        
        # Log summary
        job_end = datetime.utcnow()
        duration = (job_end - job_start).total_seconds()
        
        logger.info("=" * 70)
        logger.info("Baseline retraining job completed")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info(f"Machines processed: {results['machines_processed']}")
        logger.info(f"Models trained successfully: {results['models_trained']}")
        logger.info(f"Models failed: {results['models_failed']}")
        logger.info("=" * 70)
        
        return results
        
    except Exception as e:
        logger.error(f"Baseline retraining job failed: {e}", exc_info=True)
        raise


async def detect_anomalies_hourly():
    """
    Hourly job: Detect anomalies for all active machines.
    
    Schedule: Every hour at :05 minutes
    
    Process:
    1. Get all active machines
    2. For each machine:
       - Analyze last hour of data
       - Detect anomalies using trained models
       - Save anomalies to database
    3. Log results
    """
    job_start = datetime.utcnow()
    logger.info("=" * 70)
    logger.info("Starting hourly anomaly detection job")
    logger.info(f"Job started at: {job_start}")
    logger.info("=" * 70)
    
    results = {
        "machines_processed": 0,
        "anomalies_detected": 0,
        "errors": []
    }
    
    try:
        # Get all active machines with baseline models
        query = """
            SELECT DISTINCT m.id, m.name
            FROM machines m
            JOIN machine_status ms ON m.id = ms.machine_id
            JOIN energy_baselines eb ON m.id = eb.machine_id
            WHERE ms.is_running = TRUE
              AND eb.is_active = TRUE
            ORDER BY m.name
        """
        
        async with db.pool.acquire() as conn:
            machines = await conn.fetch(query)
        logger.info(f"Found {len(machines)} machines with active baseline models")
        
        # Detection window: last hour
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(hours=1)
        
        # Process each machine
        for machine in machines:
            machine_id = machine['id']
            machine_name = machine['name']
            results["machines_processed"] += 1
            
            try:
                logger.info(f"Detecting anomalies for {machine_name}...")
                
                result = await AnomalyService.detect_anomalies(
                    machine_id=machine_id,
                    start_time=start_date,
                    end_time=end_date
                )
                
                anomalies_found = result.get('anomalies_detected', 0)
                results["anomalies_detected"] += anomalies_found
                
                if anomalies_found > 0:
                    logger.warning(f"  ⚠ Detected {anomalies_found} anomalies")
                else:
                    logger.info(f"  ✓ No anomalies detected")
                
            except Exception as e:
                error_msg = f"Failed to detect anomalies for {machine_name}: {str(e)}"
                results["errors"].append(error_msg)
                logger.error(f"  ✗ {error_msg}")
                logger.debug(traceback.format_exc())
        
        # Log summary
        job_end = datetime.utcnow()
        duration = (job_end - job_start).total_seconds()
        
        logger.info("=" * 70)
        logger.info("Anomaly detection job completed")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info(f"Machines processed: {results['machines_processed']}")
        logger.info(f"Total anomalies detected: {results['anomalies_detected']}")
        logger.info("=" * 70)
        
        return results
        
    except Exception as e:
        logger.error(f"Anomaly detection job failed: {e}", exc_info=True)
        raise


async def calculate_kpis_daily():
    """
    Daily job: Pre-calculate KPIs for all machines.
    
    Schedule: Daily at 00:30
    
    Process:
    1. Get all active machines
    2. For each machine:
       - Calculate all 5 KPIs for yesterday
       - Log results for monitoring
    3. Summary report
    
    Note: This is for logging/monitoring. KPIs are calculated
    on-demand via API, but this provides daily summaries.
    """
    job_start = datetime.utcnow()
    logger.info("=" * 70)
    logger.info("Starting daily KPI calculation job")
    logger.info(f"Job started at: {job_start}")
    logger.info("=" * 70)
    
    results = {
        "machines_processed": 0,
        "kpis_calculated": 0,
        "errors": []
    }
    
    try:
        # Get all machines
        query = """
            SELECT id, name, type
            FROM machines
            WHERE is_active = TRUE
            ORDER BY name
        """
        
        async with db.pool.acquire() as conn:
            machines = await conn.fetch(query)
        logger.info(f"Found {len(machines)} active machines")
        
        # Calculate for yesterday (full 24 hours)
        yesterday = datetime.utcnow().date() - timedelta(days=1)
        start_date = datetime.combine(yesterday, datetime.min.time())
        end_date = datetime.combine(yesterday, datetime.max.time())
        
        # Process each machine
        for machine in machines:
            machine_id = machine['id']
            machine_name = machine['name']
            results["machines_processed"] += 1
            
            try:
                logger.info(f"Calculating KPIs for {machine_name} ({yesterday})...")
                
                # Calculate all KPIs
                kpis = await KPIService.calculate_all_kpis(
                    machine_id=machine_id,
                    start_time=start_date,
                    end_time=end_date
                )
                
                results["kpis_calculated"] += 1
                
                # Log key metrics
                logger.info(f"  SEC: {kpis.get('sec_kwh_per_unit', 0):.6f} kWh/unit")
                logger.info(f"  Peak Demand: {kpis.get('peak_demand_kw', 0):.2f} kW")
                logger.info(f"  Load Factor: {kpis.get('load_factor_percent', 0):.1f}%")
                logger.info(f"  Energy: {kpis.get('total_energy_kwh', 0):.2f} kWh")
                logger.info(f"  Cost: ${kpis.get('total_cost', 0):.2f}")
                logger.info(f"  Carbon: {kpis.get('total_co2_kg', 0):.2f} kg CO₂")
                logger.info(f"  ✓ KPIs calculated successfully")
                
            except Exception as e:
                error_msg = f"Failed to calculate KPIs for {machine_name}: {str(e)}"
                results["errors"].append(error_msg)
                logger.error(f"  ✗ {error_msg}")
                logger.debug(traceback.format_exc())
        
        # Log summary
        job_end = datetime.utcnow()
        duration = (job_end - job_start).total_seconds()
        
        logger.info("=" * 70)
        logger.info("KPI calculation job completed")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info(f"Machines processed: {results['machines_processed']}")
        logger.info(f"KPIs calculated: {results['kpis_calculated']}")
        logger.info("=" * 70)
        
        return results
        
    except Exception as e:
        logger.error(f"KPI calculation job failed: {e}", exc_info=True)
        raise


async def cleanup_stuck_training_jobs():
    """
    Hourly job: Clean up stuck training jobs.
    
    Schedule: Every hour at :15 (e.g., 00:15, 01:15, etc.)
    
    Marks training jobs as 'failed' if they've been in 'pending' or 'running'
    state for more than 30 minutes. This prevents jobs from getting stuck
    indefinitely and blocking new training requests.
    """
    job_start = datetime.utcnow()
    logger.info("=" * 70)
    logger.info("Starting stuck training job cleanup")
    logger.info(f"Job started at: {job_start}")
    logger.info("=" * 70)
    
    try:
        pool = db.pool
        
        async with pool.acquire() as conn:
            # Find stuck jobs
            stuck_jobs = await conn.fetch("""
                SELECT id, model_type, machine_id, training_status, training_start
                FROM model_training_history
                WHERE training_status IN ('pending', 'running')
                AND training_start < NOW() - INTERVAL '30 minutes'
                ORDER BY training_start ASC
            """)
            
            if not stuck_jobs:
                logger.info("No stuck training jobs found")
                return {"cleaned_up": 0}
            
            logger.info(f"Found {len(stuck_jobs)} stuck training job(s)")
            
            # Mark them as failed
            for job in stuck_jobs:
                logger.info(f"  - Job {job['id']}: {job['model_type']} (stuck since {job['training_start']})")
                
                await conn.execute("""
                    UPDATE model_training_history
                    SET training_status = 'failed',
                        training_end = NOW(),
                        error_message = 'Job timed out - exceeded 30 minute limit'
                    WHERE id = $1
                """, job['id'])
            
            logger.info(f"✓ Cleaned up {len(stuck_jobs)} stuck job(s)")
        
        job_end = datetime.utcnow()
        duration = (job_end - job_start).total_seconds()
        
        logger.info("=" * 70)
        logger.info("Stuck training job cleanup completed")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info(f"Jobs cleaned up: {len(stuck_jobs)}")
        logger.info("=" * 70)
        
        return {"cleaned_up": len(stuck_jobs)}
        
    except Exception as e:
        logger.error(f"Cleanup job failed: {e}", exc_info=True)
        raise


# Manual job triggers for testing
async def trigger_all_jobs():
    """
    Convenience function to manually trigger all jobs.
    Useful for testing and maintenance.
    """
    logger.info("Manually triggering all scheduled jobs...")
    
    try:
        await retrain_baseline_models()
        await detect_anomalies_hourly()
        await calculate_kpis_daily()
        await cleanup_stuck_training_jobs()
        logger.info("All jobs completed successfully")
    except Exception as e:
        logger.error(f"Job execution failed: {e}", exc_info=True)
        raise