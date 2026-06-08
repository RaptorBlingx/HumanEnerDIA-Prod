"""
Production Data API Routes

Provides endpoints for querying production metrics, counts, and efficiency.
Correlates energy consumption with production output to calculate SEC (Specific Energy Consumption).
"""

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from asyncpg import Record

from database import db, get_machines

router = APIRouter(prefix="/production", tags=["Production"])


@router.get("/{machine_id}")
async def get_production_data(
    machine_id: UUID,
    start_time: datetime = Query(
        ...,
        description="Start of time range (ISO8601 format)",
        example="2025-10-19T00:00:00Z"
    ),
    end_time: datetime = Query(
        ...,
        description="End of time range (ISO8601 format)",
        example="2025-10-20T23:59:59Z"
    ),
    interval: str = Query(
        "1hour",
        description="Time bucket interval: 5min, 15min, 1hour, 1day",
        regex="^(5min|15min|1hour|1day)$"
    )
):
    """
    Get production data and energy efficiency metrics for a machine.
    
    **Returns:**
    - Production counts (total, good, bad)
    - Energy consumption correlated with production
    - SEC (Specific Energy Consumption) in kWh/unit
    - Quality metrics (yield percentage)
    - Throughput and efficiency trends
    
    **OVOS Use Cases:**
    - "How much did Compressor-1 produce today?"
    - "What's the energy efficiency of Injection-Molding-1?"
    - "Show me production output for yesterday"
    
    **Example:**
    ```
    GET /api/v1/production/c0000000-0000-0000-0000-000000000001?start_time=2025-10-19T00:00:00Z&end_time=2025-10-20T00:00:00Z&interval=1hour
    ```
    """
    
    # Verify machine exists
    try:
        machines = await get_machines()
        machine = next((m for m in machines if str(m["id"]) == str(machine_id)), None)
        if not machine:
            raise HTTPException(status_code=404, detail=f"Machine {machine_id} not found")
        machine_name = machine["name"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching machine: {str(e)}")
    
    # Convert interval to PostgreSQL interval format
    interval_map = {
        "5min": "5 minutes",
        "15min": "15 minutes",
        "1hour": "1 hour",
        "1day": "1 day"
    }
    pg_interval = interval_map.get(interval, "1 hour")
    
    # Calculate time period
    duration_hours = (end_time - start_time).total_seconds() / 3600
    
    # Query production data with energy correlation
    query = f"""
        WITH production_buckets AS (
            SELECT
                time_bucket('{pg_interval}'::interval, pd.time) AS bucket_time,
                COUNT(*) AS reading_count,
                SUM(pd.production_count) AS total_production,
                SUM(pd.production_count_good) AS good_units,
                SUM(pd.production_count_bad) AS bad_units,
                AVG(pd.throughput_units_per_hour) AS avg_throughput,
                AVG(pd.quality_score) AS avg_quality_score
            FROM production_data pd
            WHERE pd.machine_id = $1
                AND pd.time >= $2
                AND pd.time < $3
            GROUP BY bucket_time
            ORDER BY bucket_time
        ),
        energy_buckets AS (
            SELECT
                time_bucket('{pg_interval}'::interval, er.time) AS bucket_time,
                SUM(er.energy_kwh) AS total_energy_kwh,
                AVG(er.power_kw) AS avg_power_kw,
                MAX(er.power_kw) AS peak_power_kw
            FROM energy_readings er
            WHERE er.machine_id = $1
                AND er.time >= $2
                AND er.time < $3
            GROUP BY bucket_time
        )
        SELECT
            pb.bucket_time,
            pb.reading_count,
            COALESCE(pb.total_production, 0) AS production_count,
            COALESCE(pb.good_units, 0) AS good_units,
            COALESCE(pb.bad_units, 0) AS bad_units,
            COALESCE(pb.avg_throughput, 0) AS throughput_units_per_hour,
            COALESCE(pb.avg_quality_score, 0) AS quality_score,
            COALESCE(eb.total_energy_kwh, 0) AS energy_kwh,
            COALESCE(eb.avg_power_kw, 0) AS avg_power_kw,
            COALESCE(eb.peak_power_kw, 0) AS peak_power_kw,
            CASE
                WHEN COALESCE(pb.total_production, 0) > 0
                THEN COALESCE(eb.total_energy_kwh, 0) / pb.total_production
                ELSE 0
            END AS sec_kwh_per_unit,
            CASE
                WHEN (COALESCE(pb.good_units, 0) + COALESCE(pb.bad_units, 0)) > 0
                THEN (COALESCE(pb.good_units, 0)::float / (pb.good_units + pb.bad_units)) * 100
                ELSE 0
            END AS yield_percent
        FROM production_buckets pb
        LEFT JOIN energy_buckets eb ON pb.bucket_time = eb.bucket_time
        ORDER BY pb.bucket_time;
    """
    
    try:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(query, machine_id, start_time, end_time)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    if not rows:
        return {
            "machine_id": str(machine_id),
            "machine_name": machine_name,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "interval": interval,
            "message": "No production data found for this period",
            "timeline": [],
            "summary": {
                "total_production": 0,
                "good_units": 0,
                "bad_units": 0,
                "avg_yield_percent": 0,
                "total_energy_kwh": 0,
                "avg_sec_kwh_per_unit": 0
            }
        }
    
    # Build timeline
    timeline = []
    for row in rows:
        timeline.append({
            "timestamp": row["bucket_time"].isoformat(),
            "production_count": int(row["production_count"]),
            "good_units": int(row["good_units"]),
            "bad_units": int(row["bad_units"]),
            "yield_percent": round(float(row["yield_percent"]), 2),
            "throughput_units_per_hour": round(float(row["throughput_units_per_hour"]), 2),
            "quality_score": round(float(row["quality_score"]), 2),
            "energy_kwh": round(float(row["energy_kwh"]), 3),
            "avg_power_kw": round(float(row["avg_power_kw"]), 3),
            "peak_power_kw": round(float(row["peak_power_kw"]), 3),
            "sec_kwh_per_unit": round(float(row["sec_kwh_per_unit"]), 6),
            "reading_count": int(row["reading_count"])
        })
    
    # Calculate summary statistics
    total_production = sum(int(row["production_count"]) for row in rows)
    total_good = sum(int(row["good_units"]) for row in rows)
    total_bad = sum(int(row["bad_units"]) for row in rows)
    total_energy = sum(float(row["energy_kwh"]) for row in rows)
    
    avg_yield = (total_good / (total_good + total_bad) * 100) if (total_good + total_bad) > 0 else 0
    avg_sec = (total_energy / total_production) if total_production > 0 else 0
    avg_throughput = sum(float(row["throughput_units_per_hour"]) for row in rows) / len(rows) if rows else 0
    avg_quality = sum(float(row["quality_score"]) for row in rows) / len(rows) if rows else 0
    
    return {
        "machine_id": str(machine_id),
        "machine_name": machine_name,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "interval": interval,
        "time_period": {
            "duration_hours": round(duration_hours, 2),
            "duration_days": round(duration_hours / 24, 2)
        },
        "timeline": timeline,
        "summary": {
            "total_periods": len(rows),
            "total_production": total_production,
            "good_units": total_good,
            "bad_units": total_bad,
            "avg_yield_percent": round(avg_yield, 2),
            "total_energy_kwh": round(total_energy, 3),
            "avg_sec_kwh_per_unit": round(avg_sec, 6),
            "avg_throughput_units_per_hour": round(avg_throughput, 2),
            "avg_quality_score": round(avg_quality, 2),
            "cost_usd": round(total_energy * 0.15, 2),  # $0.15/kWh
            "carbon_kg_co2": round(total_energy * 0.45, 2)  # 0.45 kg CO2/kWh
        }
    }
