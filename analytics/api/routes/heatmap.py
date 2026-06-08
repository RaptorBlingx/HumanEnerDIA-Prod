"""
Anomaly Heatmap API Routes
===========================
Provides anomaly pattern data for heatmap visualizations showing:
- Hour of day Ã— Machine anomaly frequency
- Day of week Ã— Machine anomaly frequency
- Time-based pattern analysis

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

router = APIRouter(prefix="/heatmap")


# ============================================================================
# DATA MODELS
# ============================================================================

class HeatmapCell(BaseModel):
    """Single cell in the heatmap"""
    x: str = Field(..., description="X-axis value (e.g., machine name)")
    y: str = Field(..., description="Y-axis value (e.g., hour)")
    value: int = Field(..., description="Count of anomalies")
    severity_avg: float = Field(..., description="Average severity score")


class HeatmapData(BaseModel):
    """Complete heatmap data"""
    cells: List[HeatmapCell] = Field(..., description="All heatmap cells")
    x_labels: List[str] = Field(..., description="X-axis labels (machines)")
    y_labels: List[str] = Field(..., description="Y-axis labels (hours/days)")
    total_anomalies: int = Field(..., description="Total anomalies in dataset")
    start_date: datetime = Field(..., description="Start of analysis period")
    end_date: datetime = Field(..., description="End of analysis period")
    max_count: int = Field(..., description="Maximum count in any cell (for color scaling)")
    patterns: List[str] = Field(..., description="Identified patterns")


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/hourly", response_model=HeatmapData)
async def get_hourly_heatmap(
    start_date: Optional[datetime] = Query(None, description="Start date (default: 30 days ago)"),
    end_date: Optional[datetime] = Query(None, description="End date (default: now)"),
    machine_ids: Optional[str] = Query(None, description="Comma-separated machine IDs (default: all)"),
    min_severity: float = Query(0.0, description="Minimum severity score (0-1)")
):
    """
    Get anomaly heatmap by hour of day.
    
    Shows: Machine Ã— Hour (24 hours) with anomaly counts
    
    Args:
        start_date: Start of analysis period
        end_date: End of analysis period
        machine_ids: Filter specific machines
        min_severity: Minimum severity threshold
    
    Returns:
        HeatmapData with hourly anomaly distribution
    """
    try:
        # Default date range: last 30 days
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        # Parse machine IDs if provided
        machine_id_list = None
        if machine_ids:
            machine_id_list = [mid.strip() for mid in machine_ids.split(',')]
        
        # Get database pool
        pool = db.pool
        
        async with pool.acquire() as conn:
            # Query: Anomaly count by machine and hour
            query = """
                SELECT 
                    m.id AS machine_id,
                    m.name AS machine_name,
                    EXTRACT(HOUR FROM a.detected_at) AS hour,
                    COUNT(*) AS anomaly_count,
                    AVG(COALESCE(a.confidence_score, 0.5)) AS avg_severity
                FROM anomalies a
                JOIN machines m ON m.id = a.machine_id
                WHERE a.detected_at >= $1 AND a.detected_at <= $2
                    AND COALESCE(a.confidence_score, 0.5) >= $3
            """
            
            params = [start_date, end_date, min_severity]
            
            if machine_id_list:
                query += " AND m.id = ANY($4::uuid[])"
                params.append(machine_id_list)
            
            query += """
                GROUP BY m.id, m.name, EXTRACT(HOUR FROM a.detected_at)
                ORDER BY m.name, hour
            """
            
            rows = await conn.fetch(query, *params)
        
        # Build heatmap cells
        cells = []
        machine_totals = {}
        hour_totals = {}
        
        for row in rows:
            machine_name = row['machine_name']
            hour = int(row['hour'])
            count = row['anomaly_count']
            avg_severity = float(row['avg_severity'])
            
            cells.append(HeatmapCell(
                x=machine_name,
                y=f"{hour:02d}:00",
                value=count,
                severity_avg=round(avg_severity, 3)
            ))
            
            # Track totals
            machine_totals[machine_name] = machine_totals.get(machine_name, 0) + count
            hour_totals[hour] = hour_totals.get(hour, 0) + count
        
        # Get unique labels
        x_labels = sorted(set(cell.x for cell in cells))
        y_labels = [f"{h:02d}:00" for h in range(24)]
        
        # Calculate total and max
        total_anomalies = sum(cell.value for cell in cells)
        max_count = max((cell.value for cell in cells), default=0)
        
        # Identify patterns
        patterns = identify_patterns(machine_totals, hour_totals, cells)
        
        return HeatmapData(
            cells=cells,
            x_labels=x_labels,
            y_labels=y_labels,
            total_anomalies=total_anomalies,
            start_date=start_date,
            end_date=end_date,
            max_count=max_count,
            patterns=patterns
        )
        
    except Exception as e:
        logger.error(f"Error generating hourly heatmap: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate heatmap: {str(e)}")


@router.get("/daily", response_model=HeatmapData)
async def get_daily_heatmap(
    start_date: Optional[datetime] = Query(None, description="Start date (default: 30 days ago)"),
    end_date: Optional[datetime] = Query(None, description="End date (default: now)"),
    machine_ids: Optional[str] = Query(None, description="Comma-separated machine IDs (default: all)"),
    min_severity: float = Query(0.0, description="Minimum severity score (0-1)")
):
    """
    Get anomaly heatmap by day of week.
    
    Shows: Machine Ã— Day of Week with anomaly counts
    
    Args:
        start_date: Start of analysis period
        end_date: End of analysis period
        machine_ids: Filter specific machines
        min_severity: Minimum severity threshold
    
    Returns:
        HeatmapData with daily anomaly distribution
    """
    try:
        # Default date range: last 30 days
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        # Parse machine IDs if provided
        machine_id_list = None
        if machine_ids:
            machine_id_list = [mid.strip() for mid in machine_ids.split(',')]
        
        # Get database pool
        pool = db.pool
        
        async with pool.acquire() as conn:
            # Query: Anomaly count by machine and day of week
            query = """
                SELECT 
                    m.id AS machine_id,
                    m.name AS machine_name,
                    EXTRACT(DOW FROM a.detected_at) AS day_of_week,
                    COUNT(*) AS anomaly_count,
                    AVG(COALESCE(a.confidence_score, 0.5)) AS avg_severity
                FROM anomalies a
                JOIN machines m ON m.id = a.machine_id
                WHERE a.detected_at >= $1 AND a.detected_at <= $2
                    AND COALESCE(a.confidence_score, 0.5) >= $3
            """
            
            params = [start_date, end_date, min_severity]
            
            if machine_id_list:
                query += " AND m.id = ANY($4::uuid[])"
                params.append(machine_id_list)
            
            query += """
                GROUP BY m.id, m.name, EXTRACT(DOW FROM a.detected_at)
                ORDER BY m.name, day_of_week
            """
            
            rows = await conn.fetch(query, *params)
        
        # Build heatmap cells
        cells = []
        machine_totals = {}
        day_totals = {}
        
        day_names = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        
        for row in rows:
            machine_name = row['machine_name']
            day_num = int(row['day_of_week'])
            day_name = day_names[day_num]
            count = row['anomaly_count']
            avg_severity = float(row['avg_severity'])
            
            cells.append(HeatmapCell(
                x=machine_name,
                y=day_name,
                value=count,
                severity_avg=round(avg_severity, 3)
            ))
            
            # Track totals
            machine_totals[machine_name] = machine_totals.get(machine_name, 0) + count
            day_totals[day_name] = day_totals.get(day_name, 0) + count
        
        # Get unique labels
        x_labels = sorted(set(cell.x for cell in cells))
        y_labels = day_names
        
        # Calculate total and max
        total_anomalies = sum(cell.value for cell in cells)
        max_count = max((cell.value for cell in cells), default=0)
        
        # Identify patterns
        patterns = identify_daily_patterns(machine_totals, day_totals, cells)
        
        return HeatmapData(
            cells=cells,
            x_labels=x_labels,
            y_labels=y_labels,
            total_anomalies=total_anomalies,
            start_date=start_date,
            end_date=end_date,
            max_count=max_count,
            patterns=patterns
        )
        
    except Exception as e:
        logger.error(f"Error generating daily heatmap: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate heatmap: {str(e)}")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def identify_patterns(machine_totals: Dict[str, int], hour_totals: Dict[int, int], cells: List[HeatmapCell]) -> List[str]:
    """
    Identify patterns in hourly anomaly data.
    
    Returns:
        List of human-readable pattern descriptions
    """
    patterns = []
    
    # Find peak hour
    if hour_totals:
        peak_hour = max(hour_totals, key=hour_totals.get)
        patterns.append(f"Most anomalies occur at {peak_hour:02d}:00 ({hour_totals[peak_hour]} anomalies)")
    
    # Find most problematic machine
    if machine_totals:
        worst_machine = max(machine_totals, key=machine_totals.get)
        patterns.append(f"Machine '{worst_machine}' has the most anomalies ({machine_totals[worst_machine]} total)")
    
    # Find night shift issues (22:00 - 06:00)
    night_count = sum(count for hour, count in hour_totals.items() if hour >= 22 or hour < 6)
    if night_count > sum(hour_totals.values()) * 0.3:
        patterns.append(f"High anomaly rate during night shift ({night_count} anomalies, {round(night_count / sum(hour_totals.values()) * 100)}%)")
    
    # Find machines with consistent issues
    consistent_machines = [
        machine for machine, count in machine_totals.items()
        if count > sum(machine_totals.values()) / len(machine_totals) * 1.5
    ]
    if consistent_machines:
        patterns.append(f"Machines with consistently high anomalies: {', '.join(consistent_machines)}")
    
    return patterns


def identify_daily_patterns(machine_totals: Dict[str, int], day_totals: Dict[str, int], cells: List[HeatmapCell]) -> List[str]:
    """
    Identify patterns in daily anomaly data.
    
    Returns:
        List of human-readable pattern descriptions
    """
    patterns = []
    
    # Find peak day
    if day_totals:
        peak_day = max(day_totals, key=day_totals.get)
        patterns.append(f"Most anomalies occur on {peak_day} ({day_totals[peak_day]} anomalies)")
    
    # Find most problematic machine
    if machine_totals:
        worst_machine = max(machine_totals, key=machine_totals.get)
        patterns.append(f"Machine '{worst_machine}' has the most anomalies ({machine_totals[worst_machine]} total)")
    
    # Find weekend issues
    weekend_count = sum(day_totals.get(day, 0) for day in ['Saturday', 'Sunday'])
    weekday_count = sum(day_totals.get(day, 0) for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'])
    
    if weekend_count > 0 and weekday_count > 0:
        weekend_ratio = weekend_count / (weekend_count + weekday_count)
        if weekend_ratio > 0.4:
            patterns.append(f"High anomaly rate on weekends ({weekend_count} anomalies, {round(weekend_ratio * 100)}%)")
    
    return patterns