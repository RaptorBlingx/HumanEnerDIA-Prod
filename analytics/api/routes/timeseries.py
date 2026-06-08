"""
EnMS Analytics Service - Time-Series API Routes
Phase 4 Session 3

REST API endpoints for time-series data visualization.
Provides historical data with various aggregation intervals.
"""

import logging
from datetime import datetime, timedelta
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from database import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/timeseries", tags=["Time Series"])


# ============================================================================
# Response Models
# ============================================================================

class TimeSeriesPoint(BaseModel):
    """Single time-series data point."""
    timestamp: str
    value: float
    unit: str


class TimeSeriesResponse(BaseModel):
    """Time-series data response."""
    machine_id: str
    machine_name: str
    metric: str
    interval: str
    start_time: str
    end_time: str
    data_points: list[TimeSeriesPoint]
    total_points: int
    aggregation: str


# ============================================================================
# Helper Functions
# ============================================================================

async def get_machine_name(machine_id: UUID) -> str:
    """Get machine name from ID."""
    pool = db.pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT name FROM machines WHERE id = $1",
            machine_id
        )
        return row['name'] if row else f"Machine-{machine_id}"


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/energy", response_model=TimeSeriesResponse)
async def get_energy_timeseries(
    machine_id: UUID = Query(..., description="Machine UUID"),
    start_time: datetime = Query(..., description="Start time (ISO format)"),
    end_time: datetime = Query(..., description="End time (ISO format)"),
    interval: Literal['1min', '5min', '15min', '1hour', '1day'] = Query(
        '1hour',
        description="Aggregation interval"
    )
):
    """
    Get energy consumption time-series data.
    
    **Returns:**
    - Timestamp and energy (kWh) for each interval
    - Aggregated using time_bucket
    - Sorted chronologically
    
    **Intervals:**
    - `1min`: Raw 1-minute data
    - `5min`: 5-minute buckets
    - `15min`: 15-minute buckets
    - `1hour`: Hourly buckets (recommended)
    - `1day`: Daily buckets
    
    **Use Cases:**
    - Energy consumption trends
    - Peak detection
    - Load profiling
    """
    logger.info(
        f"[TIMESERIES-API] Energy data for {machine_id}, "
        f"interval={interval}, range={start_time} to {end_time}"
    )
    
    # Convert interval to PostgreSQL interval format
    interval_map = {
        '1min': '1 minute',
        '5min': '5 minutes',
        '15min': '15 minutes',
        '1hour': '1 hour',
        '1day': '1 day'
    }
    pg_interval = interval_map[interval]
    
    try:
        pool = db.pool
        
        # Use raw energy_readings table for maximum accuracy and consistency
        # with the status endpoints. Aggregates might have slight lag.
        query = f"""
            SELECT 
                time_bucket('{pg_interval}', time) AS time_bucket,
                SUM(energy_kwh) AS total_energy
            FROM energy_readings
            WHERE 
                machine_id = $1
                AND time >= $2 AND time < $3
            GROUP BY time_bucket
            ORDER BY time_bucket
        """
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                query,
                machine_id,
                start_time,
                end_time
            )
        
        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for machine {machine_id} in specified time range"
            )
        
        # Format response
        data_points = [
            TimeSeriesPoint(
                timestamp=row['time_bucket'].isoformat(),
                value=float(row['total_energy']),
                unit='kWh'
            )
            for row in rows
        ]
        
        machine_name = await get_machine_name(machine_id)
        
        return TimeSeriesResponse(
            machine_id=str(machine_id),
            machine_name=machine_name,
            metric='energy',
            interval=interval,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            data_points=data_points,
            total_points=len(data_points),
            aggregation='sum'
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TIMESERIES-API] Error fetching energy data: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch energy data: {str(e)}"
        )


@router.get("/power", response_model=TimeSeriesResponse)
async def get_power_timeseries(
    machine_id: UUID = Query(..., description="Machine UUID"),
    start_time: datetime = Query(..., description="Start time (ISO format)"),
    end_time: datetime = Query(..., description="End time (ISO format)"),
    interval: Literal['1min', '5min', '15min', '1hour'] = Query(
        '15min',
        description="Aggregation interval"
    )
):
    """
    Get power demand time-series data.
    
    **Returns:**
    - Timestamp and power (kW) for each interval
    - Aggregated using average power
    - Useful for demand profiling
    
    **Use Cases:**
    - Peak demand analysis
    - Load factor calculation
    - Demand response programs
    """
    logger.info(
        f"[TIMESERIES-API] Power data for {machine_id}, "
        f"interval={interval}"
    )
    
    interval_map = {
        '1min': '1 minute',
        '5min': '5 minutes',
        '15min': '15 minutes',
        '1hour': '1 hour'
    }
    pg_interval = interval_map[interval]
    
    try:
        pool = db.pool
        
        # Use raw energy_readings table for consistency with energy endpoint
        query = f"""
            SELECT 
                time_bucket('{pg_interval}', time) AS time_bucket,
                AVG(power_kw) AS avg_power
            FROM energy_readings
            WHERE 
                machine_id = $1
                AND time >= $2 AND time < $3
            GROUP BY time_bucket
            ORDER BY time_bucket
        """
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                query,
                machine_id,
                start_time,
                end_time
            )
        
        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for machine {machine_id}"
            )
        
        data_points = [
            TimeSeriesPoint(
                timestamp=row['time_bucket'].isoformat(),
                value=float(row['avg_power']),
                unit='kW'
            )
            for row in rows
        ]
        
        machine_name = await get_machine_name(machine_id)
        
        return TimeSeriesResponse(
            machine_id=str(machine_id),
            machine_name=machine_name,
            metric='power',
            interval=interval,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            data_points=data_points,
            total_points=len(data_points),
            aggregation='average'
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TIMESERIES-API] Error fetching power data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sec", response_model=TimeSeriesResponse)
async def get_sec_timeseries(
    machine_id: UUID = Query(..., description="Machine UUID"),
    start_time: datetime = Query(..., description="Start time (ISO format)"),
    end_time: datetime = Query(..., description="End time (ISO format)"),
    interval: Literal['1hour', '1day', '1week'] = Query(
        '1day',
        description="Aggregation interval"
    )
):
    """
    Get SEC (Specific Energy Consumption) time-series data.
    
    **Formula:** SEC = Total Energy (kWh) / Total Production (units)
    
    **Returns:**
    - Timestamp and SEC (kWh/unit) for each interval
    - Requires production data
    - Identifies efficiency trends
    
    **Use Cases:**
    - Efficiency monitoring
    - Baseline comparison
    - Process optimization
    """
    logger.info(
        f"[TIMESERIES-API] SEC data for {machine_id}, "
        f"interval={interval}"
    )
    
    interval_map = {
        '1hour': '1 hour',
        '1day': '1 day',
        '1week': '1 week'
    }
    pg_interval = interval_map[interval]
    
    try:
        pool = db.pool
        
        query = f"""
            SELECT 
                time_bucket('{pg_interval}', e.bucket) AS time_bucket,
                SUM(e.total_energy_kwh) AS total_energy,
                SUM(p.total_production_count) AS total_production,
                CASE 
                    WHEN SUM(p.total_production_count) > 0 
                    THEN SUM(e.total_energy_kwh) / SUM(p.total_production_count)
                    ELSE NULL
                END AS sec
            FROM energy_readings_1min e
            LEFT JOIN production_data_1min p 
                ON e.machine_id = p.machine_id 
                AND e.bucket = p.bucket
            WHERE 
                e.machine_id = $1
                AND e.bucket >= $2 AND e.bucket < $3
            GROUP BY time_bucket
            HAVING SUM(p.total_production_count) > 0
            ORDER BY time_bucket
        """
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                query,
                machine_id,
                start_time,
                end_time
            )
        
        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"No production data found for machine {machine_id}"
            )
        
        data_points = [
            TimeSeriesPoint(
                timestamp=row['time_bucket'].isoformat(),
                value=float(row['sec']) if row['sec'] else 0.0,
                unit='kWh/unit'
            )
            for row in rows
            if row['sec'] is not None
        ]
        
        machine_name = await get_machine_name(machine_id)
        
        return TimeSeriesResponse(
            machine_id=str(machine_id),
            machine_name=machine_name,
            metric='sec',
            interval=interval,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            data_points=data_points,
            total_points=len(data_points),
            aggregation='calculated'
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TIMESERIES-API] Error fetching SEC data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/multi-machine/energy")
async def get_multi_machine_energy(
    machine_ids: str = Query(
        ...,
        description="Comma-separated machine UUIDs",
        example="uuid1,uuid2,uuid3"
    ),
    start_time: datetime = Query(..., description="Start time (ISO format)"),
    end_time: datetime = Query(..., description="End time (ISO format)"),
    interval: Literal['1hour', '1day'] = Query('1hour', description="Interval")
):
    """
    Get energy consumption for multiple machines (for comparison).
    
    **Returns:**
    - One time-series per machine
    - Synchronized timestamps
    - Ready for comparative visualization
    
    **Use Cases:**
    - Machine comparison
    - Factory-wide monitoring
    - Benchmarking analysis
    """
    # Parse machine IDs
    try:
        machine_list = [UUID(mid.strip()) for mid in machine_ids.split(',')]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid machine ID format: {e}")
    
    if len(machine_list) > 10:
        raise HTTPException(
            status_code=400,
            detail="Maximum 10 machines allowed for comparison"
        )
    
    logger.info(
        f"[TIMESERIES-API] Multi-machine energy data for {len(machine_list)} machines"
    )
    
    interval_map = {'1hour': '1 hour', '1day': '1 day'}
    pg_interval = interval_map[interval]
    
    try:
        pool = db.pool
        
        # Fetch data for all machines
        results = {}
        
        for machine_id in machine_list:
            query = f"""
                SELECT 
                    time_bucket('{pg_interval}', time) AS time_bucket,
                    SUM(energy_kwh) AS total_energy
                FROM energy_readings
                WHERE 
                    machine_id = $1
                    AND time >= $2 AND time < $3
                GROUP BY time_bucket
                ORDER BY time_bucket
            """
            
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    query,
                    machine_id,
                    start_time,
                    end_time
                )
                
                machine_name = await get_machine_name(machine_id)
                
                results[str(machine_id)] = {
                    'machine_id': str(machine_id),
                    'machine_name': machine_name,
                    'data_points': [
                        {
                            'timestamp': row['time_bucket'].isoformat(),
                            'value': float(row['total_energy']),
                            'unit': 'kWh'
                        }
                        for row in rows
                    ]
                }
        
        return {
            'interval': interval,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'machines': list(results.values()),
            'total_machines': len(results)
        }
        
    except Exception as e:
        logger.error(f"[TIMESERIES-API] Error fetching multi-machine data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latest/{machine_id}")
async def get_latest_reading(machine_id: UUID):
    """
    Get the most recent reading for a machine.
    
    **Use Cases:**
    - Real-time dashboards
    - Current status display
    - Live monitoring
    """
    try:
        pool = db.pool
        
        query = """
            SELECT 
                bucket,
                avg_power_kw,
                total_energy_kwh
            FROM energy_readings_1min
            WHERE machine_id = $1
            ORDER BY bucket DESC
            LIMIT 1
        """
        
        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, machine_id)
        
        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for machine {machine_id}"
            )
        
        machine_name = await get_machine_name(machine_id)
        
        return {
            'machine_id': str(machine_id),
            'machine_name': machine_name,
            'timestamp': row['bucket'].isoformat(),
            'power_kw': float(row['avg_power_kw']),
            'energy_kwh': float(row['total_energy_kwh']),
            'status': 'running'  # Status not available in aggregated view
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TIMESERIES-API] Error fetching latest reading: {e}")
        raise HTTPException(status_code=500, detail=str(e))