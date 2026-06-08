"""
WebSocket Connection Manager
=============================
Manages WebSocket connections and message broadcasting.

Phase 4 Session 5: Real-Time Updates
Author: EnMS Team
"""
from fastapi import WebSocket
from typing import Dict, Set
import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections and message broadcasting."""
    
    def __init__(self):
        # Store connections by type
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {
            "dashboard": {},
            "anomalies": {},
            "training": {},
            "events": {}
        }
    
    async def connect(self, websocket: WebSocket, client_id: str, connection_type: str):
        """
        Accept and register new WebSocket connection.
        
        Args:
            websocket: WebSocket connection
            client_id: Unique client identifier
            connection_type: Type of connection (dashboard, anomalies, training, events)
        """
        # Accept WebSocket with CORS support (allow any origin for dev)
        # In production, specify allowed origins: await websocket.accept(headers=[("Access-Control-Allow-Origin", "...")])
        try:
            await websocket.accept()
        except Exception as e:
            logger.error(f"Failed to accept WebSocket connection: {e}")
            raise
        
        if connection_type not in self.active_connections:
            self.active_connections[connection_type] = {}
        
        self.active_connections[connection_type][client_id] = websocket
        
        logger.info(f"Client {client_id} connected to {connection_type}")
        logger.info(f"Total connections: {self.get_connection_count()}")
        
        # Send welcome message
        await self.send_personal_message(
            {
                "type": "welcome",
                "data": {
                    "channel": connection_type,
                    "client_id": client_id,
                    "timestamp": datetime.utcnow().isoformat()
                }
            },
            websocket
        )
    
    def disconnect(self, client_id: str, connection_type: str):
        """
        Remove WebSocket connection.
        
        Args:
            client_id: Client identifier
            connection_type: Type of connection
        """
        if connection_type in self.active_connections:
            if client_id in self.active_connections[connection_type]:
                del self.active_connections[connection_type][client_id]
                logger.info(f"Client {client_id} disconnected from {connection_type}")
                logger.info(f"Total connections: {self.get_connection_count()}")
    
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send message to specific client."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Failed to send personal message: {e}")
    
    async def broadcast(self, message: dict, connection_type: str = None):
        """
        Broadcast message to all clients or specific connection type.
        
        Args:
            message: Message to broadcast
            connection_type: If specified, only broadcast to this type
        """
        if connection_type:
            # Broadcast to specific type
            await self._broadcast_to_type(message, connection_type)
        else:
            # Broadcast to all
            for conn_type in self.active_connections:
                await self._broadcast_to_type(message, conn_type)
    
    async def _broadcast_to_type(self, message: dict, connection_type: str):
        """Broadcast to all connections of a specific type."""
        if connection_type not in self.active_connections:
            return
        
        disconnected = []
        
        for client_id, websocket in self.active_connections[connection_type].items():
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Failed to send to {client_id}: {e}")
                disconnected.append(client_id)
        
        # Remove disconnected clients
        for client_id in disconnected:
            self.disconnect(client_id, connection_type)
    
    def get_connection_count(self) -> int:
        """Get total number of active connections."""
        total = 0
        for conn_type in self.active_connections:
            total += len(self.active_connections[conn_type])
        return total
    
    def get_connections_by_type(self) -> dict:
        """Get connection count by type."""
        return {
            conn_type: len(connections)
            for conn_type, connections in self.active_connections.items()
        }


# Global instance
connection_manager = ConnectionManager()
