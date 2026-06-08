"""
EnMS - Boiler Machine Simulator
Multi-Energy: Electricity + Natural Gas + Steam

Author: EnMS Team
Date: October 27, 2024
"""

from datetime import datetime
from .base_machine import BaseMachineSimulator
from models import MachineType, OperatingMode
import random
import numpy as np
from typing import Optional, Dict, Any


class BoilerSimulator(BaseMachineSimulator):
    """
    Industrial boiler simulator with 3 energy streams:
    - INPUT: Electricity (pumps, fans, control systems) ~15% of thermal power
    - INPUT: Natural Gas (fuel for combustion) ~100% thermal capacity
    - OUTPUT: Steam (process steam) ~85% efficiency
    
    Simulates realistic industrial boiler behavior:
    - Thermal capacity ~50x electrical power (e.g., 45 kW electrical → 2250 kW thermal)
    - Natural gas: 1 m³ = 10.55 kWh thermal energy
    - Steam: 2.26 kWh/kg (latent heat at 10 bar)
    - Typical efficiency: 85%
    """
    
    def __init__(self, machine_id: str, machine_name: str, rated_power_kw: float, mqtt_topic: str):
        """
        Initialize boiler simulator.
        
        Args:
            machine_id: Unique machine identifier
            machine_name: Display name (e.g., "Boiler-1")
            rated_power_kw: Electrical power rating (pumps, fans, controls)
            mqtt_topic: Base MQTT topic for publishing
        """
        super().__init__(
            machine_id=machine_id,
            machine_name=machine_name,
            machine_type=MachineType.BOILER,
            rated_power_kw=rated_power_kw,
            data_interval_seconds=30,  # 30-second readings
            mqtt_topic=mqtt_topic
        )
        
        # Boiler-specific parameters
        # Thermal capacity adjusted for realistic factory energy balance
        # Boiler electrical (45 kW) represents auxiliary systems (pumps, fans, controls)
        # Setting to 1.5x makes total thermal ~67.5 kW, creating balanced energy mix
        # With 3 energy streams (elec + gas + steam), boiler will be ~25-35% of total energy
        self.thermal_capacity_kw = rated_power_kw * 1.5  # 1.5x electrical for balanced factory energy
        self.boiler_efficiency = 0.85  # 85% efficiency
        self.steam_pressure_bar = 10.0  # 10 bar steam pressure
        self.outdoor_temp_base_c = 15.0  # Baseline outdoor temperature
        
        # Energy conversion factors
        self.gas_energy_kwh_per_m3 = 10.55  # 1 m³ natural gas = 10.55 kWh
        self.steam_energy_kwh_per_kg = 2.26  # 1 kg steam = 2.26 kWh (at 10 bar)
        self._snapshot_timestamp: Optional[datetime] = None
        self._snapshot_data: Optional[Dict[str, Any]] = None
        
    def _build_sensor_data(self, timestamp: datetime) -> dict:
        """
        Generate multi-energy sensor readings with PHYSICS-BASED correlations.
        
        ISO 50006 Heating Degree Day model:
        - Colder outdoor temp → higher heating load → more energy
        - Energy = base_load + heating_coefficient × (setpoint - outdoor_temp)
        
        Returns:
            Dict with electricity, natural gas, and steam measurements
        """
        # 1. OUTDOOR TEMPERATURE - Realistic seasonal/daily variation
        hour = timestamp.hour
        day_of_year = timestamp.timetuple().tm_yday
        
        # Seasonal variation: coldest in Jan (day ~15), warmest in July (day ~196)
        # Range: -5°C (winter) to +25°C (summer) with 15°C baseline
        seasonal_temp = 10.0 + 15.0 * np.sin(2 * np.pi * (day_of_year - 15) / 365)
        
        # Daily variation: coldest at 6am, warmest at 3pm (±5°C)
        daily_temp_swing = 5.0 * np.sin(2 * np.pi * (hour - 6) / 24)
        
        # Add noise (±2°C)
        outdoor_temp = seasonal_temp + daily_temp_swing + np.random.uniform(-2, 2)
        outdoor_temp = np.clip(outdoor_temp, -10, 35)  # Physical limits
        
        # 2. HEATING LOAD - ISO 50006 Heating Degree model
        # Heating setpoint: 18°C (below this, heating is needed)
        heating_setpoint = 18.0
        
        # Heating Degree Hours (HDH) - only count when outdoor < setpoint
        if outdoor_temp < heating_setpoint:
            # More heating needed when colder
            heating_factor = (heating_setpoint - outdoor_temp) / heating_setpoint
        else:
            # No heating needed when warm
            heating_factor = 0.05  # Minimum standby load
        
        # Clamp to realistic range
        heating_factor = np.clip(heating_factor, 0.05, 1.0)
        
        # 3. TIME-OF-DAY ADJUSTMENT (occupancy pattern)
        if 6 <= hour < 22:  # Daytime: process heating + space heating
            occupancy_factor = 1.0
        else:  # Nighttime: reduced load
            occupancy_factor = 0.6
        
        # 4. COMBINED LOAD FACTOR
        # base_load = heating_factor × occupancy × mode
        mode_multiplier = self._get_mode_multiplier()
        effective_load = heating_factor * occupancy_factor * mode_multiplier
        effective_load = np.clip(effective_load, 0.05, 1.0)
        
        # Add small random noise (±10%) - real systems have variability
        effective_load *= np.random.uniform(0.90, 1.10)
        effective_load = np.clip(effective_load, 0.05, 1.0)
        
        # 5. ELECTRICITY: Auxiliary systems (pumps, fans, controls)
        # Scales with thermal load
        electricity_kw = self.rated_power_kw * effective_load * random.uniform(0.90, 1.10)
        electricity_kwh = electricity_kw * (self.data_interval_seconds / 3600)
        
        # 6. NATURAL GAS: Fuel consumption (ISO 50006 energy driver)
        thermal_power_kw = self.thermal_capacity_kw * effective_load
        gas_input_kw = thermal_power_kw / self.boiler_efficiency
        gas_flow_m3h = gas_input_kw / self.gas_energy_kwh_per_m3
        gas_consumption_m3 = gas_flow_m3h * (self.data_interval_seconds / 3600)
        
        # 7. STEAM: Output product
        steam_output_kw = thermal_power_kw * self.boiler_efficiency
        steam_production_kgh = steam_output_kw / self.steam_energy_kwh_per_kg
        steam_production_kg = steam_production_kgh * (self.data_interval_seconds / 3600)
        
        # Additional process variables
        boiler_efficiency_actual = self.boiler_efficiency + random.uniform(-0.03, 0.03)
        steam_pressure = self.steam_pressure_bar + random.uniform(-0.5, 0.5)
        flue_gas_temp = 180 + random.uniform(-15, 15)  # Stack temperature
        # outdoor_temp already calculated above with physics-based seasonal/daily variation
        
        return {
            # Electricity readings (for energy_readings table)
            "power_kw": round(electricity_kw, 3),
            "energy_kwh": round(electricity_kwh, 4),
            "voltage_v": round(400 + random.uniform(-10, 10), 1),
            "current_a": round((electricity_kw * 1000) / (400 * 1.732 * 0.95), 2),
            
            # Natural gas readings
            "flow_rate_m3h": round(gas_flow_m3h, 3),
            "consumption_m3": round(gas_consumption_m3, 4),
            "pressure_bar": round(4.0 + random.uniform(-0.2, 0.2), 2),
            "calorific_value_kwh_m3": round(self.gas_energy_kwh_per_m3, 2),
            "temperature_c": round(20 + random.uniform(-2, 2), 1),
            
            # Steam readings
            "flow_rate_kg_h": round(steam_production_kgh, 2),
            "consumption_kg": round(steam_production_kg, 3),
            "steam_pressure_bar": round(steam_pressure, 2),
            "steam_temperature_c": round(184.0 + random.uniform(-3, 3), 1),  # ~184°C at 10 bar
            "enthalpy_kj_kg": round(2777 + random.uniform(-50, 50), 0),  # kJ/kg at 10 bar
            
            # Process variables
            "boiler_efficiency": round(boiler_efficiency_actual, 3),
            "flue_gas_temp_c": round(flue_gas_temp, 1),
            "outdoor_temp_c": round(outdoor_temp, 1),
            "operating_mode": self.operating_mode.value
        }

    def _generate_sensor_data(self, timestamp: Optional[datetime] = None) -> dict:
        """Return a single shared sensor snapshot for the given simulation timestamp."""
        snapshot_time = timestamp or datetime.utcnow()

        if self._snapshot_timestamp == snapshot_time and self._snapshot_data is not None:
            return dict(self._snapshot_data)

        sensor_data = self._build_sensor_data(snapshot_time)
        self._snapshot_timestamp = snapshot_time
        self._snapshot_data = sensor_data
        return dict(sensor_data)
    
    def _get_mode_multiplier(self) -> float:
        """
        Get load multiplier based on operating mode.
        
        Returns:
            Multiplier for energy consumption (0.0 to 1.0)
        """
        if self.operating_mode == OperatingMode.IDLE:
            return 0.15  # Keep-warm mode: 15% load
        elif self.operating_mode == OperatingMode.MAINTENANCE:
            return 0.05  # Shutdown: 5% load (safety systems only)
        elif self.operating_mode == OperatingMode.FAULT:
            return 0.20  # Emergency shutdown: 20% load
        elif self.operating_mode == OperatingMode.OFFLINE:
            return 0.0  # Completely off
        else:  # RUNNING
            return 1.0  # Normal operation
    
    # ========================================================================
    # Abstract Method Implementations (required by BaseMachineSimulator)
    # ========================================================================
    
    def generate_energy_reading(self, timestamp: datetime) -> dict:
        """
        Generate electricity energy reading (primary energy input).
        This implements the abstract method from BaseMachineSimulator.
        
        Returns:
            Energy reading dict with power_kw, energy_kwh, voltage, current
        """
        sensor_data = self._generate_sensor_data(timestamp)
        return {
            "timestamp": timestamp.isoformat(),
            "machine_id": self.machine_id,
            "power_kw": sensor_data["power_kw"],
            "energy_kwh": sensor_data["energy_kwh"],
            "voltage_v": sensor_data.get("voltage_v"),
            "current_a": sensor_data.get("current_a"),
            "power_factor": 0.95
        }
    
    def generate_production_data(self, timestamp: datetime) -> dict:
        """
        Generate production data (steam output as product).
        This implements the abstract method from BaseMachineSimulator.
        
        Returns:
            Production data dict with output counts/rates
            Field names MUST match Node-RED/database schema!
        """
        sensor_data = self._generate_sensor_data(timestamp)
        
        # Steam production: kg/h → convert to units appropriate for 30-second interval
        # Use flow rate (kg/h) as throughput, and accumulated kg as production count
        steam_kg_per_interval = sensor_data["consumption_kg"]
        steam_kg_per_hour = sensor_data["flow_rate_kg_h"]
        
        # Production count: cumulative kg (multiply by factor for visibility)
        # Since each interval produces ~1-5 kg, multiply by 10 for meaningful counts
        production_count = max(1, int(steam_kg_per_interval * 10))
        load_percent = min(100.0, max(0.0, (sensor_data.get("power_kw", 0.0) / self.rated_power_kw) * 100))
        
        return {
            "time": timestamp.isoformat(),
            "machine_id": self.machine_id,
            "production_count": production_count,
            "production_count_good": production_count,  # Steam quality is typically high
            "production_count_bad": 0,
            "throughput_units_per_hour": round(steam_kg_per_hour, 2),  # kg/h steam
            "operating_mode": sensor_data.get("operating_mode", "running"),
            "speed_percent": round(load_percent, 1)
        }
    
    def generate_environmental_data(self, timestamp: datetime) -> dict:
        """
        Generate environmental data (flue gas, outdoor conditions).
        This implements the abstract method from BaseMachineSimulator.
        
        Returns:
            Environmental data dict with temperatures, humidity, pressure
            Field names MUST match Node-RED/database schema for baseline training!
        """
        sensor_data = self._generate_sensor_data(timestamp)
        outdoor_temp = sensor_data.get("outdoor_temp_c", 15.0)
        
        # Machine temperature: flue gas / boiler shell temperature
        # Higher than outdoor due to combustion heat
        machine_temp = sensor_data.get("flue_gas_temp_c", 180.0)
        
        # Indoor temperature: boiler room temperature
        indoor_temp = outdoor_temp + random.uniform(5, 15)  # Warmer due to heat radiation
        
        return {
            "time": timestamp.isoformat(),
            "machine_id": self.machine_id,
            # Standard environmental fields (matching Node-RED/database schema)
            "outdoor_temp_c": round(outdoor_temp, 2),
            "indoor_temp_c": round(indoor_temp, 2),
            "machine_temp_c": round(machine_temp, 2),
            "outdoor_humidity_percent": round(60.0 + random.uniform(-10, 10), 2),
            "indoor_humidity_percent": round(50.0 + random.uniform(-10, 10), 2),
            "pressure_bar": round(sensor_data.get("steam_pressure_bar", 10.0), 2),
            "flow_rate_m3h": round(sensor_data.get("flow_rate_m3h", 0.0), 3),
            "vibration_mm_s": round(random.uniform(0.5, 2.0), 3)
        }
