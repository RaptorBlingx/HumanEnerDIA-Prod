"""
EnMS - Factory Simulator Service
Injection Molding Machine Simulator
"""

import numpy as np
from datetime import datetime
from typing import Dict, Any
from models import MachineType, OperatingMode
from machines.base_machine import BaseMachineSimulator


class InjectionMoldingSimulator(BaseMachineSimulator):
    """
    Injection Molding Machine Simulator
    
    Characteristics:
    - Low-frequency data (30-second intervals)
    - Complex cycle: heating → injection → cooling → ejection
    - High power during heating and injection
    - Material and mold dependent
    - Cycle time: 60-180 seconds typical
    """
    
    def __init__(self, machine_id: str, machine_name: str, rated_power_kw: float, mqtt_topic: str):
        super().__init__(
            machine_id=machine_id,
            machine_name=machine_name,
            machine_type=MachineType.INJECTION_MOLDING,
            rated_power_kw=rated_power_kw,
            data_interval_seconds=30,  # 30-second intervals
            mqtt_topic=mqtt_topic
        )
        
        # Machine-specific parameters
        self.barrel_temp_c = 0.0
        self.target_barrel_temp_c = 220.0  # For PP/PE plastics
        self.mold_temp_c = 40.0
        self.target_mold_temp_c = 50.0
        
        # Cycle state
        self.cycle_phase = "idle"  # idle, heating, injection, cooling, ejection
        self.cycle_count = 0
        self.time_in_phase = 0
        self.part_weight_g = 0.0
        
        # Cycle timing (in 30-second intervals)
        self.heating_duration = 2   # 60 seconds
        self.injection_duration = 1  # 30 seconds
        self.cooling_duration = 3    # 90 seconds
        self.ejection_duration = 1   # 30 seconds
        
        # Material properties
        self.material_type = "PP"  # Polypropylene
        self.shot_size_g = np.random.uniform(80, 150)
        
    def generate_energy_reading(self, timestamp: datetime) -> Dict[str, Any]:
        """Generate energy reading for injection molding"""
        if not self.is_running:
            self.current_power_kw = 0.0
            self.cycle_phase = "idle"
            self.barrel_temp_c = 0.0
            energy_increment = 0.0
        else:
            # Check anomaly expiry
            self.check_anomaly_expiry()
            
            # Get shift factor (production demand)
            shift_factor = self.get_shift_factor(timestamp)
            
            # Determine if we should start a cycle
            if self.cycle_phase == "idle" and np.random.random() < (shift_factor * 0.7):
                self._start_cycle()
            
            # Update cycle state
            self._update_cycle()
            
            # Power calculation based on cycle phase
            if self.cycle_phase == "heating":
                # High power for barrel heaters and hydraulics
                heating_power = self.rated_power_kw * 0.70
                hydraulic_power = self.rated_power_kw * 0.15
                self.current_power_kw = heating_power + hydraulic_power
                
                # More power if barrel is cold
                temp_factor = 1.0 + (self.target_barrel_temp_c - self.barrel_temp_c) / 100
                self.current_power_kw *= temp_factor
            
            elif self.cycle_phase == "injection":
                # Very high power during injection (hydraulic + screw)
                self.current_power_kw = self.rated_power_kw * 0.95
            
            elif self.cycle_phase == "cooling":
                # Moderate power for cooling system and holding pressure
                cooling_power = self.rated_power_kw * 0.25
                holding_power = self.rated_power_kw * 0.10
                self.current_power_kw = cooling_power + holding_power
            
            elif self.cycle_phase == "ejection":
                # Low power for ejection mechanism
                self.current_power_kw = self.rated_power_kw * 0.15
            
            else:  # idle
                # Standby - maintain barrel temperature
                self.current_power_kw = self.rated_power_kw * 0.12
            
            # Apply anomaly if active
            if self.anomaly_active:
                if self.anomaly_type == "heater_fault":
                    # One heater zone failed = longer heating time = more energy
                    if self.cycle_phase == "heating":
                        self.current_power_kw *= 1.4
                elif self.anomaly_type == "cooling_insufficient":
                    # Poor cooling = longer cycle = more energy
                    if self.cycle_phase == "cooling":
                        self.current_power_kw *= 1.2
                elif self.anomaly_type == "hydraulic_leak":
                    # Pressure loss = pump runs more
                    self.current_power_kw *= 1.25
            
            # Add noise
            self.current_power_kw = self.add_noise(self.current_power_kw, 4.0)
            
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
        """Generate production data for injection molding"""
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
        
        # Production count = completed parts
        production_units = 0
        good_units = 0
        bad_units = 0
        
        if self.cycle_phase == "ejection" and self.time_in_phase == self.ejection_duration - 1:
            # Part completed
            production_units = 1
            self.total_production_count += 1
            
            # Quality check
            # Bad parts if temperature not in spec or cycle issues
            temp_in_spec = (self.target_barrel_temp_c * 0.95 <= self.barrel_temp_c <= self.target_barrel_temp_c * 1.05)
            
            if temp_in_spec and not self.anomaly_active:
                # 98% good parts normally
                if np.random.random() < 0.98:
                    good_units = 1
                else:
                    bad_units = 1
            else:
                # 80% good parts with issues
                if np.random.random() < 0.80:
                    good_units = 1
                else:
                    bad_units = 1
        
        # Throughput (parts per hour)
        cycle_time_seconds = (
            self.heating_duration + 
            self.injection_duration + 
            self.cooling_duration + 
            self.ejection_duration
        ) * self.data_interval_seconds
        
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
            "recipe_id": f"mold_{self.material_type}_{int(self.shot_size_g)}"
        }
    
    def generate_environmental_data(self, timestamp: datetime) -> Dict[str, Any]:
        """Generate environmental data for injection molding"""
        if not self.is_running:
            return {
                "time": timestamp.isoformat(),
                "machine_id": self.machine_id,
                "machine_temp_c": 20.0
            }
        
        # Ambient factory temperature
        ambient_temp = 25.0
        
        # Machine area temperature (hot from barrel and mold)
        machine_area_temp = ambient_temp + 15.0 + np.random.uniform(-3, 3)
        
        return {
            "time": timestamp.isoformat(),
            "machine_id": self.machine_id,
            "indoor_temp_c": round(machine_area_temp, 2),
            "machine_temp_c": round(self.barrel_temp_c, 2)
        }
    
    def _start_cycle(self):
        """Start a new molding cycle"""
        self.cycle_phase = "heating"
        self.time_in_phase = 0
        self.cycle_count += 1
        
        # Randomize shot size slightly
        self.shot_size_g = np.random.uniform(80, 150)
        self.part_weight_g = 0.0
    
    def _update_cycle(self):
        """Update molding cycle state machine"""
        self.time_in_phase += 1
        
        if self.cycle_phase == "heating":
            # Heat barrel to target temperature
            if self.barrel_temp_c < self.target_barrel_temp_c:
                temp_increment = (self.target_barrel_temp_c - self.barrel_temp_c) / self.heating_duration
                self.barrel_temp_c += temp_increment
            
            # Add some temperature fluctuation
            self.barrel_temp_c += np.random.uniform(-2, 2)
            
            # Transition to injection when heated and time elapsed
            if self.time_in_phase >= self.heating_duration:
                self.cycle_phase = "injection"
                self.time_in_phase = 0
        
        elif self.cycle_phase == "injection":
            # Maintain barrel temperature during injection
            self.barrel_temp_c += np.random.uniform(-1, 1)
            
            # Transition to cooling
            if self.time_in_phase >= self.injection_duration:
                self.cycle_phase = "cooling"
                self.time_in_phase = 0
                self.part_weight_g = self.shot_size_g  # Part formed
        
        elif self.cycle_phase == "cooling":
            # Barrel temperature drops slightly
            self.barrel_temp_c -= 2.0
            
            # Mold temperature (cooling)
            temp_diff = self.mold_temp_c - self.target_mold_temp_c
            self.mold_temp_c -= temp_diff * 0.3
            
            # Transition to ejection
            if self.time_in_phase >= self.cooling_duration:
                self.cycle_phase = "ejection"
                self.time_in_phase = 0
        
        elif self.cycle_phase == "ejection":
            # Eject part
            # Transition to idle
            if self.time_in_phase >= self.ejection_duration:
                self.cycle_phase = "idle"
                self.time_in_phase = 0
        
        # Clamp temperatures
        self.barrel_temp_c = np.clip(self.barrel_temp_c, 0, 300)
        self.mold_temp_c = np.clip(self.mold_temp_c, 20, 100)