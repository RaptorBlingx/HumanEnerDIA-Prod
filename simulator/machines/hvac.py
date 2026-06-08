"""
EnMS - Factory Simulator Service
HVAC System Simulator
"""

import numpy as np
from datetime import datetime
from typing import Dict, Any
from models import MachineType, OperatingMode
from machines.base_machine import BaseMachineSimulator


class HVACSimulator(BaseMachineSimulator):
    """
    HVAC (Heating, Ventilation, Air Conditioning) Simulator
    
    Characteristics:
    - Medium-frequency data (10-second intervals)
    - Temperature-dependent power consumption
    - Coefficient of Performance (COP) varies with load
    - Supply and return air temperatures
    - Outdoor temperature affects efficiency
    """
    
    def __init__(self, machine_id: str, machine_name: str, rated_power_kw: float, mqtt_topic: str):
        super().__init__(
            machine_id=machine_id,
            machine_name=machine_name,
            machine_type=MachineType.HVAC,
            rated_power_kw=rated_power_kw,
            data_interval_seconds=10,  # 10-second intervals
            mqtt_topic=mqtt_topic
        )
        
        # HVAC-specific parameters
        self.target_indoor_temp_c = 22.0
        self.current_indoor_temp_c = 22.0
        self.supply_air_temp_c = 12.0
        self.return_air_temp_c = 22.0
        
        self.target_supply_temp_c = 12.0
        self.chilled_water_supply_temp_c = 7.0
        self.chilled_water_return_temp_c = 12.0
        
        # Coefficient of Performance (cooling efficiency)
        self.current_cop = 3.5
        self.rated_cop = 4.0
        
        # Compressor stages
        self.active_stages = 0  # 0-3 stages
        self.max_stages = 3
        
    def generate_energy_reading(self, timestamp: datetime) -> Dict[str, Any]:
        """Generate energy reading for HVAC"""
        if not self.is_running:
            self.current_power_kw = 0.0
            energy_increment = 0.0
        else:
            # Check anomaly expiry
            self.check_anomaly_expiry()
            
            # Get outdoor temperature (major driver)
            outdoor_temp_c = 15.0 + self.get_seasonal_temp_offset(timestamp)
            outdoor_temp_c += np.random.uniform(-5, 5)  # Daily variation
            
            # Add diurnal variation (hotter in afternoon)
            hour = timestamp.hour
            if 12 <= hour <= 18:
                outdoor_temp_c += np.random.uniform(2, 5)
            elif 0 <= hour <= 6:
                outdoor_temp_c -= np.random.uniform(2, 4)
            
            # Get occupancy/shift factor
            shift_factor = self.get_shift_factor(timestamp)
            
            # Indoor heat load (people, equipment, solar gain)
            base_heat_load_kw = shift_factor * 80  # kW of heat to remove
            
            # Calculate required cooling capacity
            cooling_load_kw = base_heat_load_kw + (outdoor_temp_c - self.target_indoor_temp_c) * 2
            cooling_load_kw = max(0, cooling_load_kw)
            
            # Determine active compressor stages based on load
            load_fraction = cooling_load_kw / 150  # Relative to rated capacity
            self.active_stages = int(np.ceil(load_fraction * self.max_stages))
            self.active_stages = np.clip(self.active_stages, 0, self.max_stages)
            
            # COP varies with outdoor temperature and load
            # Lower COP in hot weather (less efficient)
            outdoor_temp_effect = 1.0 - ((outdoor_temp_c - 25) / 100)
            load_effect = 0.85 + (load_fraction * 0.15)  # Better COP at higher loads
            self.current_cop = self.rated_cop * outdoor_temp_effect * load_effect
            self.current_cop = np.clip(self.current_cop, 2.0, 4.5)
            
            # Power calculation: Power = Cooling Load / COP
            if self.active_stages > 0:
                self.current_power_kw = cooling_load_kw / self.current_cop
                self.current_power_kw *= (self.active_stages / self.max_stages)
            else:
                # Standby power (fans, controls)
                self.current_power_kw = self.rated_power_kw * 0.05
            
            # Apply anomaly if active
            if self.anomaly_active:
                if self.anomaly_type == "refrigerant_leak":
                    # Lower COP = higher power for same cooling
                    self.current_cop *= 0.7
                    self.current_power_kw *= 1.4
                elif self.anomaly_type == "dirty_coils":
                    # Reduced heat transfer efficiency
                    self.current_power_kw *= 1.2
                elif self.anomaly_type == "compressor_fault":
                    # Erratic power consumption
                    self.current_power_kw *= self.anomaly_multiplier
            
            # Add noise
            self.current_power_kw = self.add_noise(self.current_power_kw, 3.0)
            
            # Ensure within rated power
            self.current_power_kw = min(self.current_power_kw, self.rated_power_kw)
            
            # Energy increment
            energy_increment = self.current_power_kw * (self.data_interval_seconds / 3600)
            self.total_energy_kwh += energy_increment
            
            # Update temperatures
            self._update_temperatures(outdoor_temp_c, cooling_load_kw)
        
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
        """Generate production data for HVAC"""
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
        
        # For HVAC, "production" is tons of cooling delivered
        # 1 ton of cooling = 3.517 kW
        cooling_tons = (self.current_power_kw * self.current_cop) / 3.517
        production_units = int(cooling_tons * 10)  # Scale up for counting
        self.total_production_count += production_units
        
        # Quality is maintaining temperature setpoint
        temp_deviation = abs(self.current_indoor_temp_c - self.target_indoor_temp_c)
        if temp_deviation < 1.0:
            good_units = production_units
            bad_units = 0
        else:
            good_units = int(production_units * 0.8)
            bad_units = production_units - good_units
        
        # Speed as percentage of stages active
        speed_percent = (self.active_stages / self.max_stages) * 100
        
        return {
            "time": timestamp.isoformat(),
            "machine_id": self.machine_id,
            "production_count": production_units,
            "production_count_good": good_units,
            "production_count_bad": bad_units,
            "throughput_units_per_hour": round(cooling_tons * 360, 2),  # Per hour
            "operating_mode": OperatingMode.RUNNING.value if self.active_stages > 0 else OperatingMode.IDLE.value,
            "speed_percent": round(speed_percent, 2)
        }
    
    def generate_environmental_data(self, timestamp: datetime) -> Dict[str, Any]:
        """Generate environmental data for HVAC"""
        outdoor_temp_c = 15.0 + self.get_seasonal_temp_offset(timestamp)
        outdoor_temp_c += np.random.uniform(-5, 5)
        
        # Add diurnal variation
        hour = timestamp.hour
        if 12 <= hour <= 18:
            outdoor_temp_c += np.random.uniform(2, 5)
        elif 0 <= hour <= 6:
            outdoor_temp_c -= np.random.uniform(2, 4)
        
        # Outdoor humidity (higher in summer)
        if timestamp.month in [6, 7, 8]:
            outdoor_humidity = np.random.uniform(60, 85)
        else:
            outdoor_humidity = np.random.uniform(40, 70)
        
        # Indoor humidity (controlled)
        indoor_humidity = np.random.uniform(45, 55)
        
        if not self.is_running:
            return {
                "time": timestamp.isoformat(),
                "machine_id": self.machine_id,
                "outdoor_temp_c": round(outdoor_temp_c, 2),
                "indoor_temp_c": round(self.current_indoor_temp_c, 2),
                "outdoor_humidity_percent": round(outdoor_humidity, 2),
                "indoor_humidity_percent": round(indoor_humidity, 2),
                "supply_air_temp_c": 0.0,
                "return_air_temp_c": 0.0,
                "cop": 0.0
            }
        
        return {
            "time": timestamp.isoformat(),
            "machine_id": self.machine_id,
            "outdoor_temp_c": round(outdoor_temp_c, 2),
            "indoor_temp_c": round(self.current_indoor_temp_c, 2),
            "outdoor_humidity_percent": round(outdoor_humidity, 2),
            "indoor_humidity_percent": round(indoor_humidity, 2),
            "supply_air_temp_c": round(self.supply_air_temp_c, 2),
            "return_air_temp_c": round(self.return_air_temp_c, 2),
            "chilled_water_supply_temp_c": round(self.chilled_water_supply_temp_c, 2),
            "chilled_water_return_temp_c": round(self.chilled_water_return_temp_c, 2),
            "cop": round(self.current_cop, 2)
        }
    
    def _update_temperatures(self, outdoor_temp_c: float, cooling_load_kw: float):
        """Update HVAC temperatures based on operation"""
        if self.active_stages > 0:
            # Supply air temperature
            self.supply_air_temp_c = self.target_supply_temp_c + np.random.uniform(-1, 1)
            
            # Return air temperature (depends on indoor temp)
            self.return_air_temp_c = self.current_indoor_temp_c + np.random.uniform(-0.5, 0.5)
            
            # Indoor temperature approaches target
            temp_error = self.target_indoor_temp_c - self.current_indoor_temp_c
            self.current_indoor_temp_c += temp_error * 0.1  # Gradual adjustment
            
            # Chilled water temperatures
            self.chilled_water_supply_temp_c = 7.0 + np.random.uniform(-1, 1)
            delta_t = 5.0  # Typical chilled water delta-T
            self.chilled_water_return_temp_c = self.chilled_water_supply_temp_c + delta_t
        else:
            # No cooling, indoor temp drifts toward outdoor
            drift = (outdoor_temp_c - self.current_indoor_temp_c) * 0.01
            self.current_indoor_temp_c += drift