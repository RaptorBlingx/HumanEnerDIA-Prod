"""
EnMS - Factory Simulator Service
Hydraulic Pump Simulator
"""

import numpy as np
from datetime import datetime
from typing import Dict, Any
from models import MachineType, OperatingMode
from machines.base_machine import BaseMachineSimulator


class HydraulicPumpSimulator(BaseMachineSimulator):
    """
    Hydraulic Pump Simulator
    
    Characteristics:
    - Low-frequency data (30-second intervals)
    - Pressure-based operation
    - Cycle-based (build pressure, hold, release)
    - Linked to press/forming operations
    - High power during pressure build, lower during hold
    """
    
    def __init__(self, machine_id: str, machine_name: str, rated_power_kw: float, mqtt_topic: str):
        super().__init__(
            machine_id=machine_id,
            machine_name=machine_name,
            machine_type=MachineType.PUMP,
            rated_power_kw=rated_power_kw,
            data_interval_seconds=30,  # 30-second intervals
            mqtt_topic=mqtt_topic
        )
        
        # Pump-specific parameters
        self.target_pressure_bar = 180.0
        self.current_pressure_bar = 0.0
        self.min_pressure_bar = 0.0
        self.max_pressure_bar = 200.0
        
        # Cycle state
        self.cycle_phase = "idle"  # idle, build, hold, release
        self.cycle_count = 0
        self.time_in_phase = 0
        
        # Cycle timing (in intervals)
        self.build_duration = 2  # 2 intervals = 60 seconds
        self.hold_duration = 3   # 3 intervals = 90 seconds
        self.release_duration = 1  # 1 interval = 30 seconds
        
    def generate_energy_reading(self, timestamp: datetime) -> Dict[str, Any]:
        """Generate energy reading for hydraulic pump"""
        if not self.is_running:
            self.current_power_kw = 0.0
            self.current_pressure_bar = 0.0
            self.cycle_phase = "idle"
            energy_increment = 0.0
        else:
            # Check anomaly expiry
            self.check_anomaly_expiry()
            
            # Get shift factor (production demand)
            shift_factor = self.get_shift_factor(timestamp)
            
            # Determine if we should be in a cycle
            # Random cycle initiation based on shift factor
            if self.cycle_phase == "idle" and np.random.random() < (shift_factor * 0.6):
                self._start_cycle()
            
            # Update cycle state
            self._update_cycle()
            
            # Power calculation based on cycle phase
            if self.cycle_phase == "build":
                # High power during pressure build
                load_factor = 0.85 + (self.current_pressure_bar / self.max_pressure_bar) * 0.15
                self.current_power_kw = self.rated_power_kw * load_factor
            
            elif self.cycle_phase == "hold":
                # Moderate power to maintain pressure
                self.current_power_kw = self.rated_power_kw * 0.30
            
            elif self.cycle_phase == "release":
                # Low power during release
                self.current_power_kw = self.rated_power_kw * 0.15
            
            else:  # idle
                # Standby power
                self.current_power_kw = self.rated_power_kw * 0.05
            
            # Apply anomaly if active
            if self.anomaly_active:
                if self.anomaly_type == "seal_leak":
                    # Pressure loss = more power to maintain
                    self.current_power_kw *= 1.3
                    self.current_pressure_bar *= 0.9
                elif self.anomaly_type == "pump_wear":
                    # Lower efficiency
                    self.current_power_kw *= 1.2
                elif self.anomaly_type == "valve_fault":
                    # Erratic pressure and power
                    self.current_power_kw *= self.anomaly_multiplier
            
            # Add noise
            self.current_power_kw = self.add_noise(self.current_power_kw, 4.0)
            
            # Ensure within rated power
            self.current_power_kw = min(self.current_power_kw, self.rated_power_kw * 1.05)
            
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
        """Generate production data for hydraulic pump"""
        if not self.is_running:
            return {
                "time": timestamp.isoformat(),
                "machine_id": self.machine_id,
                "production_count": 0,
                "production_count_good": 0,
                "production_count_bad": 0,
                "throughput_units_per_hour": 0.0,
                "operating_mode": OperatingMode.OFFLINE.value
            }
        
        # Production count = completed cycles
        production_units = 0
        if self.cycle_phase == "release" and self.time_in_phase == self.release_duration - 1:
            # Cycle completing
            production_units = 1
            self.total_production_count += 1
        
        # Quality check (pressure reached target)
        if production_units > 0:
            if self.current_pressure_bar >= self.target_pressure_bar * 0.95:
                good_units = 1
                bad_units = 0
            else:
                good_units = 0
                bad_units = 1
        else:
            good_units = 0
            bad_units = 0
        
        # Throughput (cycles per hour)
        cycle_time_seconds = (self.build_duration + self.hold_duration + self.release_duration) * self.data_interval_seconds
        throughput = 3600 / cycle_time_seconds if cycle_time_seconds > 0 else 0
        
        # Operating mode
        if self.cycle_phase == "idle":
            mode = OperatingMode.IDLE
        else:
            mode = OperatingMode.RUNNING
        
        return {
            "time": timestamp.isoformat(),
            "machine_id": self.machine_id,
            "production_count": production_units,
            "production_count_good": good_units,
            "production_count_bad": bad_units,
            "throughput_units_per_hour": round(throughput, 2),
            "operating_mode": mode.value,
            "recipe_id": f"press_cycle_{self.cycle_count}"
        }
    
    def generate_environmental_data(self, timestamp: datetime) -> Dict[str, Any]:
        """Generate environmental data for hydraulic pump"""
        if not self.is_running:
            return {
                "time": timestamp.isoformat(),
                "machine_id": self.machine_id,
                "pressure_bar": 0.0,
                "machine_temp_c": 20.0
            }
        
        # Hydraulic fluid temperature (increases during operation)
        ambient_temp = 25.0
        operating_temp_rise = 30.0 if self.cycle_phase != "idle" else 10.0
        machine_temp_c = ambient_temp + operating_temp_rise + np.random.uniform(-5, 5)
        
        # High temperature if anomaly (overheating)
        if self.anomaly_active and self.anomaly_type == "overheating":
            machine_temp_c += 20.0
        
        return {
            "time": timestamp.isoformat(),
            "machine_id": self.machine_id,
            "pressure_bar": round(self.current_pressure_bar, 3),
            "machine_temp_c": round(machine_temp_c, 2)
        }
    
    def _start_cycle(self):
        """Start a new pressure cycle"""
        self.cycle_phase = "build"
        self.time_in_phase = 0
        self.cycle_count += 1
        self.current_pressure_bar = 0.0
    
    def _update_cycle(self):
        """Update cycle state machine"""
        self.time_in_phase += 1
        
        if self.cycle_phase == "build":
            # Build pressure
            pressure_increment = self.target_pressure_bar / self.build_duration
            self.current_pressure_bar += pressure_increment
            self.current_pressure_bar = min(self.current_pressure_bar, self.max_pressure_bar)
            
            # Transition to hold
            if self.time_in_phase >= self.build_duration:
                self.cycle_phase = "hold"
                self.time_in_phase = 0
        
        elif self.cycle_phase == "hold":
            # Maintain pressure with small fluctuations
            self.current_pressure_bar += np.random.uniform(-2, 2)
            self.current_pressure_bar = np.clip(
                self.current_pressure_bar,
                self.target_pressure_bar * 0.95,
                self.target_pressure_bar * 1.05
            )
            
            # Transition to release
            if self.time_in_phase >= self.hold_duration:
                self.cycle_phase = "release"
                self.time_in_phase = 0
        
        elif self.cycle_phase == "release":
            # Release pressure
            pressure_decrement = self.current_pressure_bar / self.release_duration
            self.current_pressure_bar -= pressure_decrement
            self.current_pressure_bar = max(self.current_pressure_bar, 0.0)
            
            # Transition to idle
            if self.time_in_phase >= self.release_duration:
                self.cycle_phase = "idle"
                self.time_in_phase = 0
                self.current_pressure_bar = 0.0