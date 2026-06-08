"""
Machine Comparison API Routes
==============================
Provides comparative analysis between multiple machines for benchmarking.

Features:
- Side-by-side metrics comparison
- Performance ranking
- Energy efficiency benchmarking
- KPI comparison

Author: EnMS Team
Date: October 14, 2025
Phase 4, Session 3
"""

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import logging
from database import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/comparison")


# ============================================================================
# DATA MODELS
# ============================================================================

class MachineMetrics(BaseModel):
    """Metrics for a single machine"""
    machine_id: str
    machine_name: str
    machine_type: str
    
    # Energy metrics
    total_energy_kwh: float = Field(..., description="Total energy consumed")
    avg_power_kw: float = Field(..., description="Average power demand")
    peak_power_kw: float = Field(..., description="Peak power demand")
    
    # Efficiency metrics
    sec: float = Field(..., description="Specific Energy Consumption")
    load_factor: float = Field(..., description="Load factor (%)")
    operating_hours: float = Field(..., description="Operating hours")
    
    # Production metrics
    total_production: int = Field(..., description="Total production units")
    uptime_percent: float = Field(..., description="Uptime percentage")
    
    # Cost metrics
    energy_cost: float = Field(..., description="Total energy cost")
    cost_per_unit: float = Field(..., description="Cost per production unit")
    
    # Rank (1 = best, higher = worse)
    rank_energy: int = Field(..., description="Energy efficiency rank")
    rank_sec: int = Field(..., description="SEC rank")
    rank_cost: int = Field(..., description="Cost efficiency rank")
    rank_overall: int = Field(..., description="Overall rank")


class ComparisonData(BaseModel):
    """Complete comparison data"""
    machines: List[MachineMetrics] = Field(..., description="All machine metrics")
    start_date: datetime = Field(..., description="Start of analysis period")
    end_date: datetime = Field(..., description="End of analysis period")
    best_performer: str = Field(..., description="Name of best overall performer")
    worst_performer: str = Field(..., description="Name of worst overall performer")
    insights: List[str] = Field(..., description="Comparison insights")


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/machines", response_model=ComparisonData)
async def compare_machines(
    machine_ids: str = Query(..., description="Comma-separated machine IDs (2-5 machines)"),
    start_date: Optional[datetime] = Query(None, description="Start date (default: 30 days ago)"),
    end_date: Optional[datetime] = Query(None, description="End date (default: now)"),
    energy_cost_per_kwh: float = Query(0.12, description="Energy cost per kWh ($)")
):
    """
    Compare multiple machines side-by-side.
    
    Args:
        machine_ids: Comma-separated list of machine IDs (2-5 machines)
        start_date: Start of analysis period
        end_date: End of analysis period
        energy_cost_per_kwh: Cost per kWh for cost calculations
    
    Returns:
        ComparisonData with metrics for all machines
    """
    try:
        # Parse machine IDs
        machine_id_list = [mid.strip() for mid in machine_ids.split(',')]
        
        if len(machine_id_list) < 2:
            raise HTTPException(status_code=400, detail="At least 2 machines required for comparison")
        if len(machine_id_list) > 5:
            raise HTTPException(status_code=400, detail="Maximum 5 machines allowed for comparison")
        
        # Default date range: last 30 days
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        # Get database pool
        pool = db.pool
        
        machines_data = []
        
        async with pool.acquire() as conn:
            for machine_id in machine_id_list:
                # Get machine info
                machine_row = await conn.fetchrow("""
                    SELECT id, name, type, rated_power_kw
                    FROM machines
                    WHERE id = $1
                """, machine_id)
                
                if not machine_row:
                    raise HTTPException(status_code=404, detail=f"Machine {machine_id} not found")
                
                # Get energy metrics
                energy_row = await conn.fetchrow("""
                    SELECT 
                        COALESCE(SUM(energy_kwh), 0) AS total_energy_kwh,
                        COALESCE(AVG(power_kw), 0) AS avg_power_kw,
                        COALESCE(MAX(power_kw), 0) AS peak_power_kw,
                        COUNT(*) AS reading_count
                    FROM energy_readings
                    WHERE machine_id = $1 AND time >= $2 AND time <= $3
                """, machine_id, start_date, end_date)
                
                # Get production data
                production_row = await conn.fetchrow("""
                    SELECT 
                        COALESCE(SUM(production_count), 0) AS total_production,
                        COUNT(DISTINCT DATE(time)) AS production_days
                    FROM production_data
                    WHERE machine_id = $1 AND time >= $2 AND time <= $3
                """, machine_id, start_date, end_date)
                
                # Calculate operating hours
                duration_days = (end_date - start_date).total_seconds() / 86400
                operating_hours = duration_days * 24
                
                # Calculate metrics
                total_energy = float(energy_row['total_energy_kwh'])
                avg_power = float(energy_row['avg_power_kw'])
                peak_power = float(energy_row['peak_power_kw'])
                total_production = int(production_row['total_production'])
                rated_power = float(machine_row['rated_power_kw'])
                
                # SEC (Specific Energy Consumption)
                sec = (total_energy / total_production) if total_production > 0 else 0
                
                # Load Factor
                load_factor = (avg_power / rated_power * 100) if rated_power > 0 else 0
                
                # Uptime (based on readings vs expected readings)
                expected_readings = operating_hours * 6  # Assuming 10-min intervals
                uptime_percent = (energy_row['reading_count'] / expected_readings * 100) if expected_readings > 0 else 0
                
                # Cost
                energy_cost = total_energy * energy_cost_per_kwh
                cost_per_unit = (energy_cost / total_production) if total_production > 0 else 0
                
                machines_data.append({
                    'machine_id': str(machine_row['id']),
                    'machine_name': machine_row['name'],
                    'machine_type': machine_row['type'],
                    'total_energy_kwh': round(total_energy, 2),
                    'avg_power_kw': round(avg_power, 2),
                    'peak_power_kw': round(peak_power, 2),
                    'sec': round(sec, 4),
                    'load_factor': round(load_factor, 2),
                    'operating_hours': round(operating_hours, 2),
                    'total_production': total_production,
                    'uptime_percent': round(uptime_percent, 2),
                    'energy_cost': round(energy_cost, 2),
                    'cost_per_unit': round(cost_per_unit, 4)
                })
        
        # Calculate rankings
        # Energy efficiency rank (lower energy is better)
        machines_sorted_energy = sorted(machines_data, key=lambda x: x['total_energy_kwh'])
        for rank, machine in enumerate(machines_sorted_energy, 1):
            machine['rank_energy'] = rank
        
        # SEC rank (lower SEC is better)
        machines_sorted_sec = sorted(machines_data, key=lambda x: x['sec'])
        for rank, machine in enumerate(machines_sorted_sec, 1):
            machine['rank_sec'] = rank
        
        # Cost rank (lower cost is better)
        machines_sorted_cost = sorted(machines_data, key=lambda x: x['cost_per_unit'])
        for rank, machine in enumerate(machines_sorted_cost, 1):
            machine['rank_cost'] = rank
        
        # Overall rank (average of all ranks)
        for machine in machines_data:
            machine['rank_overall'] = round((
                machine['rank_energy'] + 
                machine['rank_sec'] + 
                machine['rank_cost']
            ) / 3)
        
        # Sort by overall rank
        machines_data.sort(key=lambda x: x['rank_overall'])
        
        # Re-rank overall to ensure sequential ranks
        for rank, machine in enumerate(machines_data, 1):
            machine['rank_overall'] = rank
        
        # Convert to Pydantic models
        machines = [MachineMetrics(**m) for m in machines_data]
        
        # Identify best and worst performers
        best_performer = machines[0].machine_name
        worst_performer = machines[-1].machine_name
        
        # Generate insights
        insights = generate_insights(machines_data)
        
        return ComparisonData(
            machines=machines,
            start_date=start_date,
            end_date=end_date,
            best_performer=best_performer,
            worst_performer=worst_performer,
            insights=insights
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing machines: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to compare machines: {str(e)}")


@router.get("/available", response_model=List[Dict])
async def get_available_machines():
    """
    Get list of available machines for comparison.
    
    Returns:
        List of machines with IDs and names
    """
    try:
        pool = db.pool
        
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, name, type, location_in_factory
                FROM machines
                WHERE is_active = TRUE
                ORDER BY name
            """)
        
        return [
            {
                "id": str(row['id']),
                "name": row['name'],
                "type": row['type'],
                "location": row['location_in_factory']
            }
            for row in rows
        ]
        
    except Exception as e:
        logger.error(f"Error fetching available machines: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch machines: {str(e)}")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def generate_insights(machines_data: List[Dict]) -> List[str]:
    """
    Generate comparison insights.
    
    Returns:
        List of human-readable insights
    """
    insights = []
    
    if len(machines_data) < 2:
        return insights
    
    # Best vs worst energy
    best_energy = min(machines_data, key=lambda x: x['total_energy_kwh'])
    worst_energy = max(machines_data, key=lambda x: x['total_energy_kwh'])
    energy_diff_pct = ((worst_energy['total_energy_kwh'] - best_energy['total_energy_kwh']) / 
                       best_energy['total_energy_kwh'] * 100) if best_energy['total_energy_kwh'] > 0 else 0
    
    insights.append(
        f"{worst_energy['machine_name']} consumes {energy_diff_pct:.1f}% more energy than "
        f"{best_energy['machine_name']} ({worst_energy['total_energy_kwh']:.1f} vs {best_energy['total_energy_kwh']:.1f} kWh)"
    )
    
    # Best SEC
    best_sec = min(machines_data, key=lambda x: x['sec'])
    insights.append(
        f"{best_sec['machine_name']} has the best energy efficiency (SEC: {best_sec['sec']:.4f} kWh/unit)"
    )
    
    # Cost savings potential
    best_cost = min(machines_data, key=lambda x: x['cost_per_unit'])
    worst_cost = max(machines_data, key=lambda x: x['cost_per_unit'])
    if worst_cost['total_production'] > 0:
        potential_savings = (worst_cost['cost_per_unit'] - best_cost['cost_per_unit']) * worst_cost['total_production']
        if potential_savings > 0:
            insights.append(
                f"Potential savings: ${potential_savings:.2f} if {worst_cost['machine_name']} "
                f"matched {best_cost['machine_name']}'s efficiency"
            )
    
    # Load factor analysis
    avg_load_factor = sum(m['load_factor'] for m in machines_data) / len(machines_data)
    low_load_machines = [m for m in machines_data if m['load_factor'] < avg_load_factor * 0.7]
    if low_load_machines:
        insights.append(
            f"{len(low_load_machines)} machine(s) running below 70% of average load factor - "
            f"consider load optimization"
        )
    
    return insights