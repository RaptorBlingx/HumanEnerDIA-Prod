"""
APScheduler Configuration
==========================
Automated job scheduling for analytics tasks.

Jobs:
- Weekly baseline retraining (Sundays 02:00)
- Hourly anomaly detection (every hour at :05)
- Daily KPI pre-calculations (00:30)
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
import logging

from config import settings

logger = logging.getLogger(__name__)


class AnalyticsScheduler:
    """
    Analytics job scheduler using APScheduler.
    
    Manages automated execution of:
    - Baseline model retraining
    - Anomaly detection
    - KPI calculations
    """
    
    def __init__(self):
        """Initialize the scheduler"""
        self.scheduler = AsyncIOScheduler(
            job_defaults={
                'coalesce': True,  # Combine missed jobs
                'max_instances': 1,  # Prevent concurrent execution
                'misfire_grace_time': 300  # 5 minutes grace period
            }
        )
        self.jobs = {}
        logger.info("Scheduler initialized")
    
    def start(self):
        """Start the scheduler and register jobs"""
        if not settings.SCHEDULER_ENABLED:
            logger.info("Scheduler is disabled in configuration")
            return
        
        try:
            # Import job functions
            from scheduler.jobs import (
                retrain_baseline_models,
                detect_anomalies_hourly,
                calculate_kpis_daily,
                cleanup_stuck_training_jobs
            )
            
            # Job 1: Weekly baseline retraining (Sundays 02:00)
            self.jobs['baseline_retrain'] = self.scheduler.add_job(
                retrain_baseline_models,
                trigger=CronTrigger.from_crontab(settings.JOB_BASELINE_RETRAIN_SCHEDULE),
                id='baseline_retrain',
                name='Weekly Baseline Retraining',
                replace_existing=True
            )
            logger.info(f"Registered job: baseline_retrain (schedule: {settings.JOB_BASELINE_RETRAIN_SCHEDULE})")
            
            # Job 2: Hourly anomaly detection (every hour at :05)
            self.jobs['anomaly_detect'] = self.scheduler.add_job(
                detect_anomalies_hourly,
                trigger=CronTrigger.from_crontab(settings.JOB_ANOMALY_DETECT_SCHEDULE),
                id='anomaly_detect',
                name='Hourly Anomaly Detection',
                replace_existing=True
            )
            logger.info(f"Registered job: anomaly_detect (schedule: {settings.JOB_ANOMALY_DETECT_SCHEDULE})")
            
            # Job 3: Daily KPI calculations (00:30)
            self.jobs['kpi_calculate'] = self.scheduler.add_job(
                calculate_kpis_daily,
                trigger=CronTrigger.from_crontab(settings.JOB_KPI_CALCULATE_SCHEDULE),
                id='kpi_calculate',
                name='Daily KPI Calculation',
                replace_existing=True
            )
            logger.info(f"Registered job: kpi_calculate (schedule: {settings.JOB_KPI_CALCULATE_SCHEDULE})")
            
            # Job 4: Hourly cleanup of stuck training jobs (every hour at :15)
            self.jobs['training_cleanup'] = self.scheduler.add_job(
                cleanup_stuck_training_jobs,
                trigger=CronTrigger.from_crontab('15 * * * *'),  # Every hour at :15
                id='training_cleanup',
                name='Training Job Cleanup',
                replace_existing=True
            )
            logger.info(f"Registered job: training_cleanup (schedule: 15 * * * *)")
            
            # Start scheduler
            self.scheduler.start()
            logger.info("✓ Scheduler started successfully")
            
            # Log next run times
            for job_id, job in self.jobs.items():
                next_run = job.next_run_time
                logger.info(f"  → {job.name}: next run at {next_run}")
        
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}", exc_info=True)
            raise
    
    def stop(self):
        """Stop the scheduler gracefully"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            logger.info("Scheduler stopped")
    
    def get_status(self) -> dict:
        """
        Get scheduler status and job information.
        
        Returns:
            dict: Scheduler status, job list, and next run times
        """
        if not self.scheduler.running:
            return {
                "enabled": settings.SCHEDULER_ENABLED,
                "running": False,
                "jobs": []
            }
        
        jobs_info = []
        for job in self.scheduler.get_jobs():
            jobs_info.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            })
        
        return {
            "enabled": settings.SCHEDULER_ENABLED,
            "running": True,
            "job_count": len(jobs_info),
            "jobs": jobs_info
        }
    
    def trigger_job(self, job_id: str) -> bool:
        """
        Manually trigger a job to run immediately.
        
        Args:
            job_id: ID of the job to trigger
            
        Returns:
            bool: True if job was triggered successfully
        """
        try:
            job = self.scheduler.get_job(job_id)
            if job:
                job.modify(next_run_time=datetime.now())
                logger.info(f"Manually triggered job: {job_id}")
                return True
            else:
                logger.warning(f"Job not found: {job_id}")
                return False
        except Exception as e:
            logger.error(f"Failed to trigger job {job_id}: {e}")
            return False


# Global scheduler instance
scheduler = AnalyticsScheduler()