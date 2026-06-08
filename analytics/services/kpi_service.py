"""
EnMS Analytics Service - KPI Service
=====================================
Business logic for KPI calculations using database functions.

Author: EnMS Team
Phase: 3 - Analytics & ML
"""

from typing import Dict, Any, Optional
from datetime import datetime
from uuid import UUID
import logging

from database import db, get_machine_by_id

logger = logging.getLogger(__name__)


class KPIService:
    """Service for calculating Key Performance Indicators."""
    
    @staticmethod
    async def calculate_sec(
        machine_id: UUID,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """
        Calculate Specific Energy Consumption (SEC).
        
        Formula: SEC = Total Energy (kWh) / Total Production (units)
        
        Args:
            machine_id: Machine UUID
            start_time: Start of calculation period
            end_time: End of calculation period
            
        Returns:
            SEC calculation results
        """
        # Validate machine
        machine = await get_machine_by_id(machine_id)
        if not machine:
            raise ValueError(f"Machine not found: {machine_id}")
        
        # Call database function
        query = "SELECT * FROM calculate_sec($1, $2, $3)"
        
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(query, machine_id, start_time, end_time)
            
            if not row:
                raise ValueError("Unable to calculate SEC - no data available")
            
            result = dict(row)
            result['machine_name'] = machine['name']
            result['machine_type'] = machine['type']
            
            return result
    
    @staticmethod
    async def calculate_peak_demand(
        machine_id: UUID,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """
        Calculate Peak Demand.
        
        Formula: Peak = MAX(power_kw) over 15-minute rolling window
        
        Args:
            machine_id: Machine UUID
            start_time: Start of calculation period
            end_time: End of calculation period
            
        Returns:
            Peak demand results
        """
        machine = await get_machine_by_id(machine_id)
        if not machine:
            raise ValueError(f"Machine not found: {machine_id}")
        
        query = "SELECT * FROM calculate_peak_demand($1, $2, $3)"
        
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(query, machine_id, start_time, end_time)
            
            if not row:
                raise ValueError("Unable to calculate peak demand - no data available")
            
            result = dict(row)
            result['machine_name'] = machine['name']
            result['machine_type'] = machine['type']
            
            return result
    
    @staticmethod
    async def calculate_load_factor(
        machine_id: UUID,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """
        Calculate Load Factor.
        
        Formula: Load_Factor = AVG(power_kw) / MAX(power_kw)
        
        Args:
            machine_id: Machine UUID
            start_time: Start of calculation period
            end_time: End of calculation period
            
        Returns:
            Load factor results
        """
        machine = await get_machine_by_id(machine_id)
        if not machine:
            raise ValueError(f"Machine not found: {machine_id}")
        
        query = "SELECT * FROM calculate_load_factor($1, $2, $3)"
        
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(query, machine_id, start_time, end_time)
            
            if not row:
                raise ValueError("Unable to calculate load factor - no data available")
            
            result = dict(row)
            result['machine_name'] = machine['name']
            result['machine_type'] = machine['type']
            
            return result
    
    @staticmethod
    async def calculate_energy_cost(
        machine_id: UUID,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """
        Calculate Energy Cost with time-of-use tariff.
        
        Formula: Cost = SUM(energy_kwh * tariff_rate)
        Tariff: Peak (08:00-20:00): $0.20/kWh, Off-peak: $0.10/kWh
        
        Args:
            machine_id: Machine UUID
            start_time: Start of calculation period
            end_time: End of calculation period
            
        Returns:
            Energy cost results
        """
        machine = await get_machine_by_id(machine_id)
        if not machine:
            raise ValueError(f"Machine not found: {machine_id}")
        
        query = "SELECT * FROM calculate_energy_cost($1, $2, $3)"
        
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(query, machine_id, start_time, end_time)
            
            if not row:
                raise ValueError("Unable to calculate energy cost - no data available")
            
            result = dict(row)
            result['machine_name'] = machine['name']
            result['machine_type'] = machine['type']
            
            return result
    
    @staticmethod
    async def calculate_carbon_intensity(
        machine_id: UUID,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """
        Calculate Carbon Intensity.
        
        Formula: CO2 = SUM(energy_kwh) * emission_factor
        Emission Factor: 0.45 kg CO2/kWh (grid average)
        
        Args:
            machine_id: Machine UUID
            start_time: Start of calculation period
            end_time: End of calculation period
            
        Returns:
            Carbon intensity results
        """
        machine = await get_machine_by_id(machine_id)
        if not machine:
            raise ValueError(f"Machine not found: {machine_id}")
        
        query = "SELECT * FROM calculate_carbon_intensity($1, $2, $3)"
        
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(query, machine_id, start_time, end_time)
            
            if not row:
                raise ValueError("Unable to calculate carbon intensity - no data available")
            
            result = dict(row)
            result['machine_name'] = machine['name']
            result['machine_type'] = machine['type']
            
            return result
    
    @staticmethod
    async def calculate_all_kpis(
        machine_id: UUID,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """
        Calculate all KPIs in a single database call.
        
        Includes: SEC, Peak Demand, Load Factor, Energy Cost, Carbon Intensity
        
        Args:
            machine_id: Machine UUID
            start_time: Start of calculation period
            end_time: End of calculation period
            
        Returns:
            All KPI results combined
        """
        machine = await get_machine_by_id(machine_id)
        if not machine:
            raise ValueError(f"Machine not found: {machine_id}")
        
        query = "SELECT * FROM calculate_all_kpis($1, $2, $3)"
        
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(query, machine_id, start_time, end_time)
            
            if not row:
                raise ValueError("Unable to calculate KPIs - no data available")
            
            # Format result
            result = {
                'machine_id': str(machine_id),
                'machine_name': machine['name'],
                'machine_type': machine['type'],
                'time_period': {
                    'start': start_time.isoformat(),
                    'end': end_time.isoformat(),
                    'hours': float(row['time_period_hours'])
                },
                'kpis': {
                    'sec': {
                        'value': float(row['sec_kwh_per_unit']) if row['sec_kwh_per_unit'] else None,
                        'unit': 'kWh/unit',
                        'description': 'Specific Energy Consumption'
                    },
                    'peak_demand': {
                        'value': float(row['peak_demand_kw']) if row['peak_demand_kw'] else None,
                        'unit': 'kW',
                        'description': 'Maximum Power Demand'
                    },
                    'load_factor': {
                        'value': float(row['load_factor']) if row['load_factor'] else None,
                        'percent': float(row['load_factor_percent']) if row['load_factor_percent'] else None,
                        'unit': 'ratio',
                        'description': 'Average/Peak Power Ratio'
                    },
                    'energy_cost': {
                        'value': float(row['total_cost']) if row['total_cost'] else None,
                        'cost_per_unit': float(row['cost_per_unit']) if row['cost_per_unit'] else None,
                        'unit': 'USD',
                        'description': 'Total Energy Cost (Time-of-Use Tariff)'
                    },
                    'carbon_intensity': {
                        'value': float(row['total_co2_kg']) if row['total_co2_kg'] else None,
                        'co2_per_unit': float(row['co2_per_unit_kg']) if row['co2_per_unit_kg'] else None,
                        'unit': 'kg CO2',
                        'description': 'Total Carbon Emissions'
                    }
                },
                'totals': {
                    'total_energy_kwh': float(row['total_energy_kwh']),
                    'avg_power_kw': float(row['avg_power_kw']),
                    'total_production_units': int(row['total_production_units']) if row['total_production_units'] else 0
                }
            }
            
            return result


# Global service instance
kpi_service = KPIService()