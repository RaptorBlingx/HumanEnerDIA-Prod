"""
EnMS - Factory Simulator Service
Base Machine Simulator
"""

import logging
import numpy as np
from abc import ABC, abstractmethod
from datetime import datetime, time
from typing import Dict, Any, Optional
from models import MachineType, OperatingMode

logger = logging.getLogger(__name__)


class BaseMachineSimulator(ABC):
    """Base class for all machine simulators"""
    
    def __init__(
        self,
        machine_id: str,
        machine_name: str,
        machine_type: MachineType,
        rated_power_kw: float,
        data_interval_seconds: int,
        mqtt_topic: str
    ):
        self.machine_id = machine_id
        self.machine_name = machine_name
        self.machine_type = machine_type
        self.rated_power_kw = rated_power_kw
        self.data_interval_seconds = data_interval_seconds
        self.mqtt_topic = mqtt_topic
        
        # State
        self.is_running = False
        self.operating_mode = OperatingMode.OFFLINE
        self.current_power_kw = 0.0
        self.readings_generated = 0
        self.last_reading_time: Optional[datetime] = None
        
        # Anomaly simulation
        self.anomaly_active = False
        self.anomaly_type: Optional[str] = None
        self.anomaly_multiplier = 1.0
        self.anomaly_start_time: Optional[datetime] = None
        self.anomaly_duration_seconds = 0
        
        # Cumulative metrics
        self.total_energy_kwh = 0.0
        self.total_production_count = 0
        
    @abstractmethod
    def generate_energy_reading(self, timestamp: datetime) -> Dict[str, Any]:
        """Generate energy reading data"""
        pass
    
    @abstractmethod
    def generate_production_data(self, timestamp: datetime) -> Dict[str, Any]:
        """Generate production data"""
        pass
    
    @abstractmethod
    def generate_environmental_data(self, timestamp: datetime) -> Dict[str, Any]:
        """Generate environmental data"""
        pass
    
    def generate_machine_status(self, timestamp: datetime) -> Dict[str, Any]:
        """Generate machine status data for MQTT publication"""
        return {
            "timestamp": timestamp.isoformat(),
            "machine_id": self.machine_id,
            "is_running": self.is_running,
            "operating_mode": self.operating_mode.value,
            "current_power_kw": round(self.current_power_kw, 3)
        }
    
    def start(self):
        """Start the machine"""
        self.is_running = True
        self.operating_mode = OperatingMode.RUNNING
        logger.info(f"{self.machine_name} started")
    
    def stop(self):
        """Stop the machine"""
        self.is_running = False
        self.operating_mode = OperatingMode.OFFLINE
        self.current_power_kw = 0.0
        logger.info(f"{self.machine_name} stopped")
    
    def inject_anomaly(self, anomaly_type: str, duration_seconds: int, severity: float):
        """Inject an anomaly for testing"""
        self.anomaly_active = True
        self.anomaly_type = anomaly_type
        self.anomaly_multiplier = severity
        self.anomaly_start_time = datetime.utcnow()
        self.anomaly_duration_seconds = duration_seconds
        logger.warning(
            f"Anomaly injected on {self.machine_name}: "
            f"{anomaly_type} (severity: {severity}, duration: {duration_seconds}s)"
        )
    
    def clear_anomaly(self):
        """Clear active anomaly"""
        if self.anomaly_active:
            logger.info(f"Anomaly cleared on {self.machine_name}")
        self.anomaly_active = False
        self.anomaly_type = None
        self.anomaly_multiplier = 1.0
        self.anomaly_start_time = None
    
    def check_anomaly_expiry(self):
        """Check if anomaly should expire"""
        if self.anomaly_active and self.anomaly_start_time:
            elapsed = (datetime.utcnow() - self.anomaly_start_time).total_seconds()
            if elapsed >= self.anomaly_duration_seconds:
                self.clear_anomaly()
    
    def get_shift_factor(self, timestamp: datetime) -> float:
        """
        Get production factor based on shift schedule
        Returns 1.0 for full production, lower values for reduced shifts
        """
        hour = timestamp.hour
        day_of_week = timestamp.weekday()  # 0=Monday, 6=Sunday
        
        # Weekend factor (Saturday=5, Sunday=6)
        if day_of_week >= 5:
            return 0.3  # 30% production on weekends
        
        # Weekday shifts
        # Shift 1: 06:00-14:00 (full production)
        if 6 <= hour < 14:
            return 1.0
        # Shift 2: 14:00-22:00 (full production)
        elif 14 <= hour < 22:
            return 1.0
        # Shift 3: 22:00-06:00 (reduced production - 50%)
        else:
            return 0.5
    
    def get_seasonal_temp_offset(self, timestamp: datetime) -> float:
        """Get outdoor temperature offset based on season"""
        month = timestamp.month
        
        # Temperature baseline: 15°C
        # Summer (June-August): +15°C
        # Winter (December-February): -10°C
        # Spring/Fall: interpolated
        
        if month in [12, 1, 2]:  # Winter
            return -10.0
        elif month in [6, 7, 8]:  # Summer
            return 15.0
        elif month in [3, 4, 5]:  # Spring
            return (month - 3) * 5.0  # Gradual increase
        else:  # Fall (9, 10, 11)
            return 15.0 - ((month - 8) * 5.0)  # Gradual decrease
    
    def add_noise(self, value: float, noise_percent: float = 3.0) -> float:
        """Add random noise to a value"""
        noise = np.random.normal(0, value * noise_percent / 100)
        return max(0, value + noise)  # Ensure non-negative
    
    def calculate_electrical_params(self, power_kw: float, voltage_v: float = 400.0) -> Dict[str, float]:
        """Calculate electrical parameters from power"""
        # Assume 3-phase power
        # P = √3 × V × I × PF
        
        power_factor = np.random.uniform(0.85, 0.95)  # Typical industrial PF
        frequency_hz = self.add_noise(50.0, 0.5)  # European standard with small variation
        
        # Calculate current: I = P / (√3 × V × PF)
        current_a = (power_kw * 1000) / (np.sqrt(3) * voltage_v * power_factor)
        
        # Add some noise
        voltage_v = self.add_noise(voltage_v, 2.0)
        current_a = self.add_noise(current_a, 2.0)
        
        return {
            "voltage_v": round(voltage_v, 2),
            "current_a": round(current_a, 2),
            "power_factor": round(power_factor, 4),
            "frequency_hz": round(frequency_hz, 2)
        }
    
    def get_state(self) -> Dict[str, Any]:
        """Get current machine state"""
        return {
            "machine_id": self.machine_id,
            "machine_name": self.machine_name,
            "machine_type": self.machine_type.value,
            "is_running": self.is_running,
            "operating_mode": self.operating_mode.value,
            "current_power_kw": self.current_power_kw,
            "data_interval_seconds": self.data_interval_seconds,
            "readings_generated": self.readings_generated,
            "last_reading_time": self.last_reading_time.isoformat() if self.last_reading_time else None,
            "anomaly_active": self.anomaly_active,
            "anomaly_type": self.anomaly_type,
            "total_energy_kwh": round(self.total_energy_kwh, 3),
            "total_production_count": self.total_production_count
        }