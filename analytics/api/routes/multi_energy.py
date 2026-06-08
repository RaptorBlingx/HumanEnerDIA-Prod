"""
Multi-Energy API Routes
Handles queries for machines with multiple energy sources (electricity, gas, steam, etc.)
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from datetime import datetime, timedelta
import logging

from database import db

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/machines/{machine_id}/energy-types", tags=["Multi-Energy", "OVOS"])
async def get_machine_energy_types(
    machine_id: str,
    hours: int = Query(24, ge=1, le=168, description="Look-back period in hours (max 7 days)")
):
    """
    Get all energy types used by a machine with summary statistics.
    
    **Use Case:** "What energy types does Boiler 1 use?"
    
    **Returns:**
    - Energy type list with counts, averages, and time ranges
    - Power equivalents for comparison
    - Original measurement units
    
    **Example Response:**
    ```json
    {
      "machine_id": "e9fcad45-1f7b-4425-8710-c368a681f15e",
      "machine_name": "Boiler-1",
      "time_period_hours": 24,
      "energy_types": [
        {
          "energy_type": "electricity",
          "reading_count": 96,
          "avg_power_kw": 25.2,
          "first_reading": "2025-10-27T00:00:00Z",
          "last_reading": "2025-10-27T23:59:00Z",
          "unit": "kWh"
        },
        {
          "energy_type": "natural_gas",
          "reading_count": 288,
          "avg_power_kw": 1785.6,
          "first_reading": "2025-10-27T00:00:00Z",
          "last_reading": "2025-10-27T23:59:00Z",
          "unit": "m³"
        }
      ]
    }
    ```
    """
    try:
        query = """
            WITH machine_info AS (
                SELECT name FROM machines WHERE id = $1::uuid
            ),
            energy_summary AS (
                SELECT 
                    COALESCE(energy_type, 'electricity') as energy_type,
                    COUNT(*) as reading_count,
                    ROUND(AVG(power_kw)::numeric, 2) as avg_power_kw,
                    MIN(time) as first_reading,
                    MAX(time) as last_reading
                FROM energy_readings 
                WHERE machine_id = $1::uuid
                    AND time > NOW() - INTERVAL '1 hour' * $2
                GROUP BY energy_type
                ORDER BY energy_type
            )
            SELECT 
                (SELECT name FROM machine_info) as machine_name,
                energy_type,
                reading_count,
                avg_power_kw,
                first_reading,
                last_reading
            FROM energy_summary;
        """
        
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(query, machine_id, hours)
            
            if not rows:
                raise HTTPException(
                    status_code=404,
                    detail=f"No energy data found for machine {machine_id} in the last {hours} hours"
                )
            
            machine_name = rows[0]['machine_name'] if rows else None
            
            energy_types = [
                {
                    "energy_type": row['energy_type'],
                    "reading_count": row['reading_count'],
                    "avg_power_kw": float(row['avg_power_kw']) if row['avg_power_kw'] else 0,
                    "first_reading": row['first_reading'].isoformat(),
                    "last_reading": row['last_reading'].isoformat(),
                    "unit": _get_energy_unit(row['energy_type'])
                }
                for row in rows
            ]
            
            return {
                "machine_id": machine_id,
                "machine_name": machine_name,
                "time_period_hours": hours,
                "energy_types": energy_types,
                "total_energy_types": len(energy_types),
                "timestamp": datetime.utcnow().isoformat()
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching energy types: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/machines/{machine_id}/energy/{energy_type}", tags=["Multi-Energy", "OVOS"])
async def get_energy_readings_by_type(
    machine_id: str,
    energy_type: str,
    limit: int = Query(100, ge=1, le=1000, description="Number of readings to return"),
    include_metadata: bool = Query(True, description="Include full metadata in response")
):
    """
    Get readings for a specific energy type with original measurements.
    
    **Use Case:** "Show me natural gas consumption for Boiler 1"
    
    **Energy Types:**
    - `electricity` - Electrical power (kW)
    - `natural_gas` - Natural gas (m³/h)
    - `steam` - Steam production (kg/h)
    - `compressed_air` - Compressed air (m³/h)
    
    **Returns:**
    - Time-series data with power equivalents
    - Original measurements (flow rate, pressure, temperature, etc.)
    - Metadata for detailed analysis
    
    **Example Response:**
    ```json
    {
      "machine_id": "e9fcad45-1f7b-4425-8710-c368a681f15e",
      "energy_type": "natural_gas",
      "data": [
        {
          "time": "2025-10-27T08:12:34Z",
          "power_kw": 1744.896,
          "flow_rate_m3h": 165.393,
          "consumption_m3": 1.3783,
          "pressure_bar": 4.16,
          "temperature_c": 21.7,
          "calorific_value_kwh_m3": 10.55
        }
      ]
    }
    ```
    """
    try:
        # Validate energy type
        valid_types = ['electricity', 'natural_gas', 'steam', 'compressed_air']
        if energy_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid energy_type. Must be one of: {', '.join(valid_types)}"
            )
        
        query = """
            SELECT 
                time,
                power_kw,
                metadata
            FROM energy_readings 
            WHERE machine_id = $1::uuid
              AND metadata->>'energy_type' = $2
            ORDER BY time DESC 
            LIMIT $3;
        """
        
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(query, machine_id, energy_type, limit)
            
            if not rows:
                raise HTTPException(
                    status_code=404,
                    detail=f"No {energy_type} data found for machine {machine_id}"
                )
            
            # Parse metadata based on energy type
            data = []
            for row in rows:
                reading = {
                    "time": row['time'].isoformat(),
                    "power_kw": float(row['power_kw']) if row['power_kw'] else 0
                }
                
                # Add energy-specific measurements
                if include_metadata and row['metadata']:
                    import json
                    metadata = json.loads(row['metadata']) if isinstance(row['metadata'], str) else row['metadata']
                    
                    if energy_type == 'natural_gas':
                        reading["flow_rate_m3h"] = metadata.get('flow_rate_m3h')
                        reading["consumption_m3"] = metadata.get('consumption_m3')
                        reading["pressure_bar"] = metadata.get('pressure_bar')
                        reading["temperature_c"] = metadata.get('temperature_c')
                        reading["calorific_value_kwh_m3"] = metadata.get('calorific_value_kwh_m3')
                    elif energy_type == 'steam':
                        reading["flow_rate_kg_h"] = metadata.get('flow_rate_kg_h')
                        reading["consumption_kg"] = metadata.get('consumption_kg')
                        reading["pressure_bar"] = metadata.get('pressure_bar')
                        reading["temperature_c"] = metadata.get('temperature_c')
                        reading["enthalpy_kj_kg"] = metadata.get('enthalpy_kj_kg')
                    elif energy_type == 'compressed_air':
                        reading["flow_rate_m3h"] = metadata.get('flow_rate_m3h')
                        reading["pressure_bar"] = metadata.get('pressure_bar')
                        reading["temperature_c"] = metadata.get('temperature_c')
                        reading["dew_point_c"] = metadata.get('dew_point_c')
                    # electricity has no additional fields
                
                data.append(reading)
            
            return {
                "success": True,
                "machine_id": machine_id,
                "energy_type": energy_type,
                "data": data,
                "count": len(data),
                "unit": _get_energy_unit(energy_type),
                "timestamp": datetime.utcnow().isoformat()
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching {energy_type} readings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/machines/{machine_id}/energy-summary", tags=["Multi-Energy", "OVOS"])
async def get_multi_energy_summary(
    machine_id: str,
    start_time: Optional[datetime] = Query(None, description="Start time (default: 24 hours ago)"),
    end_time: Optional[datetime] = Query(None, description="End time (default: now)")
):
    """
    Get aggregated summary across all energy types for a machine.
    
    **Use Case:** "Compare all energy types for Boiler 1"
    
    **Returns:**
    - Total consumption per energy type
    - Average power/flow rates
    - Cost estimates (if configured)
    - Efficiency metrics
    
    **Example Response:**
    ```json
    {
      "machine_id": "e9fcad45-1f7b-4425-8710-c368a681f15e",
      "time_period": {
        "start": "2025-10-26T00:00:00Z",
        "end": "2025-10-27T00:00:00Z",
        "hours": 24
      },
      "summary_by_type": [
        {
          "energy_type": "natural_gas",
          "reading_count": 288,
          "avg_power_kw": 1785.6,
          "total_consumption": "4285.4 m³",
          "avg_flow_rate": "178.6 m³/h",
          "estimated_cost_eur": 2142.7
        }
      ]
    }
    ```
    """
    try:
        # Default time range: last 24 hours
        if not end_time:
            end_time = datetime.utcnow()
        if not start_time:
            start_time = end_time - timedelta(hours=24)
        
        hours = (end_time - start_time).total_seconds() / 3600
        
        query = """
            SELECT 
                metadata->>'energy_type' as energy_type,
                COUNT(*) as reading_count,
                ROUND(AVG(power_kw)::numeric, 2) as avg_power_kw,
                ROUND((AVG(power_kw) * $4)::numeric, 2) as total_kwh
            FROM energy_readings 
            WHERE machine_id = $1::uuid
              AND time >= $2
              AND time <= $3
              AND metadata->>'energy_type' IS NOT NULL
            GROUP BY metadata->>'energy_type'
            ORDER BY energy_type;
        """
        
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(query, machine_id, start_time, end_time, hours)
            
            if not rows:
                raise HTTPException(
                    status_code=404,
                    detail=f"No multi-energy data found for machine {machine_id} in specified time range"
                )
            
            # Aggregate by energy type
            summary = []
            for row in rows:
                energy_type = row['energy_type']
                summary.append({
                    "energy_type": energy_type,
                    "reading_count": row['reading_count'],
                    "avg_power_kw": float(row['avg_power_kw']) if row['avg_power_kw'] else 0,
                    "total_kwh": float(row['total_kwh']) if row['total_kwh'] else 0,
                    "unit": _get_energy_unit(energy_type)
                })
            
            return {
                "success": True,
                "machine_id": machine_id,
                "time_period": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "hours": round(hours, 2)
                },
                "summary_by_type": summary,
                "total_energy_types": len(summary),
                "timestamp": datetime.utcnow().isoformat()
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating multi-energy summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _get_energy_unit(energy_type: str) -> str:
    """Get measurement unit for energy type."""
    units = {
        'electricity': 'kWh',
        'natural_gas': 'm³',
        'steam': 'kg',
        'compressed_air': 'Nm³'
    }
    return units.get(energy_type, 'kWh')
