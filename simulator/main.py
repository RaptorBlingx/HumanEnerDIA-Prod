"""
EnMS - Factory Simulator Service
FastAPI Application Entry Point
"""

import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from config import settings
from models import HealthCheckResponse, MessageResponse
from simulator_manager import simulator_manager
from api import routes

# ============================================================================
# Logging Configuration
# ============================================================================

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/simulator.log')
    ]
)

logger = logging.getLogger(__name__)

# ============================================================================
# Application Lifecycle
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager
    Handles startup and shutdown events
    """
    # Startup
    logger.info("=" * 70)
    logger.info(f"Starting {settings.SERVICE_NAME} v{settings.SERVICE_VERSION}")
    logger.info("=" * 70)
    
    try:
        # Initialize simulator manager
        logger.info("Initializing simulator manager...")
        await simulator_manager.initialize()
        logger.info("✓ Simulator manager initialized")
        
        # Auto-start if configured
        if settings.SIMULATOR_AUTO_START:
            logger.info("Auto-starting simulator...")
            await simulator_manager.start()
            logger.info("✓ Simulator auto-started")
        
        logger.info("=" * 70)
        logger.info(f"🚀 {settings.SERVICE_NAME} is ready!")
        logger.info(f"📡 API available at: http://0.0.0.0:{settings.API_PORT}")
        logger.info(f"📊 API docs at: http://0.0.0.0:{settings.API_PORT}/docs")
        logger.info(f"🔌 MQTT broker: {settings.MQTT_HOST}:{settings.MQTT_PORT}")
        logger.info("=" * 70)
        
    except Exception as e:
        logger.error(f"Failed to start simulator: {e}", exc_info=True)
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down simulator...")
    try:
        await simulator_manager.stop()
        logger.info("✓ Simulator stopped")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
    
    logger.info(f"{settings.SERVICE_NAME} shut down successfully")

# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title=settings.SERVICE_NAME,
    description="Factory data simulator for EnMS - generates realistic time-series data for 5 machine types",
    version=settings.SERVICE_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# ============================================================================
# Middleware
# ============================================================================

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests"""
    start_time = datetime.utcnow()
    
    # Log request
    logger.info(f"→ {request.method} {request.url.path}")
    
    # Process request
    response = await call_next(request)
    
    # Log response
    duration = (datetime.utcnow() - start_time).total_seconds()
    logger.info(f"← {request.method} {request.url.path} - {response.status_code} ({duration:.3f}s)")
    
    return response

# ============================================================================
# Exception Handlers
# ============================================================================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors"""
    logger.warning(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "message": "Validation error",
            "errors": exc.errors()
        }
    )

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Handle value errors"""
    logger.warning(f"Value error: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "success": False,
            "message": str(exc)
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected errors"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "message": "Internal server error",
            "detail": str(exc) if settings.LOG_LEVEL == "DEBUG" else "An error occurred"
        }
    )

# ============================================================================
# Root Endpoints
# ============================================================================

@app.get("/", response_model=MessageResponse)
async def root():
    """Root endpoint - service information"""
    return MessageResponse(
        message=f"{settings.SERVICE_NAME} v{settings.SERVICE_VERSION}",
        success=True,
        data={
            "service": settings.SERVICE_NAME,
            "version": settings.SERVICE_VERSION,
            "docs": "/docs",
            "health": "/health",
            "api": "/simulator"
        }
    )

@app.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """Health check endpoint"""
    from mqtt_publisher import mqtt_publisher
    
    # Check database connection
    db_connected = False
    try:
        if simulator_manager.db_pool:
            async with simulator_manager.db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            db_connected = True
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
    
    # Check MQTT connection
    mqtt_connected = mqtt_publisher.connected
    
    # Overall health status
    is_healthy = db_connected and mqtt_connected
    
    return HealthCheckResponse(
        status="healthy" if is_healthy else "degraded",
        service=settings.SERVICE_NAME,
        version=settings.SERVICE_VERSION,
        timestamp=datetime.utcnow(),
        mqtt_connected=mqtt_connected,
        database_connected=db_connected
    )

# ============================================================================
# Include API Routes
# ============================================================================

app.include_router(
    routes.router,
    prefix="/simulator",
    tags=["simulator"]
)

# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.API_PORT,
        log_level=settings.LOG_LEVEL.lower(),
        reload=False  # Set to True for development
    )