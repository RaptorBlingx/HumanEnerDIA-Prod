"""
EnMS Analytics Service - KPI API Routes
========================================
REST API endpoints for Key Performance Indicator calculations.

Author: EnMS Team
Phase: 3 - Analytics & ML
"""

from fastapi import APIRouter, HTTPException, Query
from datetime import datetime
from uuid import UUID
import logging

from services.kpi_service import kpi_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/kpi/sec", tags=["KPI"])
async def get_sec(
    machine_id: UUID = Query(..., description="Machine UUID"),
    start: datetime = Query(..., description="Start of calculation period (ISO 8601)"),
    end: datetime = Query(..., description="End of calculation period (ISO 8601)")
):
    """
    Calculate Specific Energy Consumption (SEC).
    
    **Formula:**
    ```
    SEC = Total Energy (kWh) / Total Production (units)
    ```
    
    **Unit:** kWh/unit
    
    **Use Cases:**
    - ISO 50001 compliance reporting
    - Energy efficiency benchmarking
    - Production cost analysis
    - Process optimization tracking
    
    **Returns:**
    - SEC value (kWh/unit)
    - Total energy consumed (kWh)
    - Total production (units)
    - Time period (hours)
    """
    try:
        result = await kpi_service.calculate_sec(
            machine_id=machine_id,
            start_time=start,
            end_time=end
        )
        return result
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error calculating KPIs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/kpi/factory/{factory_id}", tags=["KPI", "OVOS"])
async def get_factory_kpis(
    factory_id: UUID,
    start: datetime = Query(..., description="Start of calculation period (ISO 8601)"),
    end: datetime = Query(..., description="End of calculation period (ISO 8601)")
):
    """
    Calculate factory-wide aggregated KPIs for all machines.
    
    **OVOS-OPTIMIZED** - Factory-level energy metrics.
    
    **Aggregates:**
    - Total energy consumption (kWh)
    - Total energy cost (USD)
    - Total carbon emissions (kg CO₂)
    - Peak factory demand (kW)
    - Average power demand (kW)
    - Machine count (active/idle/stopped)
    - Production totals (units)
    - Factory-wide SEC (kWh/unit)
    
    **Use Cases:**
    - "What's the total energy consumption for the factory?"
    - "How much did the factory spend on energy today?"
    - Multi-factory comparison
    - Factory-level ISO 50001 reporting
    
    **Parameters:**
    - `factory_id`: Factory UUID
    - `start`: Start datetime (ISO 8601)
    - `end`: End datetime (ISO 8601)
    
    **Example:**
    ```bash
    curl -G "http://localhost:8001/api/v1/kpi/factory/11111111-1111-1111-1111-111111111111" \
      --data-urlencode "start=2025-10-20T00:00:00" \
      --data-urlencode "end=2025-10-20T23:59:59"
    ```
    
    **Voice Response Template:**
    "The factory consumed 2,500 kilowatt hours today, costing $375. Peak 
    demand was 310 kilowatts. 7 machines are active. Total production 
    was 125,000 units with a factory-wide SEC of 0.02 kilowatt hours per unit."
    """
    try:
        from database import db, get_machines
        from typing import Dict, Any, List
        
        # Get all machines in this factory
        all_machines = await get_machines()
        factory_machines = [m for m in all_machines if m.get('factory_id') == factory_id]
        
        if not factory_machines:
            raise HTTPException(
                status_code=404,
                detail=f"No machines found for factory_id: {factory_id}"
            )
        
        machine_ids = [m['id'] for m in factory_machines]
        
        async with db.pool.acquire() as conn:
            # Get factory info
            factory_info = await conn.fetchrow("""
                SELECT id, name, location
                FROM factories
                WHERE id = $1
            """, factory_id)
            
            if not factory_info:
                raise HTTPException(
                    status_code=404,
                    detail=f"Factory not found: {factory_id}"
                )
            
            # Aggregate energy metrics for all machines
            energy_stats = await conn.fetchrow("""
                SELECT 
                    SUM(energy_kwh) as total_energy,
                    AVG(power_kw) as avg_power,
                    MAX(power_kw) as peak_power,
                    COUNT(DISTINCT machine_id) as machines_with_data
                FROM energy_readings
                WHERE machine_id = ANY($1)
                    AND time >= $2
                    AND time <= $3
            """, machine_ids, start, end)
            
            # Get production totals
            production_stats = await conn.fetchrow("""
                SELECT 
                    SUM(production_count) as total_units,
                    SUM(production_count_good) as total_good,
                    SUM(production_count_bad) as total_bad
                FROM production_data
                WHERE machine_id = ANY($1)
                    AND time >= $2
                    AND time <= $3
            """, machine_ids, start, end)
            
            # Get current status for each machine (latest reading)
            latest_readings = await conn.fetch("""
                SELECT DISTINCT ON (machine_id)
                    machine_id,
                    power_kw,
                    time
                FROM energy_readings
                WHERE machine_id = ANY($1)
                ORDER BY machine_id, time DESC
            """, machine_ids)
        
        # Calculate metrics
        total_energy = float(energy_stats['total_energy']) if energy_stats['total_energy'] else 0.0
        avg_power = float(energy_stats['avg_power']) if energy_stats['avg_power'] else 0.0
        peak_power = float(energy_stats['peak_power']) if energy_stats['peak_power'] else 0.0
        
        # Energy cost and carbon
        ENERGY_RATE = 0.15  # $/kWh
        CARBON_RATE = 0.45  # kg CO2/kWh
        total_cost = total_energy * ENERGY_RATE
        total_carbon = total_energy * CARBON_RATE
        
        # Production metrics
        total_units = int(production_stats['total_units']) if production_stats['total_units'] else 0
        total_good = int(production_stats['total_good']) if production_stats['total_good'] else 0
        total_bad = int(production_stats['total_bad']) if production_stats['total_bad'] else 0
        quality_percent = (total_good / total_units * 100) if total_units > 0 else 0.0
        
        # Factory-wide SEC
        factory_sec = (total_energy / total_units) if total_units > 0 else 0.0
        
        # Machine status classification (based on latest power reading)
        status_counts = {"active": 0, "idle": 0, "stopped": 0}
        for reading in latest_readings:
            power = float(reading['power_kw'])
            if power > 5.0:
                status_counts["active"] += 1
            elif power > 0.5:
                status_counts["idle"] += 1
            else:
                status_counts["stopped"] += 1
        
        # Calculate duration
        duration_hours = (end - start).total_seconds() / 3600
        
        response = {
            "factory_id": str(factory_id),
            "factory_name": factory_info['name'],
            "factory_location": factory_info['location'],
            "time_period": {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "duration_hours": round(duration_hours, 2)
            },
            "energy_metrics": {
                "total_energy_kwh": round(total_energy, 2),
                "total_cost_usd": round(total_cost, 2),
                "total_carbon_kg": round(total_carbon, 2),
                "avg_power_kw": round(avg_power, 2),
                "peak_power_kw": round(peak_power, 2)
            },
            "production_metrics": {
                "total_units": total_units,
                "units_good": total_good,
                "units_bad": total_bad,
                "quality_percent": round(quality_percent, 2),
                "factory_sec_kwh_per_unit": round(factory_sec, 6)
            },
            "machine_status": {
                "total_machines": len(factory_machines),
                "active": status_counts["active"],
                "idle": status_counts["idle"],
                "stopped": status_counts["stopped"],
                "machines_with_data": energy_stats['machines_with_data']
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating factory KPIs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error calculating factory KPIs: {str(e)}")


@router.get("/kpi/factories", tags=["KPI", "OVOS"])
async def get_all_factories_kpis(
    start: datetime = Query(..., description="Start of calculation period (ISO 8601)"),
    end: datetime = Query(..., description="End of calculation period (ISO 8601)")
):
    """
    Calculate aggregated KPIs for ALL factories (multi-factory comparison).
    
    **OVOS-OPTIMIZED** - Enterprise-wide energy metrics.
    
    **Returns:**
    - Individual KPIs for each factory
    - Enterprise totals across all factories
    - Factory rankings by energy, cost, efficiency
    
    **Use Cases:**
    - "Compare energy consumption across all factories"
    - "Which factory is most efficient?"
    - Enterprise-level reporting
    - Multi-site ISO 50001 compliance
    
    **Parameters:**
    - `start`: Start datetime (ISO 8601)
    - `end`: End datetime (ISO 8601)
    
    **Example:**
    ```bash
    curl -G "http://localhost:8001/api/v1/kpi/factories" \
      --data-urlencode "start=2025-10-20T00:00:00" \
      --data-urlencode "end=2025-10-20T23:59:59"
    ```
    
    **Voice Response Template:**
    "Across all factories: Total energy consumption is 4,800 kilowatt hours 
    costing $720. The Demo Manufacturing Plant leads with 2,500 kilowatt 
    hours. The European facility used 2,300 kilowatt hours."
    """
    try:
        from database import db
        
        async with db.pool.acquire() as conn:
            # Get all factories
            factories = await conn.fetch("""
                SELECT id, name, location
                FROM factories
                ORDER BY name
            """)
            
            if not factories:
                raise HTTPException(
                    status_code=404,
                    detail="No factories found in the system"
                )
        
        # Calculate KPIs for each factory
        factory_results = []
        total_energy = 0.0
        total_cost = 0.0
        total_carbon = 0.0
        total_machines = 0
        total_production = 0
        
        for factory in factories:
            factory_id = factory['id']
            
            # Call the factory KPI endpoint logic
            try:
                factory_kpis = await get_factory_kpis(
                    factory_id=factory_id,
                    start=start,
                    end=end
                )
                
                factory_results.append(factory_kpis)
                
                # Aggregate totals
                total_energy += factory_kpis['energy_metrics']['total_energy_kwh']
                total_cost += factory_kpis['energy_metrics']['total_cost_usd']
                total_carbon += factory_kpis['energy_metrics']['total_carbon_kg']
                total_machines += factory_kpis['machine_status']['total_machines']
                total_production += factory_kpis['production_metrics']['total_units']
                
            except HTTPException as e:
                # Factory has no machines or data - skip it
                if e.status_code == 404:
                    continue
                raise
        
        # Calculate enterprise-wide SEC
        enterprise_sec = (total_energy / total_production) if total_production > 0 else 0.0
        
        # Rank factories by energy consumption
        ranked_factories = sorted(
            factory_results,
            key=lambda f: f['energy_metrics']['total_energy_kwh'],
            reverse=True
        )
        
        # Calculate duration
        duration_hours = (end - start).total_seconds() / 3600
        
        response = {
            "time_period": {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "duration_hours": round(duration_hours, 2)
            },
            "enterprise_totals": {
                "total_energy_kwh": round(total_energy, 2),
                "total_cost_usd": round(total_cost, 2),
                "total_carbon_kg": round(total_carbon, 2),
                "total_machines": total_machines,
                "total_production_units": total_production,
                "enterprise_sec_kwh_per_unit": round(enterprise_sec, 6)
            },
            "factory_count": len(factory_results),
            "factories": factory_results,
            "rankings": {
                "by_energy": [
                    {
                        "rank": idx + 1,
                        "factory_name": f['factory_name'],
                        "factory_id": f['factory_id'],
                        "energy_kwh": f['energy_metrics']['total_energy_kwh'],
                        "percentage": round(
                            f['energy_metrics']['total_energy_kwh'] / total_energy * 100, 1
                        ) if total_energy > 0 else 0.0
                    }
                    for idx, f in enumerate(ranked_factories)
                ]
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating all factory KPIs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error calculating all factory KPIs: {str(e)}")


@router.get("/kpi/peak-demand", tags=["KPI"])
async def get_peak_demand(
    machine_id: UUID = Query(..., description="Machine UUID"),
    start: datetime = Query(..., description="Start of calculation period (ISO 8601)"),
    end: datetime = Query(..., description="End of calculation period (ISO 8601)")
):
    """
    Calculate Peak Demand.
    
    **Formula:**
    ```
    Peak Demand = MAX(power_kw) over 15-minute rolling window
    ```
    
    **Unit:** kW
    
    **Use Cases:**
    - Demand charge optimization
    - Capacity planning
    - Load shedding strategies
    - Utility billing verification
    
    **Returns:**
    - Peak demand value (kW)
    - Timestamp of peak occurrence
    - Average power (kW)
    """
    try:
        result = await kpi_service.calculate_peak_demand(
            machine_id=machine_id,
            start_time=start,
            end_time=end
        )
        return result
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error calculating peak demand: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/kpi/load-factor", tags=["KPI"])
async def get_load_factor(
    machine_id: UUID = Query(..., description="Machine UUID"),
    start: datetime = Query(..., description="Start of calculation period (ISO 8601)"),
    end: datetime = Query(..., description="End of calculation period (ISO 8601)")
):
    """
    Calculate Load Factor.
    
    **Formula:**
    ```
    Load Factor = AVG(power_kw) / MAX(power_kw)
    ```
    
    **Unit:** Ratio (0-1) or Percentage (0-100%)
    
    **Interpretation:**
    - **High (>0.7)**: Efficient, consistent operation
    - **Medium (0.4-0.7)**: Typical intermittent operation
    - **Low (<0.4)**: Inefficient, frequent cycling
    
    **Use Cases:**
    - Equipment utilization analysis
    - Operational efficiency assessment
    - Maintenance planning
    - Right-sizing equipment
    
    **Returns:**
    - Load factor (ratio)
    - Load factor (percentage)
    - Average power (kW)
    - Peak power (kW)
    """
    try:
        result = await kpi_service.calculate_load_factor(
            machine_id=machine_id,
            start_time=start,
            end_time=end
        )
        return result
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error calculating load factor: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/kpi/energy-cost", tags=["KPI", "OVOS"])
async def get_energy_cost(
    machine_id: UUID = Query(..., description="Machine UUID"),
    start: datetime = Query(..., description="Start of calculation period (ISO 8601)"),
    end: datetime = Query(..., description="End of calculation period (ISO 8601)"),
    tariff: str = Query("standard", description="Tariff type: standard, time_of_use, demand_charge"),
    peak_rate: float = Query(0.20, description="Peak hour rate ($/kWh) - for time_of_use tariff"),
    offpeak_rate: float = Query(0.10, description="Off-peak hour rate ($/kWh) - for time_of_use tariff"),
    peak_hours_start: int = Query(8, description="Peak hours start (0-23) - for time_of_use tariff", ge=0, le=23),
    peak_hours_end: int = Query(20, description="Peak hours end (0-23) - for time_of_use tariff", ge=0, le=23),
    demand_charge: float = Query(15.0, description="Demand charge ($/kW) - for demand_charge tariff")
):
    """
    Calculate Energy Cost with configurable tariff structures.
    
    **OVOS-OPTIMIZED** - Realistic commercial pricing calculations.
    
    **Tariff Types:**
    
    1. **standard** (default): Flat rate $0.15/kWh
       - Simple calculation: Cost = Energy × Rate
       - Use for basic cost tracking
    
    2. **time_of_use**: Peak/off-peak pricing
       - Peak hours (default 8am-8pm): Configurable rate (default $0.20/kWh)
       - Off-peak hours (8pm-8am): Configurable rate (default $0.10/kWh)
       - Use for load-shifting analysis
    
    3. **demand_charge**: Peak demand billing
       - Energy charge: $0.15/kWh
       - Demand charge: $/kW for peak 15-min demand (default $15/kW)
       - Use for industrial utility billing simulation
    
    **Parameters:**
    - `machine_id`: Machine UUID
    - `start`: Start datetime (ISO 8601)
    - `end`: End datetime (ISO 8601)
    - `tariff`: standard | time_of_use | demand_charge
    - `peak_rate`: Peak hour rate ($/kWh) for TOU
    - `offpeak_rate`: Off-peak hour rate ($/kWh) for TOU
    - `peak_hours_start`: Peak start hour (0-23)
    - `peak_hours_end`: Peak end hour (0-23)
    - `demand_charge`: Demand charge rate ($/kW)
    
    **Examples:**
    ```bash
    # Standard flat rate
    curl -G "http://localhost:8001/api/v1/kpi/energy-cost" \
      --data-urlencode "machine_id=c0000000-0000-0000-0000-000000000001" \
      --data-urlencode "start=2025-10-20T00:00:00" \
      --data-urlencode "end=2025-10-20T23:59:59"
    
    # Time-of-use pricing
    curl -G "http://localhost:8001/api/v1/kpi/energy-cost" \
      --data-urlencode "machine_id=c0000000-0000-0000-0000-000000000001" \
      --data-urlencode "start=2025-10-20T00:00:00" \
      --data-urlencode "end=2025-10-20T23:59:59" \
      --data-urlencode "tariff=time_of_use" \
      --data-urlencode "peak_rate=0.25" \
      --data-urlencode "offpeak_rate=0.08"
    
    # Demand charge billing
    curl -G "http://localhost:8001/api/v1/kpi/energy-cost" \
      --data-urlencode "machine_id=c0000000-0000-0000-0000-000000000001" \
      --data-urlencode "start=2025-10-20T00:00:00" \
      --data-urlencode "end=2025-10-20T23:59:59" \
      --data-urlencode "tariff=demand_charge" \
      --data-urlencode "demand_charge=20.0"
    ```
    
    **OVOS Use Case:** "How much would we save with time-of-use pricing?"
    
    **Voice Response Template:**
    "With time-of-use pricing, the cost would be $82.50, compared to $84.00 
    with standard flat rate. That's a savings of $1.50 or 1.8%. Peak hours 
    consumed 180 kilowatt hours at 25 cents, off-peak used 380 kilowatt hours 
    at 8 cents."
    """
    try:
        # Validate tariff type
        valid_tariffs = ['standard', 'time_of_use', 'demand_charge']
        if tariff not in valid_tariffs:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid tariff type. Must be one of: {', '.join(valid_tariffs)}"
            )
        
        # Validate peak hours
        if peak_hours_start >= peak_hours_end:
            raise HTTPException(
                status_code=400,
                detail="peak_hours_start must be less than peak_hours_end"
            )
        
        from database import db
        
        async with db.pool.acquire() as conn:
            # Get energy readings for the period
            readings = await conn.fetch("""
                SELECT 
                    time,
                    power_kw,
                    energy_kwh
                FROM energy_readings
                WHERE machine_id = $1
                    AND time >= $2
                    AND time <= $3
                ORDER BY time
            """, machine_id, start, end)
            
            if not readings:
                raise HTTPException(
                    status_code=404,
                    detail=f"No energy data found for machine {machine_id} in the specified period"
                )
        
        total_energy = sum(float(r['energy_kwh']) for r in readings)
        
        # Calculate cost based on tariff type
        if tariff == 'standard':
            # Simple flat rate
            STANDARD_RATE = 0.15
            total_cost = total_energy * STANDARD_RATE
            
            response = {
                "tariff_type": "standard",
                "machine_id": str(machine_id),
                "time_period": {
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "duration_hours": round((end - start).total_seconds() / 3600, 2)
                },
                "energy_kwh": round(total_energy, 2),
                "rate_usd_per_kwh": STANDARD_RATE,
                "total_cost_usd": round(total_cost, 2),
                "cost_breakdown": {
                    "energy_charge": round(total_cost, 2)
                }
            }
        
        elif tariff == 'time_of_use':
            # Time-of-use pricing
            peak_energy = 0.0
            offpeak_energy = 0.0
            
            for reading in readings:
                hour = reading['time'].hour
                energy = float(reading['energy_kwh'])
                
                # Check if in peak hours
                if peak_hours_start <= hour < peak_hours_end:
                    peak_energy += energy
                else:
                    offpeak_energy += energy
            
            peak_cost = peak_energy * peak_rate
            offpeak_cost = offpeak_energy * offpeak_rate
            total_cost = peak_cost + offpeak_cost
            
            # Calculate savings compared to standard flat rate
            STANDARD_RATE = 0.15
            standard_cost = total_energy * STANDARD_RATE
            savings = standard_cost - total_cost
            savings_percent = (savings / standard_cost * 100) if standard_cost > 0 else 0.0
            
            response = {
                "tariff_type": "time_of_use",
                "machine_id": str(machine_id),
                "time_period": {
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "duration_hours": round((end - start).total_seconds() / 3600, 2)
                },
                "peak_hours": f"{peak_hours_start:02d}:00-{peak_hours_end:02d}:00",
                "energy_kwh": round(total_energy, 2),
                "total_cost_usd": round(total_cost, 2),
                "cost_breakdown": {
                    "peak_hours": {
                        "energy_kwh": round(peak_energy, 2),
                        "rate_usd_per_kwh": peak_rate,
                        "cost_usd": round(peak_cost, 2),
                        "percentage": round(peak_energy / total_energy * 100, 1) if total_energy > 0 else 0.0
                    },
                    "offpeak_hours": {
                        "energy_kwh": round(offpeak_energy, 2),
                        "rate_usd_per_kwh": offpeak_rate,
                        "cost_usd": round(offpeak_cost, 2),
                        "percentage": round(offpeak_energy / total_energy * 100, 1) if total_energy > 0 else 0.0
                    }
                },
                "comparison_to_standard": {
                    "standard_flat_rate": STANDARD_RATE,
                    "standard_cost_usd": round(standard_cost, 2),
                    "tou_cost_usd": round(total_cost, 2),
                    "savings_usd": round(savings, 2),
                    "savings_percent": round(savings_percent, 1)
                }
            }
        
        elif tariff == 'demand_charge':
            # Demand charge billing
            ENERGY_RATE = 0.15
            
            # Find peak 15-minute demand (use max power reading as proxy)
            peak_demand_kw = max(float(r['power_kw']) for r in readings)
            
            energy_charge = total_energy * ENERGY_RATE
            demand_charge_cost = peak_demand_kw * demand_charge
            total_cost = energy_charge + demand_charge_cost
            
            # Calculate savings compared to standard
            STANDARD_RATE = 0.15
            standard_cost = total_energy * STANDARD_RATE
            difference = total_cost - standard_cost
            
            response = {
                "tariff_type": "demand_charge",
                "machine_id": str(machine_id),
                "time_period": {
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "duration_hours": round((end - start).total_seconds() / 3600, 2)
                },
                "energy_kwh": round(total_energy, 2),
                "peak_demand_kw": round(peak_demand_kw, 2),
                "total_cost_usd": round(total_cost, 2),
                "cost_breakdown": {
                    "energy_charge": {
                        "energy_kwh": round(total_energy, 2),
                        "rate_usd_per_kwh": ENERGY_RATE,
                        "cost_usd": round(energy_charge, 2)
                    },
                    "demand_charge": {
                        "peak_demand_kw": round(peak_demand_kw, 2),
                        "rate_usd_per_kw": demand_charge,
                        "cost_usd": round(demand_charge_cost, 2)
                    }
                },
                "comparison_to_standard": {
                    "standard_cost_usd": round(standard_cost, 2),
                    "demand_charge_cost_usd": round(total_cost, 2),
                    "difference_usd": round(difference, 2),
                    "note": "Positive difference means demand charge billing is more expensive"
                }
            }
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating energy cost: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error calculating energy cost: {str(e)}")


@router.get("/kpi/carbon", tags=["KPI"])
async def get_carbon_intensity(
    machine_id: UUID = Query(..., description="Machine UUID"),
    start: datetime = Query(..., description="Start of calculation period (ISO 8601)"),
    end: datetime = Query(..., description="End of calculation period (ISO 8601)")
):
    """
    Calculate Carbon Intensity (CO₂ emissions).
    
    **Formula:**
    ```
    CO₂ = SUM(energy_kwh) × emission_factor
    ```
    
    **Emission Factor:** 0.45 kg CO₂/kWh (grid average)
    
    **Unit:** kg CO₂
    
    **Use Cases:**
    - Carbon footprint reporting
    - Sustainability metrics
    - Scope 2 emissions (GHG Protocol)
    - ESG reporting
    - Carbon credit calculations
    
    **Returns:**
    - Total CO₂ emissions (kg)
    - CO₂ per production unit (kg/unit)
    - Total energy consumed (kWh)
    """
    try:
        result = await kpi_service.calculate_carbon_intensity(
            machine_id=machine_id,
            start_time=start,
            end_time=end
        )
        return result
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error calculating carbon intensity: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/kpi/all", tags=["KPI"])
async def get_all_kpis(
    machine_id: UUID = Query(..., description="Machine UUID"),
    start: datetime = Query(..., description="Start of calculation period (ISO 8601)"),
    end: datetime = Query(..., description="End of calculation period (ISO 8601)")
):
    """
    Calculate all KPIs in a single optimized query.
    
    **Includes:**
    1. **SEC** - Specific Energy Consumption (kWh/unit)
    2. **Peak Demand** - Maximum power draw (kW)
    3. **Load Factor** - Utilization ratio (0-1)
    4. **Energy Cost** - Total cost with TOU tariff (USD)
    5. **Carbon Intensity** - CO₂ emissions (kg)
    
    **Performance:**
    - Single database call for efficiency
    - Optimized for dashboard displays
    - Includes summary totals
    
    **Use Cases:**
    - Executive dashboards
    - Comprehensive reports
    - ISO 50001 compliance packages
    - Multi-KPI analysis
    
    **Returns:**
    - All 5 KPIs with values and units
    - Time period summary
    - Production totals
    - Energy totals
    """
    try:
        result = await kpi_service.calculate_all_kpis(
            machine_id=machine_id,
            start_time=start,
            end_time=end
        )
        return result
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error calculating KPIs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")