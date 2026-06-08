"""
EnMS Analytics - Machines API Routes
=====================================
API endpoints for machine information.
"""

from fastapi import APIRouter, Query, HTTPException
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime

from database import get_machines, get_machine_by_id, db

router = APIRouter()

# Constants
# Removed hardcoded rates - using database functions instead


@router.get("/machines", tags=["Machines"])
async def list_machines(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search by machine name (case-insensitive partial match)")
) -> List[Dict[str, Any]]:
    """
    Get list of all machines with optional search.
    
    **Parameters:**
    - `is_active`: Filter by active status (optional)
    - `search`: Search by machine name - case-insensitive partial match (optional)
    
    **Returns:**
    - List of machine objects with basic information
    
    **OVOS Integration:**
    - Use `search` parameter to resolve machine names to UUIDs
    - Enables voice queries like "Tell me about Compressor-1"
    
    **Example:**
    ```
    GET /api/v1/machines
    GET /api/v1/machines?is_active=true
    GET /api/v1/machines?search=compressor
    GET /api/v1/machines?search=Compressor-1
    GET /api/v1/machines?search=hvac&is_active=true
    ```
    """
    machines = await get_machines(is_active=is_active)
    
    # Apply search filter if provided
    if search:
        search_lower = search.lower()
        machines = [
            machine for machine in machines
            if search_lower in machine.get("name", "").lower()
        ]
    
    return machines


@router.get("/machines/{machine_id}", tags=["Machines"])
async def get_machine(
    machine_id: UUID
) -> Dict[str, Any]:
    """
    Get detailed information about a specific machine.
    
    **Parameters:**
    - `machine_id`: Machine UUID
    
    **Returns:**
    - Machine object with full details
    
    **Example:**
    ```
    GET /api/v1/machines/c0000000-0000-0000-0000-000000000001
    ```
    """
    machine = await get_machine_by_id(machine_id)
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    return machine


@router.get("/machines/{machine_id}/status-history", tags=["Machines"])
async def get_machine_status_history(
    machine_id: UUID,
    start_time: datetime = Query(..., description="Start time (ISO 8601)"),
    end_time: datetime = Query(..., description="End time (ISO 8601)"),
    interval: str = Query("1hour", description="Aggregation interval (5min, 15min, 1hour)")
) -> Dict[str, Any]:
    """
    Get machine status history with running/stopped timeline.
    
    **NEW FEATURE** - Track when machines were online/offline.
    
    **Status Classification:**
    - `running`: power_kw > 5 kW
    - `idle`: 0.5 kW < power_kw ≤ 5 kW  
    - `stopped`: power_kw ≤ 0.5 kW
    
    **Parameters:**
    - `machine_id`: Machine UUID
    - `start_time`: Start of history period (ISO 8601)
    - `end_time`: End of history period (ISO 8601)
    - `interval`: Time bucket size (5min, 15min, 1hour, default: 1hour)
    
    **Returns:**
    - Timeline of machine status with duration percentages
    - Total running/idle/stopped times
    - Status transitions count
    
    **Use Cases:**
    - "When was Compressor-1 offline yesterday?"
    - "Show me machine uptime for last week"
    - "What's the operating pattern for HVAC-Main?"
    
    **Example:**
    ```
    GET /api/v1/machines/{id}/status-history?start_time=2025-10-19T00:00:00Z&end_time=2025-10-20T00:00:00Z&interval=1hour
    ```
    """
    # Verify machine exists
    machine = await get_machine_by_id(machine_id)
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    
    # Map interval names to PostgreSQL interval syntax
    interval_map = {
        "5min": "5 minutes",
        "15min": "15 minutes",
        "1hour": "1 hour",
        "1day": "1 day"
    }
    
    if interval not in interval_map:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid interval. Must be one of: {', '.join(interval_map.keys())}"
        )
    
    pg_interval = interval_map[interval]
    
    # Query to calculate status history with time buckets
    # Note: interval must be hardcoded for time_bucket function
    query = f"""
        WITH time_buckets AS (
            SELECT
                time_bucket('{pg_interval}'::interval, time) as bucket,
                AVG(power_kw) as avg_power_kw,
                MAX(power_kw) as max_power_kw,
                MIN(power_kw) as min_power_kw,
                COUNT(*) as reading_count
            FROM energy_readings
            WHERE machine_id = $1
                AND time >= $2
                AND time < $3
            GROUP BY bucket
            ORDER BY bucket
        ),
        status_classified AS (
            SELECT
                bucket,
                avg_power_kw,
                max_power_kw,
                min_power_kw,
                reading_count,
                CASE
                    WHEN avg_power_kw > 5 THEN 'running'
                    WHEN avg_power_kw > 0.5 THEN 'idle'
                    ELSE 'stopped'
                END as status
            FROM time_buckets
        )
        SELECT
            bucket,
            avg_power_kw,
            max_power_kw,
            min_power_kw,
            status,
            reading_count
        FROM status_classified
        ORDER BY bucket;
    """
    
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(query, machine_id, start_time, end_time)
    
    if not rows:
        return {
            "machine_id": str(machine_id),
            "machine_name": machine["name"],
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "interval": interval,
            "message": "No data available for this time period",
            "timeline": [],
            "summary": {
                "total_periods": 0,
                "running_periods": 0,
                "idle_periods": 0,
                "stopped_periods": 0,
                "running_percent": 0.0,
                "idle_percent": 0.0,
                "stopped_percent": 0.0,
                "transitions": 0
            }
        }
    
    # Build timeline
    timeline = []
    prev_status = None
    transitions = 0
    status_counts = {"running": 0, "idle": 0, "stopped": 0}
    
    for row in rows:
        status = row["status"]
        status_counts[status] += 1
        
        if prev_status and prev_status != status:
            transitions += 1
        
        timeline.append({
            "timestamp": row["bucket"].isoformat(),
            "status": status,
            "avg_power_kw": float(row["avg_power_kw"]),
            "max_power_kw": float(row["max_power_kw"]),
            "min_power_kw": float(row["min_power_kw"]),
            "reading_count": row["reading_count"]
        })
        
        prev_status = status
    
    total_periods = len(rows)
    
    return {
        "machine_id": str(machine_id),
        "machine_name": machine["name"],
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "interval": interval,
        "timeline": timeline,
        "summary": {
            "total_periods": total_periods,
            "running_periods": status_counts["running"],
            "idle_periods": status_counts["idle"],
            "stopped_periods": status_counts["stopped"],
            "running_percent": round((status_counts["running"] / total_periods) * 100, 2) if total_periods > 0 else 0.0,
            "idle_percent": round((status_counts["idle"] / total_periods) * 100, 2) if total_periods > 0 else 0.0,
            "stopped_percent": round((status_counts["stopped"] / total_periods) * 100, 2) if total_periods > 0 else 0.0,
            "transitions": transitions,
            "uptime_percent": round(((status_counts["running"] + status_counts["idle"]) / total_periods) * 100, 2) if total_periods > 0 else 0.0
        }
    }


@router.get("/machines/status/{machine_name}", tags=["Machines"])
async def get_machine_status_by_name(machine_name: str) -> Dict[str, Any]:
    """
    Get comprehensive machine status by name (no UUID required).
    
    **Voice-assistant optimized** - Resolve machine name and return complete status.
    
    **Parameters:**
    - `machine_name`: Machine name (case-insensitive, partial match supported)
    
    **Returns:**
    - Machine identification (id, name, type, location)
    - Current status (running/idle/stopped, power, temperature, last reading)
    - Today's statistics (energy, cost, uptime)
    - Recent anomalies (count, severity breakdown, latest anomaly)
    - Production data (units produced, SEC)
    
    **Example:**
    ```bash
    curl "http://localhost:8001/api/v1/machines/status/Compressor-1"
    curl "http://localhost:8001/api/v1/machines/status/compressor"
    ```
    
    **OVOS Use Cases:**
    - "What's the status of Compressor-1?"
    - "How is the injection molding machine doing?"
    - "Tell me about the HVAC system"
    
    **Voice Response Template:**
    "Compressor-1 is currently running at 28.5 kilowatts. Temperature is 
    45.2 degrees celsius. Today it has consumed 245 kilowatt hours costing 
    $36.87. Uptime is 93.75%. There are 3 anomalies today: 1 critical and 
    2 warnings. The latest warning was detected at 9:45 AM for power spike."
    """
    try:
        # Get all machines and search for matching name
        machines = await get_machines()
        
        # Search for machine (case-insensitive partial match)
        search_lower = machine_name.lower()
        matched_machines = [
            machine for machine in machines
            if search_lower in machine.get('name', '').lower()
        ]
        
        if not matched_machines:
            raise HTTPException(
                status_code=404,
                detail=f"No machine found matching name: {machine_name}"
            )
        
        if len(matched_machines) > 1:
            names = [m.get('name') for m in matched_machines]
            raise HTTPException(
                status_code=400,
                detail=f"Multiple machines found matching '{machine_name}': {names}. Please be more specific."
            )
        
        machine = matched_machines[0]
        machine_id = machine.get('id')
        
        # Get today's date range
        today = datetime.utcnow().date()
        start_of_day = datetime.combine(today, datetime.min.time())
        end_of_day = datetime.combine(today, datetime.max.time())
        
        async with db.pool.acquire() as conn:
            # Get latest reading for current status
            latest_reading = await conn.fetchrow("""
                SELECT time, power_kw, energy_kwh
                FROM energy_readings
                WHERE machine_id = $1
                ORDER BY time DESC
                LIMIT 1
            """, machine_id)
            
            # Get today's energy statistics
            today_stats = await conn.fetchrow("""
                SELECT 
                    SUM(energy_kwh) as total_energy,
                    AVG(power_kw) as avg_power,
                    MAX(power_kw) as peak_power,
                    COUNT(*) as reading_count
                FROM energy_readings
                WHERE machine_id = $1
                    AND time >= $2
                    AND time <= $3
            """, machine_id, start_of_day, end_of_day)
            
            # Get today's anomalies
            anomalies = await conn.fetch("""
                SELECT 
                    id,
                    detected_at,
                    anomaly_type,
                    severity,
                    metric_name,
                    metric_value,
                    deviation_percent
                FROM anomalies
                WHERE machine_id = $1
                    AND detected_at >= $2
                    AND detected_at <= $3
                ORDER BY detected_at DESC
            """, machine_id, start_of_day, end_of_day)
            
            # Get production data for today
            production = await conn.fetchrow("""
                SELECT 
                    SUM(production_count) as total_units,
                    SUM(production_count_good) as total_good,
                    SUM(production_count_bad) as total_bad
                FROM production_data
                WHERE machine_id = $1
                    AND time >= $2
                    AND time <= $3
            """, machine_id, start_of_day, end_of_day)
        
        # Calculate current status
        current_status = None
        if latest_reading:
            power_kw = float(latest_reading['power_kw'])
            
            # Determine operational status based on power
            if power_kw > 5.0:  # Running threshold
                status = "running"
            elif power_kw > 0.5:  # Idle threshold
                status = "idle"
            else:
                status = "stopped"
            
            current_status = {
                "status": status,
                "power_kw": round(power_kw, 2),
                "last_reading": latest_reading['time'].isoformat()
            }
        
        # Calculate today's statistics
        total_energy = float(today_stats['total_energy']) if today_stats['total_energy'] else 0.0
        
        # Use SQL functions for cost and uptime to ensure consistency
        async with db.pool.acquire() as conn:
            # Calculate Cost
            cost_row = await conn.fetchrow(
                "SELECT total_cost FROM calculate_energy_cost($1, $2, $3)", 
                machine_id, start_of_day, end_of_day
            )
            total_cost = float(cost_row['total_cost']) if cost_row and cost_row['total_cost'] else 0.0
            
            # Calculate Uptime
            uptime_row = await conn.fetchrow(
                "SELECT running_hours, utilization_percent FROM get_machine_operating_hours($1, $2, $3)", 
                machine_id, start_of_day, end_of_day
            )
            uptime_hours = float(uptime_row['running_hours']) if uptime_row and uptime_row['running_hours'] else 0.0
            uptime_percent = float(uptime_row['utilization_percent']) if uptime_row and uptime_row['utilization_percent'] else 0.0
        
        today_statistics = {
            "energy_kwh": round(total_energy, 2),
            "cost_usd": round(total_cost, 2),
            "avg_power_kw": round(float(today_stats['avg_power']), 2) if today_stats['avg_power'] else 0.0,
            "peak_power_kw": round(float(today_stats['peak_power']), 2) if today_stats['peak_power'] else 0.0,
            "uptime_hours": round(uptime_hours, 2),
            "uptime_percent": round(uptime_percent, 2)
        }
        
        # Process anomalies
        anomaly_counts = {"critical": 0, "warning": 0, "normal": 0}
        latest_anomaly = None
        
        for anomaly in anomalies:
            severity = anomaly['severity']
            if severity in anomaly_counts:
                anomaly_counts[severity] += 1
            
            if not latest_anomaly:
                # Build description from available fields
                description = f"{anomaly['anomaly_type']}"
                if anomaly['metric_name']:
                    description += f" - {anomaly['metric_name']}"
                if anomaly['deviation_percent']:
                    description += f" ({float(anomaly['deviation_percent']):.1f}% deviation)"
                
                latest_anomaly = {
                    "anomaly_id": str(anomaly['id']),
                    "detected_at": anomaly['detected_at'].isoformat(),
                    "type": anomaly['anomaly_type'],
                    "severity": severity,
                    "description": description
                }
        
        recent_anomalies = {
            "count": len(anomalies),
            "critical": anomaly_counts['critical'],
            "warnings": anomaly_counts['warning'],
            "normal": anomaly_counts['normal'],
            "latest": latest_anomaly
        }
        
        # Process production data
        production_today = None
        if production and production['total_units'] and production['total_units'] > 0:
            total_units = int(production['total_units'])
            total_good = int(production['total_good']) if production['total_good'] else 0
            total_bad = int(production['total_bad']) if production['total_bad'] else 0
            quality_percent = (total_good / total_units * 100) if total_units > 0 else 0.0
            
            production_today = {
                "units_produced": total_units,
                "units_good": total_good,
                "units_bad": total_bad,
                "quality_percent": round(quality_percent, 2)
            }
        
        # Build response
        response = {
            "machine_id": str(machine_id),
            "machine_name": machine.get('name'),
            "machine_type": machine.get('type'),
            "location": machine.get('factory_location'),
            "is_active": machine.get('is_active'),
            "current_status": current_status,
            "today_stats": today_statistics,
            "recent_anomalies": recent_anomalies,
            "production_today": production_today,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting machine status: {str(e)}")
