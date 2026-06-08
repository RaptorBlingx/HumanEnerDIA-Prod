"""
EnMS Analytics API - Factory Analytics Routes
==============================================
Factory-level energy analytics and summary endpoints.

Extracted from ovos.py as part of Phase 1 API cleanup.
Provides comprehensive factory-wide energy metrics.

Author: EnMS Team
Phase: 1 - API Cleanup & Refactoring
Date: November 5, 2025
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from datetime import datetime, timedelta
import logging

from database import db, get_machines

logger = logging.getLogger(__name__)

router = APIRouter()

# Constants
# Removed hardcoded rates - using database functions instead


@router.get("/factory/summary", tags=["Factory Analytics"])
async def get_factory_summary() -> Dict[str, Any]:
    """
    Get comprehensive factory-level energy overview.
    
    **Single API call returns all key metrics:**
    - Energy metrics (today's total, current power, average)
    - Cost estimates (today and monthly projection)
    - Machine status counts (total, active, idle, stopped)
    - Anomaly counts by severity
    - Top energy consumer information
    - Latest anomaly details
    
    **Use Cases:**
    - "Give me a system overview"
    - "What's the current factory status?"
    - "How much energy are we using today?"
    
    **Example:**
    ```bash
    curl "http://localhost:8001/api/v1/factory/summary"
    ```
    
    **Response:** Complete factory snapshot with operational status
    """
    
    try:
        # Use UTC to match machines.py logic
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        # End of day (23:59:59) to ensure we capture all data for "today"
        today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # Get all active machines
        machines = await get_machines()
        active_machines = [m for m in machines if m.get('is_active', True)]
        
        # Initialize response structure
        response = {
            "timestamp": now.isoformat(),
            "status": "operational",
            "energy": {
                "total_kwh_today": 0.0,
                "current_power_kw": 0.0,
                "avg_power_kw": 0.0
            },
            "costs": {
                "total_usd_today": 0.0,
                "estimated_month": 0.0
            },
            "machines": {
                "total": len(active_machines),
                "active": 0,
                "idle": 0,
                "stopped": 0
            },
            "anomalies": {
                "critical": 0,
                "warnings": 0,
                "normal": 0,
                "total_today": 0
            },
            "top_consumer": None,
            "latest_anomaly": None
        }
        
        if not active_machines:
            response["status"] = "no_machines"
            return response
            
        # ===== ENERGY & COST METRICS =====
        # Calculate global summary by aggregating all machines
        # This ensures we cover ALL factories, not just the first one found
        
        energy_query = """
            SELECT 
                machine_id,
                SUM(energy_kwh) as total_energy,
                AVG(power_kw) as avg_power,
                MAX(power_kw) as max_power
            FROM energy_readings
            WHERE time >= $1 AND time <= $2
            GROUP BY machine_id
        """
        
        async with db.pool.acquire() as conn:
            energy_results = await conn.fetch(energy_query, today_start, today_end)
        
        logger.info(f"Factory Summary: Found {len(energy_results)} machines with energy data")
        found_ids = [str(r['machine_id']) for r in energy_results]
        logger.info(f"Factory Summary: Machine IDs: {found_ids}")

        total_avg_power = 0.0
        total_energy_global = 0.0
        machine_energies = {}
        
        for row in energy_results:
            machine_id = str(row['machine_id'])
            energy = float(row['total_energy'] or 0)
            avg_power = float(row['avg_power'] or 0)
            
            total_avg_power += avg_power
            total_energy_global += energy
            
            machine_energies[machine_id] = {
                'energy': energy,
                'avg_power': avg_power,
                'max_power': float(row['max_power'] or 0)
            }
        
        response["energy"]["avg_power_kw"] = round(total_avg_power, 2)
        response["energy"]["total_kwh_today"] = round(total_energy_global, 2)
        
        # Calculate global cost
        # We need to calculate cost for each machine and sum it up
        # Using calculate_energy_cost SQL function for accuracy
        total_cost_global = 0.0
        
        async with db.pool.acquire() as conn:
            # We can optimize this by calling it once per machine in parallel or loop
            # For 8 machines, a loop is fine
            for m in active_machines:
                mid = m['id']
                cost_row = await conn.fetchrow(
                    "SELECT total_cost FROM calculate_energy_cost($1, $2, $3)", 
                    mid, today_start, now
                )
                if cost_row and cost_row['total_cost']:
                    total_cost_global += float(cost_row['total_cost'])
                    
        response["costs"]["total_usd_today"] = round(total_cost_global, 2)

        # Get current power
        current_power_query = """
            SELECT DISTINCT ON (machine_id)
                machine_id,
                power_kw,
                time
            FROM energy_readings
            WHERE time >= $1
            ORDER BY machine_id, time DESC
        """
        
        async with db.pool.acquire() as conn:
            current_readings = await conn.fetch(current_power_query, now - timedelta(minutes=5))
        
        current_total_power = sum(float(r['power_kw'] or 0) for r in current_readings)
        response["energy"]["current_power_kw"] = round(current_total_power, 2)
        
        # ===== COST PROJECTION =====
        # Use the cost from SQL function
        total_cost_today = response["costs"]["total_usd_today"]
        
        days_in_month = 30
        day_of_month = now.day
        if day_of_month > 0:
            estimated_month = (total_cost_today / day_of_month) * days_in_month
            response["costs"]["estimated_month"] = round(estimated_month, 2)
        
        # ===== MACHINE STATUS COUNTS =====
        active_count = 0
        idle_count = 0
        stopped_count = 0
        
        for reading in current_readings:
            power = float(reading['power_kw'] or 0)
            if power > 5.0:
                active_count += 1
            elif power > 0.5:
                idle_count += 1
            else:
                stopped_count += 1
        
        response["machines"]["active"] = active_count
        response["machines"]["idle"] = idle_count
        response["machines"]["stopped"] = stopped_count
        
        # ===== ANOMALY COUNTS =====
        anomaly_query = """
            SELECT 
                severity,
                COUNT(*) as count
            FROM anomalies
            WHERE detected_at >= $1 AND detected_at <= $2
            GROUP BY severity
        """
        
        async with db.pool.acquire() as conn:
            anomaly_results = await conn.fetch(anomaly_query, today_start, now)
        
        for row in anomaly_results:
            severity = row['severity']
            count = int(row['count'])
            
            if severity == 'critical':
                response["anomalies"]["critical"] = count
            elif severity == 'warning':
                response["anomalies"]["warnings"] = count
            elif severity == 'normal':
                response["anomalies"]["normal"] = count
        
        response["anomalies"]["total_today"] = sum([
            response["anomalies"]["critical"],
            response["anomalies"]["warnings"],
            response["anomalies"]["normal"]
        ])
        
        # ===== TOP CONSUMER =====
        if machine_energies:
            top_machine_id = max(machine_energies.items(), key=lambda x: x[1]['energy'])[0]
            top_energy = machine_energies[top_machine_id]['energy']
            
            top_machine = next((m for m in machines if str(m['id']) == top_machine_id), None)
            
            # Use the total from response
            total_kwh = response["energy"]["total_kwh_today"]
            
            if top_machine and total_kwh > 0:
                response["top_consumer"] = {
                    "machine_id": top_machine_id,
                    "machine_name": top_machine.get('name', 'Unknown'),
                    "machine_type": top_machine.get('type', 'unknown'),
                    "energy_kwh": round(top_energy, 2),
                    "percent_of_total": round((top_energy / total_kwh) * 100, 1)
                }
        
        # ===== LATEST ANOMALY =====
        latest_anomaly_query = """
            SELECT 
                a.id,
                a.machine_id,
                a.detected_at,
                a.severity,
                a.anomaly_type,
                a.is_resolved,
                m.name as machine_name
            FROM anomalies a
            LEFT JOIN machines m ON a.machine_id = m.id
            ORDER BY a.detected_at DESC
            LIMIT 1
        """
        
        async with db.pool.acquire() as conn:
            latest = await conn.fetchrow(latest_anomaly_query)
        
        if latest:
            response["latest_anomaly"] = {
                "anomaly_id": str(latest['id']),
                "machine_id": str(latest['machine_id']),
                "machine_name": latest['machine_name'] or 'Unknown',
                "detected_at": latest['detected_at'].isoformat(),
                "severity": latest['severity'],
                "type": latest['anomaly_type'] or 'unknown',
                "is_resolved": latest['is_resolved']
            }
        
        # Determine overall system status
        if response["anomalies"]["critical"] > 5:
            response["status"] = "critical_alerts"
        elif response["anomalies"]["critical"] > 0:
            response["status"] = "attention_required"
        elif response["anomalies"]["warnings"] > 10:
            response["status"] = "warnings_present"
        else:
            response["status"] = "operational"
        
        return response
        
    except Exception as e:
        logger.error(f"Error generating factory summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating summary: {str(e)}")
