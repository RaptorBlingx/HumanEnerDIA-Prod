"""
EnMS Analytics API - General Analytics Routes
==============================================
General analytics endpoints including rankings and comparisons.

Extracted from ovos.py as part of Phase 1 API cleanup.

Author: EnMS Team
Phase: 1 - API Cleanup & Refactoring
Date: November 5, 2025
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any
from datetime import datetime
import logging

from database import db, get_machines

logger = logging.getLogger(__name__)

router = APIRouter()

# Constants
ENERGY_RATE = 0.15  # $/kWh


@router.get("/analytics/top-consumers", tags=["Analytics"])
async def get_top_energy_consumers(
    metric: str = Query("energy", description="Metric to rank by: energy, cost, power, anomalies"),
    start_time: datetime = Query(None, description="Start of time range (ISO 8601) - defaults to today 00:00 UTC"),
    end_time: datetime = Query(None, description="End of time range (ISO 8601) - defaults to now"),
    limit: int = Query(5, description="Number of top consumers to return", ge=1, le=20)
) -> Dict[str, Any]:
    """
    Get top machines ranked by energy consumption metric.
    
    **Parameters:**
    - `metric`: Ranking metric - `energy`, `cost`, `power`, or `anomalies`
    - `start_time`: Start of time period (ISO 8601)
    - `end_time`: End of time period (ISO 8601)
    - `limit`: Number of results (1-20, default: 5)
    
    **Use Cases:**
    - "Which machine uses the most energy?"
    - "What are the top 3 energy consumers today?"
    - "Which machine costs the most to run?"
    
    **Example:**
    ```bash
    curl "http://localhost:8001/api/v1/analytics/top-consumers?metric=energy&start_time=2025-11-05T00:00:00Z&end_time=2025-11-05T23:59:59Z&limit=3"
    ```
    """
    
    try:
        # Set defaults if not provided
        if start_time is None:
            start_time = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        if end_time is None:
            end_time = datetime.utcnow()
        
        valid_metrics = ['energy', 'cost', 'power', 'anomalies']
        if metric not in valid_metrics:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid metric. Must be one of: {', '.join(valid_metrics)}"
            )
        
        machines = await get_machines()
        active_machines = [m for m in machines if m.get('is_active', True)]
        
        if not active_machines:
            return {
                "metric": metric,
                "time_period": {"start": start_time.isoformat(), "end": end_time.isoformat()},
                "total_value": 0.0,
                "unit": "",
                "ranking": [],
                "message": "No active machines found"
            }
        
        machine_ids = [m['id'] for m in active_machines]
        
        if metric in ['energy', 'cost', 'power']:
            energy_query = """
                SELECT 
                    machine_id,
                    SUM(total_energy_kwh) as total_energy,
                    AVG(avg_power_kw) as avg_power,
                    MAX(max_power_kw) as peak_power
                FROM energy_readings_1min
                WHERE bucket >= $1 AND bucket < $2 AND machine_id = ANY($3)
                GROUP BY machine_id
                ORDER BY total_energy DESC
            """
            
            async with db.pool.acquire() as conn:
                results = await conn.fetch(energy_query, start_time, end_time, machine_ids)
            
            if not results:
                return {
                    "metric": metric,
                    "time_period": {"start": start_time.isoformat(), "end": end_time.isoformat()},
                    "total_value": 0.0,
                    "unit": "kWh" if metric == "energy" else ("USD" if metric == "cost" else "kW"),
                    "ranking": [],
                    "message": "No data available for this time period"
                }
            
            total_energy = sum(float(r['total_energy'] or 0) for r in results)
            total_cost = total_energy * ENERGY_RATE
            
            ranking = []
            for idx, row in enumerate(results[:limit]):
                machine_id = str(row['machine_id'])
                machine = next((m for m in machines if str(m['id']) == machine_id), None)
                
                energy = float(row['total_energy'] or 0)
                cost = energy * ENERGY_RATE
                avg_power = float(row['avg_power'] or 0)
                
                if metric == 'energy':
                    value = energy
                    percentage = (energy / total_energy * 100) if total_energy > 0 else 0
                elif metric == 'cost':
                    value = cost
                    percentage = (cost / total_cost * 100) if total_cost > 0 else 0
                else:
                    value = avg_power
                    total_avg_power = sum(float(r['avg_power'] or 0) for r in results)
                    percentage = (avg_power / total_avg_power * 100) if total_avg_power > 0 else 0
                
                ranking.append({
                    "rank": idx + 1,
                    "machine_id": machine_id,
                    "machine_name": machine.get('name', 'Unknown') if machine else 'Unknown',
                    "machine_type": machine.get('type', 'unknown') if machine else 'unknown',
                    "value": round(value, 2),
                    "percentage": round(percentage, 1),
                    "energy_kwh": round(energy, 2),
                    "cost_usd": round(cost, 2),
                    "avg_power_kw": round(avg_power, 2)
                })
            
            if metric == 'energy':
                unit, total_value = "kWh", total_energy
            elif metric == 'cost':
                unit, total_value = "USD", total_cost
            else:
                unit, total_value = "kW", sum(float(r['avg_power'] or 0) for r in results)
            
            return {
                "metric": metric,
                "metric_label": {"energy": "Energy Consumption", "cost": "Energy Cost", "power": "Average Power Demand"}[metric],
                "time_period": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "duration_hours": round((end_time - start_time).total_seconds() / 3600, 2)
                },
                "total_value": round(total_value, 2),
                "unit": unit,
                "machines_analyzed": len(results),
                "ranking": ranking
            }
        
        else:  # anomalies metric
            anomaly_query = """
                SELECT 
                    machine_id,
                    COUNT(*) as anomaly_count,
                    SUM(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) as critical_count,
                    SUM(CASE WHEN severity = 'warning' THEN 1 ELSE 0 END) as warning_count,
                    SUM(CASE WHEN severity = 'normal' THEN 1 ELSE 0 END) as normal_count
                FROM anomalies
                WHERE detected_at >= $1 AND detected_at <= $2 AND machine_id = ANY($3)
                GROUP BY machine_id
                ORDER BY anomaly_count DESC
            """
            
            async with db.pool.acquire() as conn:
                results = await conn.fetch(anomaly_query, start_time, end_time, machine_ids)
            
            if not results:
                return {
                    "metric": "anomalies",
                    "time_period": {"start": start_time.isoformat(), "end": end_time.isoformat()},
                    "total_value": 0,
                    "unit": "anomalies",
                    "ranking": [],
                    "message": "No anomalies detected in this period"
                }
            
            total_anomalies = sum(int(r['anomaly_count']) for r in results)
            
            ranking = []
            for idx, row in enumerate(results[:limit]):
                machine_id = str(row['machine_id'])
                machine = next((m for m in machines if str(m['id']) == machine_id), None)
                
                count = int(row['anomaly_count'])
                percentage = (count / total_anomalies * 100) if total_anomalies > 0 else 0
                
                ranking.append({
                    "rank": idx + 1,
                    "machine_id": machine_id,
                    "machine_name": machine.get('name', 'Unknown') if machine else 'Unknown',
                    "machine_type": machine.get('type', 'unknown') if machine else 'unknown',
                    "value": count,
                    "percentage": round(percentage, 1),
                    "critical": int(row['critical_count']),
                    "warnings": int(row['warning_count']),
                    "normal": int(row['normal_count'])
                })
            
            return {
                "metric": "anomalies",
                "metric_label": "Anomaly Count",
                "time_period": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "duration_hours": round((end_time - start_time).total_seconds() / 3600, 2)
                },
                "total_value": total_anomalies,
                "unit": "anomalies",
                "machines_analyzed": len(results),
                "ranking": ranking
            }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating top consumers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error calculating top consumers: {str(e)}")
