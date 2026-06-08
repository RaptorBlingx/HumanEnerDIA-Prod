"""
Event Subscriber
================
Subscribes to Redis channels and forwards events to WebSocket clients.

Phase 4 Session 5: Real-Time Updates
Author: EnMS Team
"""
import logging
from typing import Dict, Any

from services.redis_manager import redis_manager
from services.websocket_manager import connection_manager
from config import settings

logger = logging.getLogger(__name__)


class EventSubscriber:
    """Subscribes to Redis events and forwards to WebSocket clients."""
    
    async def start(self):
        """Start subscribing to all channels."""
        logger.info("Starting event subscriber...")
        
        # Subscribe to all channels
        await redis_manager.subscribe(
            settings.CHANNEL_ANOMALY_DETECTED,
            self._handle_anomaly_detected
        )
        
        await redis_manager.subscribe(
            settings.CHANNEL_METRIC_UPDATED,
            self._handle_metric_updated
        )
        
        await redis_manager.subscribe(
            settings.CHANNEL_TRAINING_STARTED,
            self._handle_training_started
        )
        
        await redis_manager.subscribe(
            settings.CHANNEL_TRAINING_PROGRESS,
            self._handle_training_progress
        )
        
        await redis_manager.subscribe(
            settings.CHANNEL_TRAINING_COMPLETED,
            self._handle_training_completed
        )
        
        await redis_manager.subscribe(
            settings.CHANNEL_SYSTEM_ALERT,
            self._handle_system_alert
        )
        
        logger.info("✓ Event subscriber started")
    
    async def _handle_anomaly_detected(self, channel: str, data: Dict[str, Any]):
        """Handle anomaly detected event."""
        logger.info(f"Anomaly detected: {data.get('machine_id')} - {data.get('severity')}")
        
        # Broadcast to dashboard clients
        await connection_manager.broadcast(
            {
                "type": "anomaly_detected",
                "data": data
            },
            connection_type="dashboard"
        )
        
        # Broadcast to anomaly page clients
        await connection_manager.broadcast(
            {
                "type": "anomaly_detected",
                "data": data
            },
            connection_type="anomalies"
        )
    
    async def _handle_metric_updated(self, channel: str, data: Dict[str, Any]):
        """Handle metric updated event."""
        logger.debug(f"Metric updated: {data.get('machine_id')} - {data.get('metric')}")
        
        # Broadcast to dashboard clients
        await connection_manager.broadcast(
            {
                "type": "metric_updated",
                "data": data
            },
            connection_type="dashboard"
        )
    
    async def _handle_training_started(self, channel: str, data: Dict[str, Any]):
        """Handle training started event."""
        logger.info(f"Training started: Job {data.get('job_id')}")
        
        # Broadcast to training page clients
        await connection_manager.broadcast(
            {
                "type": "training_started",
                "data": data
            },
            connection_type="training"
        )
    
    async def _handle_training_progress(self, channel: str, data: Dict[str, Any]):
        """Handle training progress event."""
        logger.debug(f"Training progress: Job {data.get('job_id')} - {data.get('progress_pct')}%")
        
        # Broadcast to training page clients
        await connection_manager.broadcast(
            {
                "type": "training_progress",
                "data": data
            },
            connection_type="training"
        )
    
    async def _handle_training_completed(self, channel: str, data: Dict[str, Any]):
        """Handle training completed event."""
        logger.info(f"Training completed: Job {data.get('job_id')} - {data.get('status')}")
        
        # Broadcast to training page clients
        await connection_manager.broadcast(
            {
                "type": "training_completed",
                "data": data
            },
            connection_type="training"
        )
        
        # Also update dashboard
        await connection_manager.broadcast(
            {
                "type": "model_updated",
                "data": data
            },
            connection_type="dashboard"
        )
    
    async def _handle_system_alert(self, channel: str, data: Dict[str, Any]):
        """Handle system alert event."""
        logger.warning(f"System alert: {data.get('alert_type')} - {data.get('severity')}")
        
        # Broadcast to all event clients
        await connection_manager.broadcast(
            {
                "type": "system_alert",
                "data": data
            },
            connection_type="events"
        )


# Global instance
event_subscriber = EventSubscriber()
