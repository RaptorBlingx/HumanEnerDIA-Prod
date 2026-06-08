"""
EnMS - Factory Simulator Service
API Routes
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status

from models import (
    SimulatorStartRequest,
    SimulatorStopRequest,
    SimulatorConfigUpdate,
    AnomalyInjectionRequest,
    SimulatorStatusResponse,
    MachineStatusResponse,
    MessageResponse
)
from simulator_manager import simulator_manager
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================================================
# Simulator Control Endpoints
# ============================================================================

@router.post("/start", response_model=MessageResponse)
async def start_simulator(request: SimulatorStartRequest = None):
    """
    Start the factory simulator
    
    Optionally specify which machines to start. If not specified, starts all machines.
    
    **Request Body:**
    - `factory_ids` (optional): List of factory IDs to start
    - `machine_ids` (optional): List of machine IDs to start
    
    **Example:**
    ```json
    {
        "machine_ids": ["c0000000-0000-0000-0000-000000000001", "c0000000-0000-0000-0000-000000000002"]
    }
    ```
    
    **Returns:**
    - Success message with started machines count
    """
    try:
        # Extract machine IDs if provided
        machine_ids = None
        if request and request.machine_ids:
            machine_ids = request.machine_ids
        
        # Start simulator
        await simulator_manager.start(machine_ids=machine_ids)
        
        # Get status
        status_data = simulator_manager.get_status()
        
        return MessageResponse(
            message="Simulator started successfully",
            success=True,
            data={
                "running_machines": status_data["running_machines"],
                "total_machines": status_data["machines_count"]
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to start simulator: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start simulator: {str(e)}"
        )


@router.post("/stop", response_model=MessageResponse)
async def stop_simulator(request: SimulatorStopRequest = None):
    """
    Stop the factory simulator
    
    Optionally specify which machines to stop. If not specified, stops all machines.
    
    **Request Body:**
    - `factory_ids` (optional): List of factory IDs to stop
    - `machine_ids` (optional): List of machine IDs to stop
    
    **Returns:**
    - Success message with stopped machines count
    """
    try:
        # Extract machine IDs if provided
        machine_ids = None
        if request and request.machine_ids:
            machine_ids = request.machine_ids
        
        # Stop simulator
        await simulator_manager.stop(machine_ids=machine_ids)
        
        # Get status
        status_data = simulator_manager.get_status()
        
        return MessageResponse(
            message="Simulator stopped successfully",
            success=True,
            data={
                "running_machines": status_data["running_machines"],
                "total_machines": status_data["machines_count"]
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to stop simulator: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop simulator: {str(e)}"
        )


@router.put("/config", response_model=MessageResponse)
async def update_configuration(config: SimulatorConfigUpdate):
    """
    Update simulator configuration
    
    **Request Body:**
    - `enable_anomalies` (optional): Enable/disable anomaly generation
    - `anomaly_probability` (optional): Probability of anomalies (0.0-1.0)
    - `weekend_production_factor` (optional): Production factor for weekends (0.0-1.0)
    
    **Example:**
    ```json
    {
        "enable_anomalies": true,
        "anomaly_probability": 0.15
    }
    ```
    
    **Returns:**
    - Success message with updated configuration
    """
    try:
        updated_fields = {}
        
        # Update settings (note: these are runtime changes, not persisted)
        if config.enable_anomalies is not None:
            settings.SIMULATOR_ENABLE_ANOMALIES = config.enable_anomalies
            updated_fields["enable_anomalies"] = config.enable_anomalies
        
        if config.anomaly_probability is not None:
            settings.ANOMALY_PROBABILITY = config.anomaly_probability
            updated_fields["anomaly_probability"] = config.anomaly_probability
        
        if config.weekend_production_factor is not None:
            settings.WEEKEND_PRODUCTION_FACTOR = config.weekend_production_factor
            updated_fields["weekend_production_factor"] = config.weekend_production_factor
        
        logger.info(f"Configuration updated: {updated_fields}")
        
        return MessageResponse(
            message="Configuration updated successfully",
            success=True,
            data=updated_fields
        )
        
    except Exception as e:
        logger.error(f"Failed to update configuration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update configuration: {str(e)}"
        )

# ============================================================================
# Status Endpoints
# ============================================================================

@router.get("/status", response_model=SimulatorStatusResponse)
async def get_status():
    """
    Get overall simulator status
    
    Returns comprehensive status including:
    - Current status (running/stopped/etc.)
    - Uptime
    - Number of factories and machines
    - Running machines count
    - Total readings generated
    - MQTT connection status
    - Configuration
    
    **Returns:**
    - Complete simulator status
    """
    try:
        status_data = simulator_manager.get_status()
        return SimulatorStatusResponse(**status_data)
        
    except Exception as e:
        logger.error(f"Failed to get status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get status: {str(e)}"
        )

# ============================================================================
# Machine Endpoints
# ============================================================================

@router.get("/machines", response_model=List[MachineStatusResponse])
async def get_all_machines():
    """
    Get status of all machines
    
    Returns a list of all machines with their current state:
    - Machine ID and name
    - Machine type (compressor, hvac, motor, pump, injection_molding)
    - Running status
    - Operating mode (idle, running, maintenance, fault, offline)
    - Current power consumption
    - Data interval
    - Readings generated
    - Anomaly status
    
    **Returns:**
    - List of machine statuses
    """
    try:
        machines = simulator_manager.get_all_machines_status()
        
        # Convert to response model
        return [
            MachineStatusResponse(
                machine_id=m["machine_id"],
                machine_name=m["machine_name"],
                machine_type=m["machine_type"],
                is_running=m["is_running"],
                operating_mode=m["operating_mode"],
                current_power_kw=m["current_power_kw"],
                data_interval_seconds=m["data_interval_seconds"],
                readings_generated=m["readings_generated"],
                last_reading_time=m["last_reading_time"],
                anomaly_active=m["anomaly_active"]
            )
            for m in machines
        ]
        
    except Exception as e:
        logger.error(f"Failed to get machines: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get machines: {str(e)}"
        )


@router.get("/machines/{machine_id}", response_model=MachineStatusResponse)
async def get_machine_status(machine_id: str):
    """
    Get status of a specific machine
    
    **Path Parameters:**
    - `machine_id`: UUID of the machine
    
    **Example:**
    ```
    GET /simulator/machines/c0000000-0000-0000-0000-000000000001
    ```
    
    **Returns:**
    - Detailed machine status
    """
    try:
        machine = simulator_manager.get_machine_status(machine_id)
        
        if not machine:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Machine {machine_id} not found"
            )
        
        return MachineStatusResponse(
            machine_id=machine["machine_id"],
            machine_name=machine["machine_name"],
            machine_type=machine["machine_type"],
            is_running=machine["is_running"],
            operating_mode=machine["operating_mode"],
            current_power_kw=machine["current_power_kw"],
            data_interval_seconds=machine["data_interval_seconds"],
            readings_generated=machine["readings_generated"],
            last_reading_time=machine["last_reading_time"],
            anomaly_active=machine["anomaly_active"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get machine status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get machine status: {str(e)}"
        )

# ============================================================================
# Anomaly Testing Endpoints
# ============================================================================

@router.post("/machines/{machine_id}/anomaly", response_model=MessageResponse)
async def inject_anomaly(machine_id: str, request: AnomalyInjectionRequest):
    """
    Inject an anomaly into a specific machine for testing
    
    **Path Parameters:**
    - `machine_id`: UUID of the machine
    
    **Request Body:**
    - `anomaly_type`: Type of anomaly (e.g., "leak", "efficiency_loss", "bearing_fault")
    - `duration_seconds`: How long the anomaly should last (10-3600 seconds)
    - `severity`: Severity multiplier (1.0-5.0)
    
    **Anomaly Types by Machine:**
    - **Compressor**: leak, efficiency_loss, bearing_fault
    - **HVAC**: refrigerant_leak, dirty_coils, compressor_fault
    - **Motor**: bearing_wear, belt_slip, overload
    - **Pump**: seal_leak, pump_wear, valve_fault
    - **Injection Molding**: heater_fault, cooling_insufficient, hydraulic_leak
    
    **Example:**
    ```json
    {
        "anomaly_type": "leak",
        "duration_seconds": 300,
        "severity": 1.5
    }
    ```
    
    **Returns:**
    - Success message with anomaly details
    """
    try:
        # Validate that request.machine_id matches path machine_id
        if request.machine_id != machine_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Machine ID in request body must match path parameter"
            )
        
        # Inject anomaly
        await simulator_manager.inject_anomaly(
            machine_id=machine_id,
            anomaly_type=request.anomaly_type,
            duration_seconds=request.duration_seconds,
            severity=request.severity
        )
        
        logger.info(
            f"Anomaly injected: {request.anomaly_type} on {machine_id} "
            f"(duration: {request.duration_seconds}s, severity: {request.severity})"
        )
        
        return MessageResponse(
            message=f"Anomaly '{request.anomaly_type}' injected successfully",
            success=True,
            data={
                "machine_id": machine_id,
                "anomaly_type": request.anomaly_type,
                "duration_seconds": request.duration_seconds,
                "severity": request.severity
            }
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to inject anomaly: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to inject anomaly: {str(e)}"
        )


@router.delete("/machines/{machine_id}/anomaly", response_model=MessageResponse)
async def clear_anomaly(machine_id: str):
    """
    Clear any active anomaly on a specific machine
    
    **Path Parameters:**
    - `machine_id`: UUID of the machine
    
    **Returns:**
    - Success message
    """
    try:
        machine = simulator_manager.get_machine_status(machine_id)
        
        if not machine:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Machine {machine_id} not found"
            )
        
        # Get the machine object and clear anomaly
        machine_obj = simulator_manager.machines.get(machine_id)
        if machine_obj:
            machine_obj.clear_anomaly()
        
        logger.info(f"Anomaly cleared on machine {machine_id}")
        
        return MessageResponse(
            message="Anomaly cleared successfully",
            success=True,
            data={"machine_id": machine_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear anomaly: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear anomaly: {str(e)}"
        )

# ============================================================================
# Information Endpoints
# ============================================================================

@router.get("/info", response_model=MessageResponse)
async def get_info():
    """
    Get simulator information and capabilities
    
    Returns information about:
    - Service name and version
    - Available machine types
    - Configuration options
    - API endpoints
    
    **Returns:**
    - Simulator information
    """
    return MessageResponse(
        message="EnMS Factory Simulator Information",
        success=True,
        data={
            "service": settings.SERVICE_NAME,
            "version": settings.SERVICE_VERSION,
            "machine_types": [
                "compressor",
                "hvac",
                "motor",
                "pump",
                "injection_molding"
            ],
            "data_intervals": {
                "compressor": f"{settings.COMPRESSOR_INTERVAL}s",
                "hvac": f"{settings.HVAC_INTERVAL}s",
                "motor": f"{settings.MOTOR_INTERVAL}s",
                "pump": f"{settings.PUMP_INTERVAL}s",
                "injection_molding": f"{settings.INJECTION_MOLDING_INTERVAL}s"
            },
            "endpoints": {
                "start": "POST /simulator/start",
                "stop": "POST /simulator/stop",
                "status": "GET /simulator/status",
                "machines": "GET /simulator/machines",
                "machine_detail": "GET /simulator/machines/{id}",
                "inject_anomaly": "POST /simulator/machines/{id}/anomaly",
                "clear_anomaly": "DELETE /simulator/machines/{id}/anomaly",
                "update_config": "PUT /simulator/config"
            }
        }
    )