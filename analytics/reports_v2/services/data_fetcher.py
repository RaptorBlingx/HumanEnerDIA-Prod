"""
EnMS Report Data Fetcher
========================
Fetches real data from TimescaleDB for report generation.

Author: EnMS Team
Phase: 3 - Content
Date: 2025-12-26
"""

import asyncpg
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from decimal import Decimal
import logging
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))
from database import Database
from config import settings

logger = logging.getLogger(__name__)


class ReportDataFetcher:
    """Fetches data from TimescaleDB for report generation."""
    
    def __init__(self, db: Database):
        """Initialize data fetcher with database connection."""
        self.db = db
    
    async def get_factory_info(self, factory_id: str) -> Optional[Dict[str, Any]]:
        """Get factory information."""
        async with self.db.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, name, location, timezone, contact_email
                FROM factories
                WHERE id = $1 AND is_active = TRUE
                """,
                factory_id
            )
            
            if not row:
                return None
            
            return dict(row)
    
    async def get_total_energy(
        self,
        factory_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> Decimal:
        """Get total energy consumption for period."""
        async with self.db.pool.acquire() as conn:
            result = await conn.fetchval(
                """
                SELECT COALESCE(SUM(avg_power_kw * 1.0), 0) as total_kwh
                FROM energy_readings_1hour er
                JOIN machines m ON er.machine_id = m.id
                WHERE m.factory_id = $1
                AND er.bucket >= $2
                AND er.bucket < $3
                """,
                factory_id,
                start_date,
                end_date
            )
            
            return result or Decimal('0')
    
    async def get_energy_by_category(
        self,
        factory_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Get energy consumption breakdown by machine type."""
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT 
                    m.type as category,
                    SUM(er.avg_power_kw * 1.0) as total_kwh,
                    COUNT(DISTINCT m.id) as machine_count
                FROM energy_readings_1hour er
                JOIN machines m ON er.machine_id = m.id
                WHERE m.factory_id = $1
                AND er.bucket >= $2
                AND er.bucket < $3
                GROUP BY m.type
                ORDER BY total_kwh DESC
                """,
                factory_id,
                start_date,
                end_date
            )
            
            return [dict(row) for row in rows]
    
    async def get_daily_trend(
        self,
        factory_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Get daily energy consumption trend."""
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT 
                    DATE(er.bucket) as date,
                    SUM(er.avg_power_kw * 24.0) as total_kwh,
                    AVG(er.avg_power_kw) as avg_power_kw
                FROM energy_readings_1day er
                JOIN machines m ON er.machine_id = m.id
                WHERE m.factory_id = $1
                AND er.bucket >= $2
                AND er.bucket < $3
                GROUP BY DATE(er.bucket)
                ORDER BY date
                """,
                factory_id,
                start_date,
                end_date
            )
            
            return [dict(row) for row in rows]
    
    async def get_hourly_heatmap(
        self,
        factory_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Get hourly consumption pattern (7 days x 24 hours)."""
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT 
                    EXTRACT(DOW FROM er.bucket)::INT as day_of_week,
                    EXTRACT(HOUR FROM er.bucket)::INT as hour,
                    AVG(er.avg_power_kw) as avg_power_kw
                FROM energy_readings_1hour er
                JOIN machines m ON er.machine_id = m.id
                WHERE m.factory_id = $1
                AND er.bucket >= $2
                AND er.bucket < $3
                GROUP BY day_of_week, hour
                ORDER BY day_of_week, hour
                """,
                factory_id,
                start_date,
                end_date
            )
            
            return [dict(row) for row in rows]
    
    async def get_peak_demand(
        self,
        factory_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> Tuple[Decimal, datetime]:
        """Get peak power demand and timestamp."""
        async with self.db.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 
                    er.max_power_kw as peak_kw,
                    er.bucket as timestamp
                FROM energy_readings_1hour er
                JOIN machines m ON er.machine_id = m.id
                WHERE m.factory_id = $1
                AND er.bucket >= $2
                AND er.bucket < $3
                ORDER BY er.max_power_kw DESC
                LIMIT 1
                """,
                factory_id,
                start_date,
                end_date
            )
            
            if row:
                return (row['peak_kw'], row['timestamp'])
            return (Decimal('0'), start_date)
    
    async def get_top_consumers(
        self,
        factory_id: str,
        start_date: datetime,
        end_date: datetime,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get top energy consuming machines."""
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT 
                    m.id,
                    m.name,
                    m.type,
                    m.rated_power_kw,
                    SUM(er.avg_power_kw * 1.0) as total_kwh,
                    AVG(er.avg_power_kw) as avg_power_kw,
                    MAX(er.max_power_kw) as peak_power_kw,
                    COUNT(*) as hours_run
                FROM energy_readings_1hour er
                JOIN machines m ON er.machine_id = m.id
                WHERE m.factory_id = $1
                AND er.bucket >= $2
                AND er.bucket < $3
                GROUP BY m.id, m.name, m.type, m.rated_power_kw
                ORDER BY total_kwh DESC
                LIMIT $4
                """,
                factory_id,
                start_date,
                end_date,
                limit
            )
            
            return [dict(row) for row in rows]
    
    async def get_machine_profile(
        self,
        machine_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Get detailed machine profile data."""
        async with self.db.pool.acquire() as conn:
            # Machine info
            machine_info = await conn.fetchrow(
                """
                SELECT 
                    m.id, m.name, m.type, m.description,
                    m.manufacturer, m.model, m.rated_power_kw,
                    m.location_in_factory, f.name as factory_name
                FROM machines m
                JOIN factories f ON m.factory_id = f.id
                WHERE m.id = $1
                """,
                machine_id
            )
            
            if not machine_info:
                return None
            
            # Energy statistics
            energy_stats = await conn.fetchrow(
                """
                SELECT 
                    SUM(er.avg_power_kw * 1.0) as total_kwh,
                    AVG(er.avg_power_kw) as avg_power_kw,
                    MAX(er.max_power_kw) as peak_power_kw,
                    MIN(er.min_power_kw) as min_power_kw,
                    COUNT(*) as hours_run
                FROM energy_readings_1hour er
                WHERE er.machine_id = $1
                AND er.bucket >= $2
                AND er.bucket < $3
                """,
                machine_id,
                start_date,
                end_date
            )
            
            # Daily trend
            daily_trend = await conn.fetch(
                """
                SELECT 
                    DATE(er.bucket) as date,
                    SUM(er.avg_power_kw * 24.0) as total_kwh
                FROM energy_readings_1day er
                WHERE er.machine_id = $1
                AND er.bucket >= $2
                AND er.bucket < $3
                GROUP BY DATE(er.bucket)
                ORDER BY date
                """,
                machine_id,
                start_date,
                end_date
            )
            
            # Efficiency (runtime vs capacity)
            efficiency = (float(energy_stats['avg_power_kw']) / float(machine_info['rated_power_kw']) * 100 
                         if machine_info['rated_power_kw'] > 0 else 0)
            
            # Production data
            production_stats = await conn.fetchrow(
                """
                SELECT 
                    SUM(pd.total_production_count) as total_production,
                    SUM(pd.total_production_good) as good_units,
                    SUM(pd.total_production_bad) as defect_units,
                    AVG(pd.avg_throughput) as avg_throughput
                FROM production_data_1hour pd
                WHERE pd.machine_id = $1
                AND pd.bucket >= $2
                AND pd.bucket < $3
                """,
                machine_id,
                start_date,
                end_date
            )
            
            # Calculate SEC (Specific Energy Consumption)
            total_production = float(production_stats['total_production']) if production_stats and production_stats['total_production'] else 0
            sec = float(energy_stats['total_kwh']) / total_production if total_production > 0 else 0
            
            # Calculate baseline from previous comparable period
            # Use period immediately before current period with same duration
            period_duration = end_date - start_date
            baseline_end = start_date
            baseline_start = baseline_end - period_duration
            
            baseline_stats = await conn.fetchrow(
                """
                SELECT 
                    SUM(er.avg_power_kw * 1.0) as total_kwh,
                    AVG(er.avg_power_kw) as avg_power_kw
                FROM energy_readings_1hour er
                WHERE er.machine_id = $1
                AND er.bucket >= $2
                AND er.bucket < $3
                """,
                machine_id,
                baseline_start,
                baseline_end
            )
            
            # Use previous period if available, otherwise use 95% of current as target baseline
            baseline_kwh = float(baseline_stats['total_kwh']) if baseline_stats and baseline_stats['total_kwh'] else float(energy_stats['total_kwh']) * 0.95
            
            return {
                'machine_info': dict(machine_info),
                'energy_stats': dict(energy_stats),
                'production_stats': dict(production_stats) if production_stats else {},
                'daily_trend': [dict(row) for row in daily_trend],
                'efficiency_pct': round(efficiency, 1),
                'sec': round(sec, 3),
                'total_production': total_production,
                'baseline_kwh': round(baseline_kwh, 2)
            }
    
    async def get_cost_data(
        self,
        factory_id: str,
        start_date: datetime,
        end_date: datetime,
        electricity_rate: Decimal = Decimal('0.10')  # Default: $0.10/kWh
    ) -> Dict[str, Any]:
        """Get cost analysis data."""
        # Get total energy
        total_kwh = await self.get_total_energy(factory_id, start_date, end_date)
        
        # Calculate costs
        total_cost = total_kwh * electricity_rate
        
        # Get cost by category
        categories = await self.get_energy_by_category(factory_id, start_date, end_date)
        cost_breakdown = [
            {
                'category': cat['category'],
                'kwh': float(cat['total_kwh']),
                'cost': float(cat['total_kwh'] * electricity_rate),
                'percentage': float(cat['total_kwh'] / total_kwh * 100) if total_kwh > 0 else 0
            }
            for cat in categories
        ]
        
        # Get daily cost trend
        daily_trend = await self.get_daily_trend(factory_id, start_date, end_date)
        cost_trend = [
            {
                'date': row['date'],
                'kwh': float(row['total_kwh']),
                'cost': float(row['total_kwh'] * electricity_rate)
            }
            for row in daily_trend
        ]
        
        return {
            'total_kwh': float(total_kwh),
            'total_cost': float(total_cost),
            'electricity_rate': float(electricity_rate),
            'breakdown': cost_breakdown,
            'trend': cost_trend
        }
    
    async def get_carbon_data(
        self,
        factory_id: str,
        start_date: datetime,
        end_date: datetime,
        emission_factor: Decimal = Decimal('0.5')  # Default: 0.5 kg CO2/kWh
    ) -> Dict[str, Any]:
        """Get carbon footprint data."""
        # Get total energy
        total_kwh = await self.get_total_energy(factory_id, start_date, end_date)
        
        # Calculate emissions
        total_emissions = total_kwh * emission_factor
        
        # Get emissions by category
        categories = await self.get_energy_by_category(factory_id, start_date, end_date)
        emission_breakdown = [
            {
                'category': cat['category'],
                'kwh': float(cat['total_kwh']),
                'emissions_kg': float(cat['total_kwh'] * emission_factor),
                'percentage': float(cat['total_kwh'] / total_kwh * 100) if total_kwh > 0 else 0
            }
            for cat in categories
        ]
        
        # Calculate carbon intensity
        carbon_intensity = emission_factor
        
        return {
            'total_emissions_kg': float(total_emissions),
            'total_kwh': float(total_kwh),
            'emission_factor': float(emission_factor),
            'carbon_intensity': float(carbon_intensity),
            'breakdown': emission_breakdown
        }
    
    async def get_anomalies(
        self,
        factory_id: str,
        start_date: datetime,
        end_date: datetime,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get recent anomalies."""
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT 
                    a.id, a.machine_id, a.detected_at as timestamp,
                    a.severity, a.deviation_std_dev as energy_impact_kwh,
                    a.anomaly_type as description, a.is_resolved,
                    m.name as machine_name
                FROM anomalies a
                JOIN machines m ON a.machine_id = m.id
                WHERE m.factory_id = $1
                AND a.detected_at >= $2
                AND a.detected_at < $3
                ORDER BY a.detected_at DESC
                LIMIT $4
                """,
                factory_id,
                start_date,
                end_date,
                limit
            )
            
            return [dict(row) for row in rows]
    
    async def get_kpi_summary(
        self,
        factory_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Get high-level KPI summary for executive dashboard."""
        # Get total energy
        total_kwh = await self.get_total_energy(factory_id, start_date, end_date)
        
        # Get previous period for comparison
        period_length = end_date - start_date
        prev_start = start_date - period_length
        prev_end = start_date
        prev_kwh = await self.get_total_energy(factory_id, prev_start, prev_end)
        
        # Calculate change
        energy_change_pct = float((total_kwh - prev_kwh) / prev_kwh * 100) if prev_kwh > 0 else 0
        
        # Get cost data
        cost_data = await self.get_cost_data(factory_id, start_date, end_date)
        
        # Get carbon data
        carbon_data = await self.get_carbon_data(factory_id, start_date, end_date)
        
        # Calculate average efficiency (placeholder - would need more complex calculation)
        efficiency = 85.0  # Placeholder
        
        return {
            'total_energy_kwh': float(total_kwh),
            'previous_energy_kwh': float(prev_kwh),
            'energy_change_pct': round(energy_change_pct, 1),
            'total_cost': cost_data['total_cost'],
            'total_emissions_kg': carbon_data['total_emissions_kg'],
            'efficiency_pct': efficiency,
            'period_start': start_date,
            'period_end': end_date
        }
    
    async def get_operating_hours(
        self,
        factory_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> Tuple[int, int]:
        """Get operating hours and downtime hours."""
        async with self.db.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 
                    COUNT(*) as total_readings,
                    COUNT(CASE WHEN er.avg_power_kw > 0.1 THEN 1 END) as operating_readings
                FROM energy_readings_1hour er
                JOIN machines m ON er.machine_id = m.id
                WHERE m.factory_id = $1
                AND er.bucket >= $2
                AND er.bucket < $3
                """,
                factory_id,
                start_date,
                end_date
            )
            
            if row:
                # Divide by number of machines to get average hours
                machines_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM machines WHERE factory_id = $1",
                    factory_id
                )
                if machines_count and machines_count > 0:
                    operating_hours = int(row['operating_readings'] / machines_count)
                    total_hours = int(row['total_readings'] / machines_count)
                    downtime_hours = total_hours - operating_hours
                    return (operating_hours, downtime_hours)
            
            return (0, 0)
