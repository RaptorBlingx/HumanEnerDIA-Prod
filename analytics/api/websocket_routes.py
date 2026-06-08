"""
WebSocket API Routes
====================
Real-time WebSocket endpoints for live data streaming.

Phase 4 Session 5: Real-Time Updates
Author: EnMS Team
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from typing import Optional
import logging
import uuid
from datetime import datetime

from services.websocket_manager import connection_manager
from services.redis_manager import redis_manager
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["WebSocket"])


@router.websocket("/dashboard")
async def websocket_dashboard(websocket: WebSocket, client_id: Optional[str] = Query(None)):
    """
    WebSocket endpoint for real-time dashboard updates.
    
    Streams:
    - Active machine count updates
    - Baseline model count updates
    - Recent anomaly count updates
    - Scheduler status updates
    """
    if not client_id:
        client_id = str(uuid.uuid4())
    
    await connection_manager.connect(websocket, client_id, "dashboard")
    
    try:
        while True:
            # Keep connection alive and receive client messages
            data = await websocket.receive_text()
            
            # Echo back or handle client messages
            if data == "ping":
                await connection_manager.send_personal_message(
                    {"type": "pong", "timestamp": datetime.utcnow().isoformat()},
                    websocket
                )
    
    except WebSocketDisconnect:
        connection_manager.disconnect(client_id, "dashboard")
        logger.info(f"Dashboard client {client_id} disconnected")
    
    except Exception as e:
        logger.error(f"Dashboard WebSocket error: {e}")
        connection_manager.disconnect(client_id, "dashboard")


@router.websocket("/anomalies")
async def websocket_anomalies(websocket: WebSocket, client_id: Optional[str] = Query(None)):
    """
    WebSocket endpoint for real-time anomaly alerts.
    
    Streams:
    - New anomaly detections
    - Anomaly severity changes
    - Anomaly acknowledgments
    """
    if not client_id:
        client_id = str(uuid.uuid4())
    
    await connection_manager.connect(websocket, client_id, "anomalies")
    
    try:
        while True:
            data = await websocket.receive_text()
            
            if data == "ping":
                await connection_manager.send_personal_message(
                    {"type": "pong", "timestamp": datetime.utcnow().isoformat()},
                    websocket
                )
    
    except WebSocketDisconnect:
        connection_manager.disconnect(client_id, "anomalies")
        logger.info(f"Anomalies client {client_id} disconnected")
    
    except Exception as e:
        logger.error(f"Anomalies WebSocket error: {e}")
        connection_manager.disconnect(client_id, "anomalies")


@router.websocket("/training")
async def websocket_training(websocket: WebSocket, client_id: Optional[str] = Query(None)):
    """
    WebSocket endpoint for real-time training progress.
    
    Streams:
    - Training job started events
    - Training progress updates
    - Training completion events
    - Training error notifications
    """
    if not client_id:
        client_id = str(uuid.uuid4())
    
    await connection_manager.connect(websocket, client_id, "training")
    
    try:
        while True:
            data = await websocket.receive_text()
            
            if data == "ping":
                await connection_manager.send_personal_message(
                    {"type": "pong", "timestamp": datetime.utcnow().isoformat()},
                    websocket
                )
    
    except WebSocketDisconnect:
        connection_manager.disconnect(client_id, "training")
        logger.info(f"Training client {client_id} disconnected")
    
    except Exception as e:
        logger.error(f"Training WebSocket error: {e}")
        connection_manager.disconnect(client_id, "training")


@router.websocket("/events")
async def websocket_events(websocket: WebSocket, client_id: Optional[str] = Query(None)):
    """
    WebSocket endpoint for general system events.
    
    Streams:
    - System alerts
    - Service status changes
    - Configuration updates
    - General notifications
    """
    if not client_id:
        client_id = str(uuid.uuid4())
    
    await connection_manager.connect(websocket, client_id, "events")
    
    try:
        while True:
            data = await websocket.receive_text()
            
            if data == "ping":
                await connection_manager.send_personal_message(
                    {"type": "pong", "timestamp": datetime.utcnow().isoformat()},
                    websocket
                )
    
    except WebSocketDisconnect:
        connection_manager.disconnect(client_id, "events")
        logger.info(f"Events client {client_id} disconnected")
    
    except Exception as e:
        logger.error(f"Events WebSocket error: {e}")
        connection_manager.disconnect(client_id, "events")
