"""
Comparative Analytics API Routes

Provides simplified machine comparison and ranking by various metrics.
Designed for quick OVOS queries like "Which machine uses the most energy?"
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from database import db, get_machines

router = APIRouter(prefix="/compare", tags=["Comparative Analytics"])


@router.get("/machines")
async def compare_machines(
    machine_ids: Optional[str] = Query(
        None,
        description="Comma-separated machine UUIDs (omit for all machines)",
        example="c0000000-0000-0000-0000-000000000001,c0000000-0000-0000-0000-000000000002"
    ),
    metric: str = Query(
        "energy",
        description="Comparison metric: energy, efficiency, cost, anomalies, production",
        regex="^(energy|efficiency|cost|anomalies|production)$"
    ),
    start_time: datetime = Query(
        ...,
        description="Start of comparison period (ISO8601)",
        example="2025-10-19T00:00:00Z"
    ),
    end_time: datetime = Query(
        ...,
        description="End of comparison period (ISO8601)",
        example="2025-10-20T23:59:59Z"
    )
):
    """
    Compare machines and rank them by a specific metric.
    
    **Available Metrics:**
    - `energy`: Total energy consumption (kWh) - higher = worse
    - `efficiency`: Energy per production unit (SEC) - lower = better
    - `cost`: Total energy cost ($) - higher = worse
    - `anomalies`: Number of anomalies detected - higher = worse
    - `production`: Total production output - higher = better
    
    **OVOS Use Cases:**
    - "Which machine uses the most energy?"
    - "Which machine is most efficient?"
    - "Which machine costs the most to run?"
    - "Which machine has the most alerts?"
    - "Which machine produced the most units?"
    
    **Example:**
    ```
    GET /api/v1/compare/machines?metric=energy&start_time=2025-10-19T00:00:00Z&end_time=2025-10-20T00:00:00Z
    GET /api/v1/compare/machines?machine_ids=uuid1,uuid2&metric=efficiency&start_time=...&end_time=...
    ```
    """
    
    # Determine which machines to compare
    if machine_ids:
        try:
            machine_uuid_list = [UUID(mid.strip()) for mid in machine_ids.split(",")]
            query_description = f"{len(machine_uuid_list)} selected machines"
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid machine_id format: {str(e)}")
    else:
        # Get all active machines
        all_machines = await get_machines(is_active=True)
        machine_uuid_list = [m["id"] for m in all_machines]
        query_description = "All active machines"
    
    if not machine_uuid_list:
        raise HTTPException(status_code=404, detail="No machines found")
    
    # Calculate time period
    duration_hours = (end_time - start_time).total_seconds() / 3600
    
    # Build query based on metric
    if metric == "energy":
        comparison_data = await _compare_energy(machine_uuid_list, start_time, end_time)
        ranking_order = "desc"  # Higher energy = worse rank
        metric_label = "Total Energy Consumption"
        metric_unit = "kWh"
    
    elif metric == "efficiency":
        comparison_data = await _compare_efficiency(machine_uuid_list, start_time, end_time)
        ranking_order = "asc"  # Lower SEC = better rank
        metric_label = "Specific Energy Consumption (SEC)"
        metric_unit = "kWh/unit"
    
    elif metric == "cost":
        comparison_data = await _compare_cost(machine_uuid_list, start_time, end_time)
        ranking_order = "desc"  # Higher cost = worse rank
        metric_label = "Total Energy Cost"
        metric_unit = "USD"
    
    elif metric == "anomalies":
        comparison_data = await _compare_anomalies(machine_uuid_list, start_time, end_time)
        ranking_order = "desc"  # More anomalies = worse rank
        metric_label = "Anomaly Count"
        metric_unit = "anomalies"
    
    elif metric == "production":
        comparison_data = await _compare_production(machine_uuid_list, start_time, end_time)
        ranking_order = "desc"  # Higher production = better rank (but inverted in response)
        metric_label = "Total Production Output"
        metric_unit = "units"
    
    else:
        raise HTTPException(status_code=400, detail=f"Invalid metric: {metric}")
    
    if not comparison_data:
        raise HTTPException(status_code=404, detail="No data found for comparison period")
    
    # Rank machines
    ranked = sorted(comparison_data, key=lambda x: x["metric_value"], reverse=(ranking_order == "desc"))
    
    # For production, higher is better, so invert rank meaning
    for idx, machine in enumerate(ranked):
        if metric == "production":
            machine["rank"] = idx + 1  # 1 = highest production = best
            machine["performance"] = "best" if idx == 0 else "worst" if idx == len(ranked) - 1 else "average"
        else:
            machine["rank"] = idx + 1  # 1 = highest energy/cost/anomalies = worst
            machine["performance"] = "worst" if idx == 0 else "best" if idx == len(ranked) - 1 else "average"
    
    # Generate insights
    best = ranked[-1] if metric == "production" else ranked[-1]
    worst = ranked[0] if metric == "production" else ranked[0]
    
    insights = []
    if metric == "energy":
        insights.append(f"{worst['machine_name']} consumed {worst['metric_value']:.1f} kWh ({worst['percentage']:.1f}% of total)")
        insights.append(f"{best['machine_name']} consumed only {best['metric_value']:.1f} kWh ({best['percentage']:.1f}% of total)")
        diff_percent = ((worst['metric_value'] - best['metric_value']) / best['metric_value']) * 100
        insights.append(f"{worst['machine_name']} used {diff_percent:.1f}% more energy than {best['machine_name']}")
    
    elif metric == "efficiency":
        insights.append(f"{best['machine_name']} is most efficient at {best['metric_value']:.6f} kWh/unit")
        insights.append(f"{worst['machine_name']} is least efficient at {worst['metric_value']:.6f} kWh/unit")
    
    elif metric == "cost":
        total_cost = sum(m['metric_value'] for m in ranked)
        insights.append(f"Total cost across all machines: ${total_cost:.2f}")
        insights.append(f"{worst['machine_name']} cost ${worst['metric_value']:.2f} ({worst['percentage']:.1f}% of total)")
        insights.append(f"{best['machine_name']} cost only ${best['metric_value']:.2f} ({best['percentage']:.1f}% of total)")
    
    elif metric == "anomalies":
        total_anomalies = sum(m['metric_value'] for m in ranked)
        insights.append(f"Total anomalies: {int(total_anomalies)} across {len(ranked)} machines")
        if worst['metric_value'] > 0:
            insights.append(f"{worst['machine_name']} had {int(worst['metric_value'])} anomalies (needs attention)")
        if best['metric_value'] == 0:
            insights.append(f"{best['machine_name']} had no anomalies (excellent performance)")
    
    elif metric == "production":
        total_production = sum(m['metric_value'] for m in ranked)
        insights.append(f"Total production: {int(total_production):,} units across {len(ranked)} machines")
        insights.append(f"{ranked[0]['machine_name']} produced {int(ranked[0]['metric_value']):,} units ({ranked[0]['percentage']:.1f}% of total)")
        insights.append(f"{ranked[-1]['machine_name']} produced only {int(ranked[-1]['metric_value']):,} units ({ranked[-1]['percentage']:.1f}% of total)")
    
    return {
        "metric": metric,
        "metric_label": metric_label,
        "metric_unit": metric_unit,
        "time_period": {
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
            "duration_hours": round(duration_hours, 2),
            "duration_days": round(duration_hours / 24, 2)
        },
        "query": query_description,
        "machines_count": len(ranked),
        "ranking": ranked,
        "best_performer": best["machine_name"],
        "worst_performer": worst["machine_name"],
        "insights": insights
    }


async def _compare_energy(machine_ids: List[UUID], start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
    """Compare machines by total energy consumption."""
    query = """
        SELECT
            m.id::text as machine_id,
            m.name as machine_name,
            m.type as machine_type,
            COALESCE(SUM(er.energy_kwh), 0) as total_energy
        FROM machines m
        LEFT JOIN energy_readings er ON m.id = er.machine_id
            AND er.time >= $2
            AND er.time < $3
        WHERE m.id = ANY($1::uuid[])
        GROUP BY m.id, m.name, m.type
        HAVING COALESCE(SUM(er.energy_kwh), 0) > 0
        ORDER BY total_energy DESC;
    """
    
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(query, machine_ids, start_time, end_time)
    
    if not rows:
        return []
    
    total = sum(float(row["total_energy"]) for row in rows)
    
    results = []
    for row in rows:
        energy = float(row["total_energy"])
        results.append({
            "machine_id": row["machine_id"],
            "machine_name": row["machine_name"],
            "machine_type": row["machine_type"],
            "metric_value": round(energy, 3),
            "percentage": round((energy / total * 100) if total > 0 else 0, 2)
        })
    
    return results


async def _compare_efficiency(machine_ids: List[UUID], start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
    """Compare machines by SEC (Specific Energy Consumption)."""
    # Use separate subqueries to avoid timeout on large tables
    query = """
        WITH energy_agg AS (
            SELECT
                machine_id,
                SUM(energy_kwh) as total_energy
            FROM energy_readings
            WHERE machine_id = ANY($1::uuid[])
                AND time >= $2
                AND time < $3
            GROUP BY machine_id
        ),
        production_agg AS (
            SELECT
                machine_id,
                SUM(production_count) as total_production
            FROM production_data
            WHERE machine_id = ANY($1::uuid[])
                AND time >= $2
                AND time < $3
            GROUP BY machine_id
        )
        SELECT
            m.id::text as machine_id,
            m.name as machine_name,
            m.type as machine_type,
            COALESCE(e.total_energy, 0) as total_energy,
            COALESCE(p.total_production, 0) as total_production
        FROM machines m
        JOIN production_agg p ON m.id = p.machine_id
        JOIN energy_agg e ON m.id = e.machine_id
        WHERE m.id = ANY($1::uuid[])
            AND p.total_production > 0;
    """
    
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(query, machine_ids, start_time, end_time)
    
    if not rows:
        return []
    
    results = []
    for row in rows:
        energy = float(row["total_energy"])
        production = int(row["total_production"])
        sec = energy / production if production > 0 else 0
        
        results.append({
            "machine_id": row["machine_id"],
            "machine_name": row["machine_name"],
            "machine_type": row["machine_type"],
            "metric_value": round(sec, 6),
            "total_energy_kwh": round(energy, 3),
            "total_production": production,
            "percentage": 0  # Not applicable for SEC
        })
    
    return results


async def _compare_cost(machine_ids: List[UUID], start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
    """Compare machines by total energy cost."""
    COST_PER_KWH = 0.15
    
    query = """
        SELECT
            m.id::text as machine_id,
            m.name as machine_name,
            m.type as machine_type,
            COALESCE(SUM(er.energy_kwh), 0) as total_energy
        FROM machines m
        LEFT JOIN energy_readings er ON m.id = er.machine_id
            AND er.time >= $2
            AND er.time < $3
        WHERE m.id = ANY($1::uuid[])
        GROUP BY m.id, m.name, m.type
        HAVING COALESCE(SUM(er.energy_kwh), 0) > 0;
    """
    
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(query, machine_ids, start_time, end_time)
    
    if not rows:
        return []
    
    total_cost = sum(float(row["total_energy"]) * COST_PER_KWH for row in rows)
    
    results = []
    for row in rows:
        energy = float(row["total_energy"])
        cost = energy * COST_PER_KWH
        
        results.append({
            "machine_id": row["machine_id"],
            "machine_name": row["machine_name"],
            "machine_type": row["machine_type"],
            "metric_value": round(cost, 2),
            "total_energy_kwh": round(energy, 3),
            "percentage": round((cost / total_cost * 100) if total_cost > 0 else 0, 2)
        })
    
    return results


async def _compare_anomalies(machine_ids: List[UUID], start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
    """Compare machines by anomaly count."""
    query = """
        SELECT
            m.id::text as machine_id,
            m.name as machine_name,
            m.type as machine_type,
            COUNT(a.id) as anomaly_count,
            SUM(CASE WHEN a.severity = 'critical' THEN 1 ELSE 0 END) as critical_count,
            SUM(CASE WHEN a.severity = 'warning' THEN 1 ELSE 0 END) as warning_count
        FROM machines m
        LEFT JOIN anomalies a ON m.id = a.machine_id
            AND a.detected_at >= $2
            AND a.detected_at < $3
        WHERE m.id = ANY($1::uuid[])
        GROUP BY m.id, m.name, m.type
        ORDER BY anomaly_count DESC;
    """
    
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(query, machine_ids, start_time, end_time)
    
    if not rows:
        return []
    
    total_anomalies = sum(int(row["anomaly_count"]) for row in rows)
    
    results = []
    for row in rows:
        count = int(row["anomaly_count"])
        
        results.append({
            "machine_id": row["machine_id"],
            "machine_name": row["machine_name"],
            "machine_type": row["machine_type"],
            "metric_value": count,
            "critical_anomalies": int(row["critical_count"]),
            "warning_anomalies": int(row["warning_count"]),
            "percentage": round((count / total_anomalies * 100) if total_anomalies > 0 else 0, 2)
        })
    
    return results


async def _compare_production(machine_ids: List[UUID], start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
    """Compare machines by total production output."""
    query = """
        SELECT
            m.id::text as machine_id,
            m.name as machine_name,
            m.type as machine_type,
            COALESCE(SUM(pd.production_count), 0) as total_production,
            COALESCE(SUM(pd.production_count_good), 0) as good_units,
            COALESCE(SUM(pd.production_count_bad), 0) as bad_units
        FROM machines m
        LEFT JOIN production_data pd ON m.id = pd.machine_id
            AND pd.time >= $2
            AND pd.time < $3
        WHERE m.id = ANY($1::uuid[])
        GROUP BY m.id, m.name, m.type
        HAVING COALESCE(SUM(pd.production_count), 0) > 0;
    """
    
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(query, machine_ids, start_time, end_time)
    
    if not rows:
        return []
    
    total_production = sum(int(row["total_production"]) for row in rows)
    
    results = []
    for row in rows:
        production = int(row["total_production"])
        good = int(row["good_units"])
        bad = int(row["bad_units"])
        yield_pct = (good / production * 100) if production > 0 else 0
        
        results.append({
            "machine_id": row["machine_id"],
            "machine_name": row["machine_name"],
            "machine_type": row["machine_type"],
            "metric_value": production,
            "good_units": good,
            "bad_units": bad,
            "yield_percent": round(yield_pct, 2),
            "percentage": round((production / total_production * 100) if total_production > 0 else 0, 2)
        })
    
    return results
