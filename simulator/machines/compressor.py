"""
EnMS - Factory Simulator Service
Compressor Machine Simulator
"""

import numpy as np
from datetime import datetime
from typing import Dict, Any
from models import MachineType, OperatingMode
from machines.base_machine import BaseMachineSimulator


class CompressorSimulator(BaseMachineSimulator):
    """
    Air Compressor Simulator
    
    Characteristics:
    - High-frequency data (1-second intervals)
    - Pressure control (6-8 bar typical)
    - Load/unload cycles
    - Flow rate varies with demand
    - Energy consumption tied to pressure and flow
    """
    
    def __init__(self, machine_id: str, machine_name: str, rated_power_kw: float, mqtt_topic: str):
        super().__init__(
            machine_id=machine_id,
            machine_name=machine_name,
            machine_type=MachineType.COMPRESSOR,
            rated_power_kw=rated_power_kw,
            data_interval_seconds=1,  # 1-second intervals
            mqtt_topic=mqtt_topic
        )
        
        # Compressor-specific parameters
        self.target_pressure_bar = 7.0
        self.current_pressure_bar = 7.0
        self.min_pressure_bar = 6.0
        self.max_pressure_bar = 8.0
        
        self.flow_rate_m3h = 0.0
        self.max_flow_rate_m3h = 500.0
        
        # Load/unload control
        self.is_loaded = True
        self.load_pressure_threshold = 6.5
        self.unload_pressure_threshold = 7.5
        
    def generate_energy_reading(self, timestamp: datetime) -> Dict[str, Any]:
        """Generate energy reading for compressor"""
        if not self.is_running:
            self.current_power_kw = 0.0
            energy_increment = 0.0
        else:
            # Check anomaly expiry
            self.check_anomaly_expiry()
            
            # Get shift factor
            shift_factor = self.get_shift_factor(timestamp)
            
            # Simulate demand (flow rate)
            base_demand = shift_factor * 0.7  # 70% of max at full shift
            demand_variation = np.random.uniform(0.8, 1.2)
            self.flow_rate_m3h = base_demand * demand_variation * self.max_flow_rate_m3h
            
            # Pressure control logic
            self._update_pressure_control()
            
            # Power calculation based on load state
            if self.is_loaded:
                # Loaded: 70-95% of rated power based on flow
                load_factor = 0.7 + (self.flow_rate_m3h / self.max_flow_rate_m3h) * 0.25
                self.current_power_kw = self.rated_power_kw * load_factor
            else:
                # Unloaded: 20-30% of rated power (idling)
                self.current_power_kw = self.rated_power_kw * np.random.uniform(0.20, 0.30)
            
            # Apply anomaly if active
            if self.anomaly_active:
                if self.anomaly_type == "leak":
                    # Leak causes higher power due to continuous loading
                    self.current_power_kw *= 1.3
                    self.current_pressure_bar *= 0.9  # Pressure drop
                elif self.anomaly_type == "efficiency_loss":
                    # Worn components = higher power for same output
                    self.current_power_kw *= self.anomaly_multiplier
            
            # Add noise
            self.current_power_kw = self.add_noise(self.current_power_kw, 3.0)
            
            # Energy increment (kWh) = Power (kW) × Time (hours)
            energy_increment = self.current_power_kw * (self.data_interval_seconds / 3600)
            self.total_energy_kwh += energy_increment
        
        # Calculate electrical parameters
        electrical = self.calculate_electrical_params(self.current_power_kw)
        
        # Update state
        self.readings_generated += 1
        self.last_reading_time = timestamp
        
        return {
            "time": timestamp.isoformat(),
            "machine_id": self.machine_id,
            "power_kw": round(self.current_power_kw, 3),
            "energy_kwh": round(energy_increment, 6),
            **electrical
        }
    
    def generate_production_data(self, timestamp: datetime) -> Dict[str, Any]:
        """Generate production data for compressor"""
        if not self.is_running:
            return {
                "time": timestamp.isoformat(),
                "machine_id": self.machine_id,
                "production_count": 0,
                "production_count_good": 0,
                "production_count_bad": 0,
                "throughput_units_per_hour": 0.0,
                "operating_mode": OperatingMode.OFFLINE.value,
                "speed_percent": 0.0
            }
        
        # For compressor, "production" is air delivered (m³/h)
        # We'll convert this to "units" for consistency
        production_units = int(self.flow_rate_m3h)
        self.total_production_count += production_units
        
        # Quality is typically 100% for compressors (or track moisture)
        good_units = production_units
        bad_units = 0
        
        # Speed as percentage of rated flow
        speed_percent = (self.flow_rate_m3h / self.max_flow_rate_m3h) * 100
        
        return {
            "time": timestamp.isoformat(),
            "machine_id": self.machine_id,
            "production_count": production_units,
            "production_count_good": good_units,
            "production_count_bad": bad_units,
            "throughput_units_per_hour": round(self.flow_rate_m3h, 2),
            "operating_mode": OperatingMode.RUNNING.value if self.is_loaded else OperatingMode.IDLE.value,
            "speed_percent": round(speed_percent, 2)
        }
    
    def generate_environmental_data(self, timestamp: datetime) -> Dict[str, Any]:
        """Generate environmental data for compressor"""
        if not self.is_running:
            return {
                "time": timestamp.isoformat(),
                "machine_id": self.machine_id,
                "pressure_bar": 0.0,
                "flow_rate_m3h": 0.0
            }
        
        # Outdoor temperature (for cooler efficiency)
        outdoor_temp_c = 15.0 + self.get_seasonal_temp_offset(timestamp)
        outdoor_temp_c += np.random.uniform(-5, 5)  # Daily variation
        
        # Machine temperature (higher when loaded)
        if self.is_loaded:
            machine_temp_c = outdoor_temp_c + np.random.uniform(30, 50)
        else:
            machine_temp_c = outdoor_temp_c + np.random.uniform(10, 20)
        
        # Vibration (higher when loaded or if anomaly)
        base_vibration = 2.0 if self.is_loaded else 0.5
        if self.anomaly_active and self.anomaly_type == "bearing_fault":
            base_vibration *= 3.0
        vibration_mm_s = self.add_noise(base_vibration, 20.0)
        
        return {
            "time": timestamp.isoformat(),
            "machine_id": self.machine_id,
            "outdoor_temp_c": round(outdoor_temp_c, 2),
            "machine_temp_c": round(machine_temp_c, 2),
            "pressure_bar": round(self.current_pressure_bar, 3),
            "flow_rate_m3h": round(self.flow_rate_m3h, 3),
            "vibration_mm_s": round(vibration_mm_s, 4)
        }
    
    def _update_pressure_control(self):
        """Simulate pressure control logic (load/unload)"""
        # Pressure drops when delivering air
        if self.is_loaded:
            pressure_drop_rate = self.flow_rate_m3h / 10000  # bar per interval
            self.current_pressure_bar -= pressure_drop_rate
            
            # Unload if pressure drops too low
            if self.current_pressure_bar < self.load_pressure_threshold:
                self.is_loaded = True
        else:
            # Pressure builds when unloaded
            pressure_build_rate = 0.1  # bar per interval
            self.current_pressure_bar += pressure_build_rate
            
            # Load if pressure exceeds threshold
            if self.current_pressure_bar > self.unload_pressure_threshold:
                self.is_loaded = False
        
        # Clamp pressure to physical limits
        self.current_pressure_bar = np.clip(
            self.current_pressure_bar,
            self.min_pressure_bar,
            self.max_pressure_bar
        )