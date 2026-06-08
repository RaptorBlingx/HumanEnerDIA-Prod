"""
EnMS Analytics - OVOS Voice Bridge Proxy
=========================================
Proxy endpoint for forwarding natural language queries to OVOS REST Bridge.

This is separate from ovos.py which contains direct database query endpoints.
This router proxies text queries to the OVOS voice assistant system.

Architecture:
    EnMS Frontend → This Proxy → OVOS REST Bridge (WSL2:5000) → OVOS Messagebus → EnMS Skill

Configuration via environment variables:
    OVOS_BRIDGE_HOST: Hostname of OVOS REST Bridge (default: ovos-enms)
    OVOS_BRIDGE_PORT: Port of OVOS REST Bridge (default: 5000)
    OVOS_BRIDGE_TIMEOUT: Request timeout in seconds (default: 20)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import httpx
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ovos/voice", tags=["OVOS Voice"])

# ============================================================================
# Configuration (Environment Variables)
# ============================================================================

OVOS_BRIDGE_HOST = os.getenv("OVOS_BRIDGE_HOST", "ovos-enms")
OVOS_BRIDGE_PORT = os.getenv("OVOS_BRIDGE_PORT", "5000")
OVOS_BRIDGE_TIMEOUT = float(os.getenv("OVOS_BRIDGE_TIMEOUT", "20"))
OVOS_BRIDGE_URL = f"http://{OVOS_BRIDGE_HOST}:{OVOS_BRIDGE_PORT}"


# ============================================================================
# Request/Response Models
# ============================================================================

class VoiceQueryRequest(BaseModel):
    """Request model for voice query"""
    text: str
    session_id: Optional[str] = None
    include_audio: bool = True  # Request audio response from OVOS TTS
    
    class Config:
        json_schema_extra = {
            "example": {
                "text": "What's the energy consumption for Compressor-1?",
                "session_id": None,
                "include_audio": True
            }
        }


class VoiceQueryResponse(BaseModel):
    """Response model for voice query with optional audio"""
    success: bool
    response: Optional[str] = None
    intent: Optional[str] = None
    confidence: Optional[float] = None
    data: Optional[dict] = None
    insights: Optional[dict] = None
    audio_base64: Optional[str] = None  # Base64 encoded WAV audio from OVOS TTS
    audio_format: Optional[str] = None  # Audio format (wav, mp3, etc.) - None if no audio
    pdf_base64: Optional[str] = None  # LEGACY: Base64 encoded PDF for report downloads (V1)
    pdf_filename: Optional[str] = None  # LEGACY: Suggested filename for PDF download (V1)
    pdf_download: Optional[dict] = None  # V2: PDF download metadata {report_id, download_url, filename, file_size_kb, ready}
    error: Optional[str] = None
    session_id: str
    latency_ms: int
    tts_latency_ms: int = 0
    timestamp: str
    bridge_url: str


class VoiceBridgeHealth(BaseModel):
    """Health check response for OVOS bridge"""
    status: str
    bridge_reachable: bool
    bridge_url: str
    ovos_connected: Optional[bool] = None
    tts_available: Optional[bool] = None
    tts_engine: Optional[str] = None
    error: Optional[str] = None


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/query", response_model=VoiceQueryResponse)
async def voice_query(request: VoiceQueryRequest):
    """
    Send natural language query to OVOS voice assistant.
    
    This endpoint proxies text queries to the OVOS REST Bridge running on WSL2,
    which then forwards to OVOS messagebus for processing by the EnMS skill.
    
    **Audio Response:**
    When include_audio=true (default), returns base64-encoded WAV audio from OVOS TTS (Mimic3).
    Browser can play it with: `new Audio("data:audio/wav;base64," + audio_base64).play()`
    
    **Example queries:**
    - "What's the energy consumption for Compressor-1?"
    - "Give me a factory overview"
    - "How much did we spend on energy today?"
    - "Are there any anomalies?"
    - "What's the forecast for tomorrow?"
    
    **Configuration:**
    Set OVOS_BRIDGE_HOST to the OVOS REST bridge hostname or IP.
    """
    start_time = datetime.now()
    
    # Use /query/voice endpoint for audio, /query for text-only
    endpoint = "/query/voice" if request.include_audio else "/query"
    
    try:
        async with httpx.AsyncClient(timeout=OVOS_BRIDGE_TIMEOUT) as client:
            response = await client.post(
                f"{OVOS_BRIDGE_URL}{endpoint}",
                json={
                    "text": request.text,
                    "session_id": request.session_id
                }
            )
            
            latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            if response.status_code != 200:
                logger.error(f"OVOS Bridge returned {response.status_code}: {response.text}")
                return VoiceQueryResponse(
                    success=False,
                    response=None,
                    intent=None,
                    confidence=None,
                    data=None,
                    insights=None,
                    audio_base64=None,
                    error=f"OVOS Bridge error: {response.status_code}",
                    session_id=request.session_id or "none",
                    latency_ms=latency_ms,
                    tts_latency_ms=0,
                    timestamp=datetime.now().isoformat(),
                    bridge_url=OVOS_BRIDGE_URL
                )
            
            data = response.json()
            
            return VoiceQueryResponse(
                success=data.get("success", False),
                response=data.get("response"),
                intent=data.get("intent"),
                confidence=data.get("confidence"),
                data=data.get("data"),
                insights=data.get("insights"),
                audio_base64=data.get("audio_base64"),
                audio_format=data.get("audio_format", "wav"),
                pdf_base64=data.get("pdf_base64"),  # V1 legacy
                pdf_filename=data.get("pdf_filename"),  # V1 legacy
                pdf_download=data.get("pdf_download"),  # V2: Pass through PDF metadata object
                error=data.get("error"),
                session_id=data.get("session_id", request.session_id or "auto"),
                latency_ms=latency_ms,
                tts_latency_ms=data.get("tts_latency_ms", 0),
                timestamp=datetime.now().isoformat(),
                bridge_url=OVOS_BRIDGE_URL
            )
            
    except httpx.ConnectError as e:
        latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        logger.error(f"Cannot connect to OVOS Bridge at {OVOS_BRIDGE_URL}: {e}")
        return VoiceQueryResponse(
            success=False,
            response=None,
            intent=None,
            confidence=None,
            data=None,
            insights=None,
            audio_base64=None,
            error=f"Cannot connect to OVOS Bridge at {OVOS_BRIDGE_URL}. Is it running?",
            session_id=request.session_id or "none",
            latency_ms=latency_ms,
            tts_latency_ms=0,
            timestamp=datetime.now().isoformat(),
            bridge_url=OVOS_BRIDGE_URL
        )
        
    except httpx.TimeoutException as e:
        latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        logger.error(f"Timeout connecting to OVOS Bridge: {e}")
        return VoiceQueryResponse(
            success=False,
            response=None,
            intent=None,
            confidence=None,
            data=None,
            insights=None,
            audio_base64=None,
            error=f"Timeout after {OVOS_BRIDGE_TIMEOUT}s waiting for OVOS response",
            session_id=request.session_id or "none",
            latency_ms=latency_ms,
            tts_latency_ms=0,
            timestamp=datetime.now().isoformat(),
            bridge_url=OVOS_BRIDGE_URL
        )
        
    except Exception as e:
        latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        logger.error(f"Error querying OVOS: {e}")
        return VoiceQueryResponse(
            success=False,
            response=None,
            intent=None,
            confidence=None,
            data=None,
            insights=None,
            audio_base64=None,
            error=str(e),
            session_id=request.session_id or "none",
            latency_ms=latency_ms,
            tts_latency_ms=0,
            timestamp=datetime.now().isoformat(),
            bridge_url=OVOS_BRIDGE_URL
        )


@router.get("/health", response_model=VoiceBridgeHealth)
async def voice_bridge_health():
    """
    Check connectivity to OVOS REST Bridge.
    
    Use this to verify the OVOS voice system is reachable before sending queries.
    
    **Returns:**
    - bridge_reachable: Can we connect to the REST bridge?
    - ovos_connected: Is the bridge connected to OVOS messagebus?
    - tts_available: Is TTS (Mimic3) available for audio responses?
    - tts_engine: Which TTS engine is configured (mimic3, piper, espeak)
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{OVOS_BRIDGE_URL}/health")
            
            if response.status_code == 200:
                data = response.json()
                # OVOS bridge returns 'messagebus_connected', map to 'ovos_connected'
                is_connected = data.get("messagebus_connected", data.get("ovos_connected", False))
                return VoiceBridgeHealth(
                    status="ok" if is_connected else "degraded",
                    bridge_reachable=True,
                    bridge_url=OVOS_BRIDGE_URL,
                    ovos_connected=is_connected,
                    tts_available=data.get("tts_available", False),
                    tts_engine=data.get("tts_engine"),
                    error=None
                )
            else:
                return VoiceBridgeHealth(
                    status="error",
                    bridge_reachable=True,
                    bridge_url=OVOS_BRIDGE_URL,
                    ovos_connected=False,
                    tts_available=False,
                    tts_engine=None,
                    error=f"Bridge returned status {response.status_code}"
                )
                
    except httpx.ConnectError:
        return VoiceBridgeHealth(
            status="unreachable",
            bridge_reachable=False,
            bridge_url=OVOS_BRIDGE_URL,
            ovos_connected=False,
            tts_available=False,
            tts_engine=None,
            error=f"Cannot connect to OVOS Bridge at {OVOS_BRIDGE_URL}"
        )
        
    except Exception as e:
        return VoiceBridgeHealth(
            status="error",
            bridge_reachable=False,
            bridge_url=OVOS_BRIDGE_URL,
            ovos_connected=False,
            tts_available=False,
            tts_engine=None,
            error=str(e)
        )


@router.get("/config")
async def voice_config():
    """
    Get current OVOS Bridge configuration.
    
    Shows the configured OVOS Bridge connection details.
    Useful for debugging connectivity issues.
    """
    return {
        "bridge_host": OVOS_BRIDGE_HOST,
        "bridge_port": OVOS_BRIDGE_PORT,
        "bridge_url": OVOS_BRIDGE_URL,
        "timeout_seconds": OVOS_BRIDGE_TIMEOUT,
        "env_vars": {
            "OVOS_BRIDGE_HOST": "Set this to change the bridge host",
            "OVOS_BRIDGE_PORT": "Set this to change the bridge port (default: 5000)",
            "OVOS_BRIDGE_TIMEOUT": "Set this to change timeout (default: 20s)"
        }
    }
