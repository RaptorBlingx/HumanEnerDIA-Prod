"""
EnMS - Factory Simulator Service
Data Models
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum


class MachineType(str, Enum):
    """Machine type enumeration"""
    COMPRESSOR = "compressor"
    HVAC = "hvac"
    MOTOR = "motor"
    PUMP = "pump"
    INJECTION_MOLDING = "injection_molding"
    BOILER = "boiler"


class OperatingMode(str, Enum):
    """Operating mode enumeration"""
    IDLE = "idle"
    RUNNING = "running"
    MAINTENANCE = "maintenance"
    FAULT = "fault"
    OFFLINE = "offline"


class SimulatorStatus(str, Enum):
    """Simulator status"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


# ============================================================================
# Request/Response Models
# ============================================================================

class SimulatorStartRequest(BaseModel):
    """Request to start simulator"""
    factory_ids: Optional[list[str]] = None
    machine_ids: Optional[list[str]] = None


class SimulatorStopRequest(BaseModel):
    """Request to stop simulator"""
    factory_ids: Optional[list[str]] = None
    machine_ids: Optional[list[str]] = None


class SimulatorConfigUpdate(BaseModel):
    """Update simulator configuration"""
    enable_anomalies: Optional[bool] = None
    anomaly_probability: Optional[float] = Field(None, ge=0.0, le=1.0)
    weekend_production_factor: Optional[float] = Field(None, ge=0.0, le=1.0)


class AnomalyInjectionRequest(BaseModel):
    """Request to inject an anomaly"""
    machine_id: str
    anomaly_type: str
    duration_seconds: int = Field(300, ge=10, le=3600)
    severity: float = Field(1.5, ge=1.0, le=5.0)


# ============================================================================
# Machine Data Models
# ============================================================================

class EnergyReading(BaseModel):
    """Energy reading data"""
    time: datetime
    machine_id: str
    power_kw: float
    energy_kwh: float
    voltage_v: Optional[float] = None
    current_a: Optional[float] = None
    power_factor: Optional[float] = None
    frequency_hz: Optional[float] = None


class ProductionData(BaseModel):
    """Production data"""
    time: datetime
    machine_id: str
    production_count: int
    production_count_good: int
    production_count_bad: int
    throughput_units_per_hour: float
    operating_mode: OperatingMode
    speed_percent: Optional[float] = None


class EnvironmentalData(BaseModel):
    """Environmental data"""
    time: datetime
    machine_id: str
    outdoor_temp_c: Optional[float] = None
    indoor_temp_c: Optional[float] = None
    machine_temp_c: Optional[float] = None
    outdoor_humidity_percent: Optional[float] = None
    indoor_humidity_percent: Optional[float] = None
    pressure_bar: Optional[float] = None
    flow_rate_m3h: Optional[float] = None
    supply_air_temp_c: Optional[float] = None
    return_air_temp_c: Optional[float] = None
    cop: Optional[float] = None
    vibration_mm_s: Optional[float] = None


# ============================================================================
# Machine State Models
# ============================================================================

class MachineState(BaseModel):
    """Current state of a machine"""
    machine_id: str
    machine_name: str
    machine_type: MachineType
    is_running: bool
    operating_mode: OperatingMode
    current_power_kw: float
    data_interval_seconds: int
    last_reading_time: Optional[datetime] = None
    readings_generated: int = 0
    anomaly_active: bool = False
    anomaly_type: Optional[str] = None


# ============================================================================
# Response Models
# ============================================================================

class SimulatorStatusResponse(BaseModel):
    """Simulator status response"""
    status: SimulatorStatus
    uptime_seconds: float
    factories_count: int
    machines_count: int
    running_machines: int
    total_readings_generated: int
    mqtt_connected: bool
    mqtt_messages_published: int
    configuration: Dict[str, Any]


class MachineStatusResponse(BaseModel):
    """Machine status response"""
    machine_id: str
    machine_name: str
    machine_type: MachineType
    is_running: bool
    operating_mode: OperatingMode
    current_power_kw: float
    data_interval_seconds: int
    readings_generated: int
    last_reading_time: Optional[datetime]
    anomaly_active: bool


class HealthCheckResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    version: str
    timestamp: datetime
    mqtt_connected: bool
    database_connected: bool


class MessageResponse(BaseModel):
    """Generic message response"""
    message: str
    success: bool
    data: Optional[Dict[str, Any]] = None