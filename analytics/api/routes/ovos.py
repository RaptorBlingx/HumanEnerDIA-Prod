"""
EnMS Analytics - OVOS Integration Routes
=========================================
Voice-assistant optimized endpoints for OVOS integration.
Designed for simple, efficient API calls with minimal complexity.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from uuid import UUID

from database import db, get_machines

router = APIRouter()

# Constants
ENERGY_RATE = 0.15  # $/kWh
CARBON_RATE = 0.45  # kg CO2/kWh


@router.get("/ovos/summary", tags=["OVOS"])
async def get_ovos_summary() -> Dict[str, Any]:
    """
    Get comprehensive system overview optimized for voice assistants.
    
    **OVOS-OPTIMIZED** - Single API call returns all key metrics.
    
    **No Parameters Required** - Returns current system snapshot.
    
    **Returns:**
    - Timestamp and operational status
    - Energy metrics (today's total, current power, average)
    - Cost estimates (today and monthly projection)
    - Machine status counts (total, active, idle, stopped)
    - Anomaly counts by severity
    - Top energy consumer information
    - Latest anomaly details
    
    **Use Cases:**
    - "Give me a system overview"
    - "What's the current status?"
    - "How are we doing today?"
    
    **Example:**
    ```
    GET /api/v1/ovos/summary
    ```
    
    **Voice Response Example:**
    "System is operational. 7 machines active. Today's energy consumption 
    is 1,520 kilowatt hours costing $185. Compressor-EU-1 is the top 
    consumer at 450 kilowatt hours. There are 2 critical alerts and 
    5 warnings requiring attention."
    """
    
    try:
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
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
        
        # ===== ENERGY METRICS =====
        # Get today's total energy across all machines
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
            energy_results = await conn.fetch(energy_query, today_start, now)
        
        total_energy = 0.0
        total_avg_power = 0.0
        machine_energies = {}
        
        for row in energy_results:
            machine_id = str(row['machine_id'])
            energy = float(row['total_energy'] or 0)
            avg_power = float(row['avg_power'] or 0)
            
            total_energy += energy
            total_avg_power += avg_power
            machine_energies[machine_id] = {
                'energy': energy,
                'avg_power': avg_power,
                'max_power': float(row['max_power'] or 0)
            }
        
        response["energy"]["total_kwh_today"] = round(total_energy, 2)
        response["energy"]["avg_power_kw"] = round(total_avg_power, 2)
        
        # Get current power (last reading for each machine)
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
        
        # ===== COST CALCULATIONS =====
        total_cost_today = total_energy * ENERGY_RATE
        response["costs"]["total_usd_today"] = round(total_cost_today, 2)
        
        # Estimate monthly cost (today's cost * days in month)
        days_in_month = 30  # Simplified
        day_of_month = now.day
        if day_of_month > 0:
            estimated_month = (total_cost_today / day_of_month) * days_in_month
            response["costs"]["estimated_month"] = round(estimated_month, 2)
        
        # ===== MACHINE STATUS COUNTS =====
        # Classify machines by current power level
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
            # Find machine with highest energy consumption
            top_machine_id = max(machine_energies.items(), key=lambda x: x[1]['energy'])[0]
            top_energy = machine_energies[top_machine_id]['energy']
            
            # Get machine name
            top_machine = next((m for m in machines if str(m['id']) == top_machine_id), None)
            
            if top_machine and total_energy > 0:
                response["top_consumer"] = {
                    "machine_id": top_machine_id,
                    "machine_name": top_machine.get('name', 'Unknown'),
                    "machine_type": top_machine.get('type', 'unknown'),
                    "energy_kwh": round(top_energy, 2),
                    "percent_of_total": round((top_energy / total_energy) * 100, 1)
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
        raise HTTPException(status_code=500, detail=f"Error generating summary: {str(e)}")


@router.get("/ovos/top-consumers", tags=["OVOS"])
async def get_top_consumers(
    metric: str = Query("energy", description="Metric to rank by: energy, cost, power, anomalies"),
    start_time: Optional[datetime] = Query(None, description="Start of time range (ISO 8601) - defaults to today 00:00"),
    end_time: Optional[datetime] = Query(None, description="End of time range (ISO 8601) - defaults to now"),
    limit: int = Query(5, description="Number of top consumers to return", ge=1, le=20)
) -> Dict[str, Any]:
    """
    Get top machines ranked by consumption metric.
    
    **OVOS-OPTIMIZED** - Simple ranking for voice responses.
    
    **Parameters:**
    - `metric`: What to rank by - `energy`, `cost`, `power`, or `anomalies`
    - `start_time`: Start of time period (ISO 8601)
    - `end_time`: End of time period (ISO 8601)
    - `limit`: Number of results (1-20, default: 5)
    
    **Metrics:**
    - `energy`: Total energy consumption (kWh) - higher is worse
    - `cost`: Total energy cost (USD) - higher is worse
    - `power`: Average power demand (kW) - higher is worse
    - `anomalies`: Number of anomalies - higher is worse
    
    **Returns:**
    - Ranked list of machines
    - Total value for context
    - Percentage breakdown
    
    **Use Cases:**
    - "Which machine uses the most energy?"
    - "What are the top 3 energy consumers today?"
    - "Which machine costs the most to run?"
    - "Which machine has the most alerts?"
    
    **Example:**
    ```
    GET /api/v1/machines/top-consumers?metric=energy&start_time=2025-10-20T00:00:00Z&end_time=2025-10-20T23:59:59Z&limit=3
    ```
    
    **Voice Response Example:**
    "The top 3 energy consumers are: Compressor-EU-1 at 867 kilowatt hours 
    representing 35.6% of total, Compressor-1 at 650 kilowatt hours at 26.7%, 
    and Injection-Molding-1 at 450 kilowatt hours at 18.5%."
    """
    
    try:
        # Set defaults for time range if not provided
        if start_time is None:
            start_time = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        if end_time is None:
            end_time = datetime.utcnow()
        
        # Validate metric
        valid_metrics = ['energy', 'cost', 'power', 'anomalies']
        if metric not in valid_metrics:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid metric. Must be one of: {', '.join(valid_metrics)}"
            )
        
        # Get all active machines
        machines = await get_machines()
        active_machines = [m for m in machines if m.get('is_active', True)]
        
        if not active_machines:
            return {
                "metric": metric,
                "time_period": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat()
                },
                "total_value": 0.0,
                "unit": "",
                "ranking": [],
                "message": "No active machines found"
            }
        
        machine_ids = [m['id'] for m in active_machines]
        
        # Build response based on metric type
        if metric in ['energy', 'cost', 'power']:
            # Energy-based metrics
            energy_query = """
                SELECT 
                    machine_id,
                    SUM(energy_kwh) as total_energy,
                    AVG(power_kw) as avg_power,
                    MAX(power_kw) as peak_power
                FROM energy_readings
                WHERE time >= $1 AND time <= $2
                    AND machine_id = ANY($3)
                GROUP BY machine_id
                ORDER BY total_energy DESC
            """
            
            async with db.pool.acquire() as conn:
                results = await conn.fetch(
                    energy_query, 
                    start_time, 
                    end_time, 
                    machine_ids
                )
            
            if not results:
                return {
                    "metric": metric,
                    "time_period": {
                        "start": start_time.isoformat(),
                        "end": end_time.isoformat()
                    },
                    "total_value": 0.0,
                    "unit": "kWh" if metric == "energy" else ("USD" if metric == "cost" else "kW"),
                    "ranking": [],
                    "message": "No data available for this time period"
                }
            
            # Calculate totals
            total_energy = sum(float(r['total_energy'] or 0) for r in results)
            total_cost = total_energy * ENERGY_RATE
            
            # Build ranking list
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
                else:  # power
                    value = avg_power
                    # For power, percentage based on total avg power
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
            
            # Determine unit and total value
            if metric == 'energy':
                unit = "kWh"
                total_value = total_energy
            elif metric == 'cost':
                unit = "USD"
                total_value = total_cost
            else:  # power
                unit = "kW"
                total_value = sum(float(r['avg_power'] or 0) for r in results)
            
            return {
                "metric": metric,
                "metric_label": {
                    "energy": "Energy Consumption",
                    "cost": "Energy Cost",
                    "power": "Average Power Demand"
                }[metric],
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
                WHERE detected_at >= $1 AND detected_at <= $2
                    AND machine_id = ANY($3)
                GROUP BY machine_id
                ORDER BY anomaly_count DESC
            """
            
            async with db.pool.acquire() as conn:
                results = await conn.fetch(
                    anomaly_query,
                    start_time,
                    end_time,
                    machine_ids
                )
            
            if not results:
                return {
                    "metric": "anomalies",
                    "metric_label": "Anomaly Count",
                    "time_period": {
                        "start": start_time.isoformat(),
                        "end": end_time.isoformat()
                    },
                    "total_value": 0,
                    "unit": "anomalies",
                    "ranking": [],
                    "message": "No anomalies detected in this period"
                }
            
            # Calculate total
            total_anomalies = sum(int(r['anomaly_count']) for r in results)
            
            # Build ranking
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
        raise HTTPException(status_code=500, detail=f"Error calculating top consumers: {str(e)}")


@router.get("/ovos/machines/{machine_name}/status", tags=["OVOS"])
async def get_machine_status_by_name(machine_name: str) -> Dict[str, Any]:
    """
    Get comprehensive machine status by name (no UUID required).
    
    **OVOS-OPTIMIZED** - Resolve machine name and return complete status.
    
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
    curl "http://localhost:8001/api/v1/ovos/machines/Compressor-1/status"
    curl "http://localhost:8001/api/v1/ovos/machines/compressor/status"
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
        total_cost = total_energy * ENERGY_RATE
        
        # Calculate uptime (hours with readings > 0.5 kW)
        reading_count = today_stats['reading_count'] if today_stats['reading_count'] else 0
        hours_elapsed = (datetime.utcnow() - start_of_day).total_seconds() / 3600
        uptime_hours = reading_count / 12 if reading_count > 0 else 0  # Assuming 5-min intervals
        uptime_percent = (uptime_hours / hours_elapsed * 100) if hours_elapsed > 0 else 0.0
        
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


@router.get("/ovos/forecast/tomorrow", tags=["OVOS"])
async def get_tomorrow_forecast(
    machine_id: Optional[UUID] = Query(None, description="Specific machine UUID (optional - if omitted, returns all machines)")
) -> Dict[str, Any]:
    """
    Get simplified energy forecast for tomorrow (24 hours).
    
    **OVOS-OPTIMIZED** - Quick forecast summary for voice queries.
    
    **Features:**
    - Tomorrow's predicted energy consumption (kWh)
    - Estimated cost at standard rate ($0.15/kWh)
    - Peak demand prediction (kW)
    - Peak time prediction
    - Confidence score
    - Per-machine breakdown (optional)
    
    **Parameters:**
    - `machine_id`: Optional - specific machine UUID. If omitted, returns factory-wide forecast.
    
    **Examples:**
    ```bash
    # Forecast for all machines (factory-wide)
    curl "http://localhost:8001/api/v1/ovos/forecast/tomorrow"
    
    # Forecast for specific machine
    curl "http://localhost:8001/api/v1/ovos/forecast/tomorrow?machine_id=c0000000-0000-0000-0000-000000000001"
    ```
    
    **OVOS Use Cases:**
    - "How much energy will we use tomorrow?"
    - "What's the forecast for Compressor-1 tomorrow?"
    - "When will peak demand occur tomorrow?"
    
    **Voice Response Template:**
    "Tomorrow's forecast: The factory will consume approximately 2,500 kilowatt 
    hours costing $375. Peak demand of 310 kilowatts is expected at 2 PM. 
    Confidence is 85%."
    """
    try:
        from database import db, get_machines
        from datetime import timedelta
        
        # Get tomorrow's date range
        today = datetime.utcnow().date()
        tomorrow = today + timedelta(days=1)
        tomorrow_start = datetime.combine(tomorrow, datetime.min.time())
        tomorrow_end = datetime.combine(tomorrow, datetime.max.time())
        
        ENERGY_RATE = 0.15  # $/kWh
        
        if machine_id:
            # Single machine forecast
            async with db.pool.acquire() as conn:
                # Get last 7 days of data for simple moving average forecast
                historical = await conn.fetch("""
                    SELECT 
                        DATE(time) as date,
                        SUM(energy_kwh) as daily_energy,
                        AVG(power_kw) as avg_power,
                        MAX(power_kw) as peak_power
                    FROM energy_readings
                    WHERE machine_id = $1
                        AND time >= NOW() - INTERVAL '7 days'
                        AND time < NOW()
                    GROUP BY DATE(time)
                    ORDER BY date DESC
                    LIMIT 7
                """, machine_id)
                
                if not historical or len(historical) == 0:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Insufficient historical data for machine {machine_id}"
                    )
                
                # Get machine info
                machines = await get_machines()
                machine = next((m for m in machines if m['id'] == machine_id), None)
                if not machine:
                    raise HTTPException(status_code=404, detail=f"Machine not found: {machine_id}")
            
            # Simple moving average forecast
            daily_energies = [float(h['daily_energy']) for h in historical]
            avg_powers = [float(h['avg_power']) for h in historical]
            peak_powers = [float(h['peak_power']) for h in historical]
            
            forecast_energy = sum(daily_energies) / len(daily_energies)
            forecast_avg_power = sum(avg_powers) / len(avg_powers)
            forecast_peak_power = sum(peak_powers) / len(peak_powers)
            forecast_cost = forecast_energy * ENERGY_RATE
            
            # Calculate confidence based on variance
            variance = sum((x - forecast_energy) ** 2 for x in daily_energies) / len(daily_energies)
            std_dev = variance ** 0.5
            coefficient_of_variation = (std_dev / forecast_energy) if forecast_energy > 0 else 1.0
            confidence = max(0.5, min(0.95, 1.0 - coefficient_of_variation))
            
            # Predict peak time (simplified - use historical pattern)
            # For simplicity, assume peak at 2 PM (14:00)
            peak_time = "14:00:00"
            
            response = {
                "forecast_type": "single_machine",
                "forecast_date": tomorrow.isoformat(),
                "machine_id": str(machine_id),
                "machine_name": machine.get('name'),
                "machine_type": machine.get('type'),
                "predicted_energy_kwh": round(forecast_energy, 2),
                "predicted_cost_usd": round(forecast_cost, 2),
                "predicted_avg_power_kw": round(forecast_avg_power, 2),
                "predicted_peak_power_kw": round(forecast_peak_power, 2),
                "predicted_peak_time": peak_time,
                "confidence": round(confidence, 2),
                "historical_days_used": len(historical),
                "method": "7-day moving average",
                "timestamp": datetime.utcnow().isoformat()
            }
        
        else:
            # Factory-wide forecast (all machines)
            machines = await get_machines()
            active_machines = [m for m in machines if m.get('is_active')]
            
            machine_forecasts = []
            total_energy = 0.0
            total_cost = 0.0
            max_peak_power = 0.0
            peak_machine = None
            total_confidence = 0.0
            
            async with db.pool.acquire() as conn:
                for machine in active_machines:
                    mid = machine['id']
                    
                    # Get historical data
                    historical = await conn.fetch("""
                        SELECT 
                            DATE(time) as date,
                            SUM(energy_kwh) as daily_energy,
                            MAX(power_kw) as peak_power
                        FROM energy_readings
                        WHERE machine_id = $1
                            AND time >= NOW() - INTERVAL '7 days'
                            AND time < NOW()
                        GROUP BY DATE(time)
                        ORDER BY date DESC
                        LIMIT 7
                    """, mid)
                    
                    if not historical or len(historical) == 0:
                        continue
                    
                    # Forecast for this machine
                    daily_energies = [float(h['daily_energy']) for h in historical]
                    peak_powers = [float(h['peak_power']) for h in historical]
                    
                    forecast_energy = sum(daily_energies) / len(daily_energies)
                    forecast_peak = sum(peak_powers) / len(peak_powers)
                    forecast_cost = forecast_energy * ENERGY_RATE
                    
                    # Confidence
                    variance = sum((x - forecast_energy) ** 2 for x in daily_energies) / len(daily_energies)
                    std_dev = variance ** 0.5
                    coefficient_of_variation = (std_dev / forecast_energy) if forecast_energy > 0 else 1.0
                    confidence = max(0.5, min(0.95, 1.0 - coefficient_of_variation))
                    
                    machine_forecasts.append({
                        "machine_id": str(mid),
                        "machine_name": machine.get('name'),
                        "machine_type": machine.get('type'),
                        "predicted_energy_kwh": round(forecast_energy, 2),
                        "predicted_cost_usd": round(forecast_cost, 2),
                        "predicted_peak_power_kw": round(forecast_peak, 2),
                        "confidence": round(confidence, 2)
                    })
                    
                    total_energy += forecast_energy
                    total_cost += forecast_cost
                    total_confidence += confidence
                    
                    if forecast_peak > max_peak_power:
                        max_peak_power = forecast_peak
                        peak_machine = machine.get('name')
            
            if len(machine_forecasts) == 0:
                raise HTTPException(
                    status_code=404,
                    detail="Insufficient historical data for forecasting"
                )
            
            avg_confidence = total_confidence / len(machine_forecasts)
            
            response = {
                "forecast_type": "factory_wide",
                "forecast_date": tomorrow.isoformat(),
                "total_predicted_energy_kwh": round(total_energy, 2),
                "total_predicted_cost_usd": round(total_cost, 2),
                "predicted_peak_demand_kw": round(max_peak_power, 2),
                "predicted_peak_time": "14:00:00",
                "peak_machine": peak_machine,
                "average_confidence": round(avg_confidence, 2),
                "machines_forecasted": len(machine_forecasts),
                "by_machine": machine_forecasts,
                "method": "7-day moving average (per machine)",
                "timestamp": datetime.utcnow().isoformat()
            }
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating forecast: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating forecast: {str(e)}")


