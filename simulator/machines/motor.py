"""
EnMS - Factory Simulator Service
Motor/Conveyor Simulator
"""

import numpy as np
from datetime import datetime
from typing import Dict, Any
from models import MachineType, OperatingMode
from machines.base_machine import BaseMachineSimulator


class MotorSimulator(BaseMachineSimulator):
    """
    Electric Motor / Conveyor Belt Simulator
    
    Characteristics:
    - Medium-frequency data (10-second intervals)
    - Variable Frequency Drive (VFD) controlled
    - Speed varies with production demand
    - Load-dependent power consumption
    - Production count linked to conveyor operation
    """
    
    def __init__(self, machine_id: str, machine_name: str, rated_power_kw: float, mqtt_topic: str):
        super().__init__(
            machine_id=machine_id,
            machine_name=machine_name,
            machine_type=MachineType.MOTOR,
            rated_power_kw=rated_power_kw,
            data_interval_seconds=10,  # 10-second intervals
            mqtt_topic=mqtt_topic
        )
        
        # Motor-specific parameters
        self.current_speed_percent = 0.0
        self.target_speed_percent = 75.0
        self.min_speed_percent = 20.0
        self.max_speed_percent = 100.0
        
        # Conveyor parameters
        self.conveyor_speed_m_per_min = 0.0
        self.max_conveyor_speed = 30.0  # meters per minute
        self.items_per_meter = 2  # Items on conveyor per meter
        
        # Load
        self.current_load_percent = 0.0
        
    def generate_energy_reading(self, timestamp: datetime) -> Dict[str, Any]:
        """Generate energy reading for motor"""
        if not self.is_running:
            self.current_power_kw = 0.0
            self.current_speed_percent = 0.0
            energy_increment = 0.0
        else:
            # Check anomaly expiry
            self.check_anomaly_expiry()
            
            # Get shift factor (production demand)
            shift_factor = self.get_shift_factor(timestamp)
            
            # Target speed based on shift
            self.target_speed_percent = shift_factor * 80 + 20  # 20-100%
            
            # Gradual speed ramp (VFD acceleration/deceleration)
            speed_error = self.target_speed_percent - self.current_speed_percent
            ramp_rate = 5.0  # percent per interval
            if abs(speed_error) > ramp_rate:
                self.current_speed_percent += np.sign(speed_error) * ramp_rate
            else:
                self.current_speed_percent = self.target_speed_percent
            
            # Add some speed variation
            self.current_speed_percent += np.random.uniform(-2, 2)
            self.current_speed_percent = np.clip(
                self.current_speed_percent,
                self.min_speed_percent,
                self.max_speed_percent
            )
            
            # Conveyor speed
            self.conveyor_speed_m_per_min = (self.current_speed_percent / 100) * self.max_conveyor_speed
            
            # Load varies with speed and belt tension
            base_load = 40  # Base mechanical load
            speed_load = (self.current_speed_percent / 100) * 60
            self.current_load_percent = base_load + speed_load
            self.current_load_percent += np.random.uniform(-5, 5)
            self.current_load_percent = np.clip(self.current_load_percent, 0, 100)
            
            # Power calculation
            # Motor power = (Speed/100)^3 × Rated Power × Load Factor
            # Cubic relationship due to fan/pump laws (for VFD)
            speed_factor = (self.current_speed_percent / 100) ** 2.5
            load_factor = self.current_load_percent / 100
            self.current_power_kw = self.rated_power_kw * speed_factor * load_factor
            
            # Motor efficiency (better at higher loads)
            if self.current_load_percent > 70:
                efficiency = 0.95
            elif self.current_load_percent > 40:
                efficiency = 0.92
            else:
                efficiency = 0.85
            
            self.current_power_kw /= efficiency
            
            # Apply anomaly if active
            if self.anomaly_active:
                if self.anomaly_type == "bearing_wear":
                    # Increased friction = higher power
                    self.current_power_kw *= 1.2
                elif self.anomaly_type == "belt_slip":
                    # Power consumption high but output low
                    self.current_power_kw *= 1.15
                    self.conveyor_speed_m_per_min *= 0.85
                elif self.anomaly_type == "overload":
                    # Excessive load
                    self.current_power_kw *= self.anomaly_multiplier
            
            # Add noise
            self.current_power_kw = self.add_noise(self.current_power_kw, 3.0)
            
            # Ensure within rated power
            self.current_power_kw = min(self.current_power_kw, self.rated_power_kw * 1.1)
            
            # Energy increment
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
        """Generate production data for motor/conveyor"""
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
        
        # Production count based on conveyor speed
        # Items moved = (speed m/min × items per meter × interval seconds / 60)
        items_moved = int(
            self.conveyor_speed_m_per_min * 
            self.items_per_meter * 
            (self.data_interval_seconds / 60)
        )
        
        self.total_production_count += items_moved
        
        # Quality - occasional defects
        defect_rate = 0.02  # 2% defect rate
        bad_units = int(items_moved * defect_rate)
        good_units = items_moved - bad_units
        
        # Throughput per hour
        throughput = (self.conveyor_speed_m_per_min * self.items_per_meter * 60)
        
        # Operating mode
        if self.current_speed_percent < 25:
            mode = OperatingMode.IDLE
        else:
            mode = OperatingMode.RUNNING
        
        return {
            "time": timestamp.isoformat(),
            "machine_id": self.machine_id,
            "production_count": items_moved,
            "production_count_good": good_units,
            "production_count_bad": bad_units,
            "throughput_units_per_hour": round(throughput, 2),
            "operating_mode": mode.value,
            "speed_percent": round(self.current_speed_percent, 2)
        }
    
    def generate_environmental_data(self, timestamp: datetime) -> Dict[str, Any]:
        """Generate environmental data for motor"""
        if not self.is_running:
            return {
                "time": timestamp.isoformat(),
                "machine_id": self.machine_id,
                "machine_temp_c": 20.0,
                "vibration_mm_s": 0.0
            }
        
        # Motor temperature (increases with load)
        ambient_temp = 25.0
        temp_rise = (self.current_load_percent / 100) * 40  # Up to 40°C rise at full load
        machine_temp_c = ambient_temp + temp_rise + np.random.uniform(-5, 5)
        
        # Vibration (higher at high speeds or if bearing fault)
        base_vibration = 1.0 + (self.current_speed_percent / 100) * 2.0
        if self.anomaly_active and self.anomaly_type == "bearing_wear":
            base_vibration *= 4.0
        vibration_mm_s = self.add_noise(base_vibration, 15.0)
        
        return {
            "time": timestamp.isoformat(),
            "machine_id": self.machine_id,
            "machine_temp_c": round(machine_temp_c, 2),
            "vibration_mm_s": round(vibration_mm_s, 4)
        }