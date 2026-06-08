"""
Redis Connection Manager for Pub/Sub
=====================================
Manages Redis connection and pub/sub operations for real-time events.

Phase 4 Session 5: Real-Time Updates
Author: EnMS Team
"""
import redis.asyncio as redis
from typing import Optional, Callable, Dict
import logging
import asyncio
from config import settings

logger = logging.getLogger(__name__)


class RedisManager:
    """Manages Redis connection and pub/sub operations."""
    
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None
        self.subscribers: Dict[str, list] = {}
        self._listener_task: Optional[asyncio.Task] = None
    
    async def connect(self):
        """Establish Redis connection."""
        try:
            self.redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                db=settings.REDIS_DB,
                decode_responses=True
            )
            
            # Test connection
            await self.redis_client.ping()
            logger.info("✓ Redis connected successfully")
            
            # Initialize pub/sub
            self.pubsub = self.redis_client.pubsub()
            
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    async def disconnect(self):
        """Close Redis connection."""
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        
        if self.pubsub:
            await self.pubsub.close()
        
        if self.redis_client:
            await self.redis_client.close()
        
        logger.info("Redis disconnected")
    
    async def publish(self, channel: str, message: dict):
        """
        Publish message to Redis channel.
        
        Args:
            channel: Channel name
            message: Message dict (will be JSON serialized)
        """
        try:
            import json
            message_str = json.dumps(message)
            await self.redis_client.publish(channel, message_str)
            logger.debug(f"Published to {channel}: {message}")
        except Exception as e:
            logger.error(f"Failed to publish to {channel}: {e}")
    
    async def subscribe(self, channel: str, callback: Callable):
        """
        Subscribe to Redis channel with callback.
        
        Args:
            channel: Channel name
            callback: Async function to call with message
        """
        try:
            await self.pubsub.subscribe(channel)
            
            if channel not in self.subscribers:
                self.subscribers[channel] = []
            self.subscribers[channel].append(callback)
            
            logger.info(f"Subscribed to channel: {channel}")
            
            # Start listener if not already running
            if not self._listener_task:
                self._listener_task = asyncio.create_task(self._listen())
        
        except Exception as e:
            logger.error(f"Failed to subscribe to {channel}: {e}")
    
    async def _listen(self):
        """Listen for messages on subscribed channels."""
        try:
            async for message in self.pubsub.listen():
                if message["type"] == "message":
                    channel = message["channel"]
                    data = message["data"]
                    
                    # Parse JSON
                    import json
                    try:
                        parsed_data = json.loads(data)
                    except:
                        parsed_data = data
                    
                    # Call all callbacks for this channel
                    if channel in self.subscribers:
                        for callback in self.subscribers[channel]:
                            try:
                                await callback(channel, parsed_data)
                            except Exception as e:
                                logger.error(f"Callback error for {channel}: {e}")
        
        except asyncio.CancelledError:
            logger.info("Redis listener cancelled")
        except Exception as e:
            logger.error(f"Redis listener error: {e}")


# Global instance
redis_manager = RedisManager()
