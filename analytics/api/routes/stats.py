"""
EnMS Analytics - Statistics API Routes
========================================
API endpoints for aggregated statistics across multiple machines.
"""

from fastapi import APIRouter, Query, HTTPException
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime

from database import db, get_machines

router = APIRouter()


@router.get("/stats/aggregated", tags=["Statistics"])
async def get_aggregated_stats(
    machine_ids: Optional[str] = Query(None, description="Comma-separated machine IDs or 'all'"),
    start_time: datetime = Query(..., description="Start time (ISO 8601)"),
    end_time: datetime = Query(..., description="End time (ISO 8601)")
) -> Dict[str, Any]:
    """
    Get aggregated statistics across multiple machines.
    
    **NEW FEATURE** - Factory-wide energy totals and analytics.
    
    **Parameters:**
    - `machine_ids`: Comma-separated UUIDs or "all" for all machines
    - `start_time`: Start of period (ISO 8601)
    - `end_time`: End of period (ISO 8601)
    
    **Returns:**
    - Aggregated energy consumption, costs, carbon emissions
    - Per-machine breakdown with rankings
    - Time period summary
    
    **Use Cases:**
    - "Total energy consumption this week for all machines"
    - "How much energy did Compressor-1 and HVAC-Main use today?"
    - "What's our factory-wide carbon footprint this month?"
    
    **Example:**
    ```
    GET /api/v1/stats/aggregated?machine_ids=all&start_time=2025-10-01T00:00:00Z&end_time=2025-10-20T23:59:59Z
    GET /api/v1/stats/aggregated?machine_ids=uuid1,uuid2&start_time=...&end_time=...
    ```
    """
    
    # Determine which machines to query
    if machine_ids and machine_ids.lower() == "all":
        # Get all active machines
        all_machines = await get_machines(is_active=True)
        # asyncpg returns UUID objects directly, no need to convert
        machine_uuid_list = [m["id"] for m in all_machines]
        query_description = "All machines"
    elif machine_ids:
        # Parse comma-separated UUIDs
        try:
            machine_uuid_list = [UUID(mid.strip()) for mid in machine_ids.split(",")]
            query_description = f"{len(machine_uuid_list)} machines"
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid machine_id format: {str(e)}"
            )
    else:
        raise HTTPException(
            status_code=400,
            detail="machine_ids parameter is required (comma-separated UUIDs or 'all')"
        )
    
    if not machine_uuid_list:
        raise HTTPException(
            status_code=404,
            detail="No machines found"
        )
    
    # Calculate time period duration
    duration_hours = (end_time - start_time).total_seconds() / 3600
    
    # Query aggregated data
    query = """
        WITH machine_stats AS (
            SELECT
                er.machine_id,
                m.name as machine_name,
                m.type as machine_type,
                COUNT(*) as reading_count,
                COALESCE(SUM(er.energy_kwh), 0) as total_energy_kwh,
                COALESCE(AVG(er.power_kw), 0) as avg_power_kw,
                COALESCE(MAX(er.power_kw), 0) as peak_power_kw,
                COALESCE(MIN(er.power_kw), 0) as min_power_kw
            FROM energy_readings er
            JOIN machines m ON er.machine_id = m.id
            WHERE er.machine_id = ANY($1::uuid[])
                AND er.time >= $2
                AND er.time < $3
            GROUP BY er.machine_id, m.name, m.type
        )
        SELECT
            machine_id,
            machine_name,
            machine_type,
            reading_count,
            total_energy_kwh,
            avg_power_kw,
            peak_power_kw,
            min_power_kw
        FROM machine_stats
        ORDER BY total_energy_kwh DESC;
    """
    
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(query, machine_uuid_list, start_time, end_time)
    
    if not rows:
        return {
            "time_period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "duration_hours": round(duration_hours, 2)
            },
            "query": query_description,
            "machines_count": 0,
            "message": "No data available for this time period",
            "totals": {
                "total_energy_kwh": 0.0,
                "total_cost_usd": 0.0,
                "total_carbon_kg_co2": 0.0,
                "avg_power_kw": 0.0,
                "peak_power_kw": 0.0
            },
            "machines": []
        }
    
    # Calculate totals and build machine list
    total_energy = 0.0
    total_avg_power = 0.0
    peak_power = 0.0
    machines = []
    
    for row in rows:
        machine_energy = float(row["total_energy_kwh"])
        machine_avg_power = float(row["avg_power_kw"])
        machine_peak_power = float(row["peak_power_kw"])
        
        total_energy += machine_energy
        total_avg_power += machine_avg_power
        peak_power = max(peak_power, machine_peak_power)
        
        machines.append({
            "machine_id": str(row["machine_id"]),
            "machine_name": row["machine_name"],
            "machine_type": row["machine_type"],
            "reading_count": row["reading_count"],
            "total_energy_kwh": round(machine_energy, 3),
            "avg_power_kw": round(machine_avg_power, 3),
            "peak_power_kw": round(machine_peak_power, 3),
            "min_power_kw": round(float(row["min_power_kw"]), 3)
        })
    
    # Calculate costs and carbon
    # Using standard rates: $0.15/kWh and 0.45 kg CO2/kWh
    cost_per_kwh = 0.15
    carbon_per_kwh = 0.45
    
    total_cost = total_energy * cost_per_kwh
    total_carbon = total_energy * carbon_per_kwh
    
    # Add percentage contribution to each machine
    for machine in machines:
        machine["energy_percent"] = round(
            (machine["total_energy_kwh"] / total_energy * 100) if total_energy > 0 else 0.0,
            2
        )
        machine["cost_usd"] = round(machine["total_energy_kwh"] * cost_per_kwh, 2)
        machine["carbon_kg_co2"] = round(machine["total_energy_kwh"] * carbon_per_kwh, 2)
    
    return {
        "time_period": {
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
            "duration_hours": round(duration_hours, 2),
            "duration_days": round(duration_hours / 24, 2)
        },
        "query": query_description,
        "machines_count": len(machines),
        "totals": {
            "total_energy_kwh": round(total_energy, 3),
            "total_cost_usd": round(total_cost, 2),
            "total_carbon_kg_co2": round(total_carbon, 2),
            "avg_power_kw": round(total_avg_power, 3),
            "peak_power_kw": round(peak_power, 3),
            "cost_per_day": round(total_cost / (duration_hours / 24), 2) if duration_hours > 0 else 0.0,
            "carbon_per_day": round(total_carbon / (duration_hours / 24), 2) if duration_hours > 0 else 0.0
        },
        "machines": machines,
        "rankings": {
            "highest_energy": machines[0]["machine_name"] if machines else None,
            "highest_peak_power": max(machines, key=lambda m: m["peak_power_kw"])["machine_name"] if machines else None,
            "highest_avg_power": max(machines, key=lambda m: m["avg_power_kw"])["machine_name"] if machines else None
        }
    }
