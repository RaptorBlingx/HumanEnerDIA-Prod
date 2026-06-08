"""
Report Service
==============
Handles data fetching and processing for all report types.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import calendar
import asyncpg
from io import BytesIO

from database import db
from services.kpi_service import KPIService
from services.enpi_calculator import EnPICalculator


class ReportService:
    """Service for generating report data."""
    
    def __init__(self):
        self.kpi_service = KPIService()
        self.enpi_calculator = EnPICalculator()
    
    async def generate_monthly_enpi_data(
        self,
        year: int,
        month: int,
        factory_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Fetch all data needed for monthly EnPI report.
        
        Args:
            year: Report year
            month: Report month (1-12)
            factory_id: Optional factory filter
        
        Returns:
            Dictionary with all report sections
        """
        # Validate inputs
        if not 1 <= month <= 12:
            raise ValueError("Month must be between 1 and 12")
        
        # Calculate date range
        start_date = datetime(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        end_date = datetime(year, month, last_day, 23, 59, 59)
        
        # Fetch all data sections sequentially (using same connection)
        async with db.pool.acquire() as conn:
            summary = await self._get_executive_summary(conn, start_date, end_date, factory_id)
            enpis = await self._get_enpis(conn, start_date, end_date, factory_id)
            machines = await self._get_machine_consumption(conn, start_date, end_date, factory_id)
            daily = await self._get_daily_trend(conn, start_date, end_date, factory_id)
            anomalies = await self._get_anomalies(conn, start_date, end_date, factory_id)
            factory_name = await self._get_factory_name(conn, factory_id) if factory_id else "All Factories"
        
        # Build response
        month_name = start_date.strftime('%B')
        
        return {
            'year': year,
            'month': month,
            'period': f"{month_name} {year}",
            'factory_name': factory_name,
            'summary': summary,
            'enpis': enpis,
            'machines': machines,
            'daily_data': daily,
            'daily_stats': self._calculate_daily_stats(daily),
            'anomalies': anomalies,
            'recommendations': self._generate_recommendations(summary, machines, anomalies)
        }
    
    async def _get_executive_summary(
        self,
        conn: asyncpg.Connection,
        start_date: datetime,
        end_date: datetime,
        factory_id: Optional[int]
    ) -> Dict[str, Any]:
        """Get executive summary data."""
        factory_filter = "AND m.factory_id = $3" if factory_id else ""
        params = [start_date, end_date]
        if factory_id:
            params.append(factory_id)
        
        # Total consumption
        query = f"""
        SELECT 
            COALESCE(SUM(e.total_energy_kwh), 0) as total_kwh
        FROM energy_readings_1day e
        JOIN machines m ON e.machine_id = m.id
        WHERE e.bucket >= $1 AND e.bucket < $2
        {factory_filter}
        """
        row = await conn.fetchrow(query, *params)
        total_kwh = float(row['total_kwh']) if row else 0.0
        
        # Previous month consumption (for comparison)
        prev_start = start_date - timedelta(days=calendar.monthrange(start_date.year, start_date.month)[1])
        prev_params = [prev_start, start_date]
        if factory_id:
            prev_params.append(factory_id)
        
        prev_query = f"""
        SELECT 
            COALESCE(SUM(e.total_energy_kwh), 0) as total_kwh
        FROM energy_readings_1day e
        JOIN machines m ON e.machine_id = m.id
        WHERE e.bucket >= $1 AND e.bucket < $2
        {factory_filter}
        """
        prev_row = await conn.fetchrow(prev_query, *prev_params)
        prev_kwh = float(prev_row['total_kwh']) if prev_row else 0.0
        
        # Calculate change
        prev_change = 0.0
        if prev_kwh > 0:
            prev_change = ((total_kwh - prev_kwh) / prev_kwh) * 100
        
        # Anomaly counts
        anomaly_query = f"""
        SELECT 
            severity,
            COUNT(*) as count
        FROM anomalies a
        JOIN machines m ON a.machine_id = m.id
        WHERE a.detected_at >= $1 AND a.detected_at < $2
        {factory_filter}
        GROUP BY severity
        """
        anomaly_rows = await conn.fetch(anomaly_query, *params)
        
        anomaly_counts = {
            'critical': 0,
            'warning': 0,
            'normal': 0
        }
        for row in anomaly_rows:
            anomaly_counts[row['severity']] = row['count']
        
        return {
            'total_kwh': total_kwh,
            'prev_month_change': prev_change,
            'anomaly_counts': anomaly_counts
        }
    
    async def _get_enpis(
        self,
        conn: asyncpg.Connection,
        start_date: datetime,
        end_date: datetime,
        factory_id: Optional[int]
    ) -> List[Dict[str, Any]]:
        """Get EnPI values for the period."""
        factory_filter = "AND m.factory_id = $3" if factory_id else ""
        params = [start_date, end_date]
        if factory_id:
            params.append(factory_id)
        
        # SEC (Specific Energy Consumption) - kWh per unit
        sec_query = f"""
        SELECT 
            COALESCE(SUM(e.total_energy_kwh), 0) as total_kwh,
            COALESCE(SUM(p.total_production_count), 0) as total_units
        FROM energy_readings_1day e
        JOIN machines m ON e.machine_id = m.id
        LEFT JOIN production_data_1day p ON e.machine_id = p.machine_id AND e.bucket = p.bucket
        WHERE e.bucket >= $1 AND e.bucket < $2
        {factory_filter}
        """
        sec_row = await conn.fetchrow(sec_query, *params)
        
        sec_current = 0.0
        if sec_row and sec_row['total_units'] > 0:
            sec_current = float(sec_row['total_kwh']) / float(sec_row['total_units'])
        
        # Load Factor - average vs peak
        lf_query = f"""
        SELECT 
            COALESCE(AVG(e.avg_power_kw), 0) as avg_power,
            COALESCE(MAX(e.max_power_kw), 0) as peak_power
        FROM energy_readings_1day e
        JOIN machines m ON e.machine_id = m.id
        WHERE e.bucket >= $1 AND e.bucket < $2
        {factory_filter}
        """
        lf_row = await conn.fetchrow(lf_query, *params)
        
        load_factor = 0.0
        if lf_row and lf_row['peak_power'] > 0:
            load_factor = (float(lf_row['avg_power']) / float(lf_row['peak_power'])) * 100
        
        # Peak Demand
        peak_demand = float(lf_row['peak_power']) if lf_row else 0.0
        
        return [
            {
                'name': 'SEC (kWh/unit)',
                'current': round(sec_current, 2),
                'target': 1.5,  # Target from ISO dashboard
                'status': '✓ Good' if sec_current <= 1.5 else '⚠ Above Target'
            },
            {
                'name': 'Load Factor (%)',
                'current': round(load_factor, 2),
                'target': 75.0,  # Target from plan
                'status': '✓ Good' if load_factor >= 75 else '⚠ Below Target'
            },
            {
                'name': 'Peak Demand (kW)',
                'current': round(peak_demand, 2),
                'target': 500.0,  # Example target
                'status': '✓ Good' if peak_demand <= 500 else '⚠ Above Target'
            }
        ]
    
    async def _get_machine_consumption(
        self,
        conn: asyncpg.Connection,
        start_date: datetime,
        end_date: datetime,
        factory_id: Optional[int]
    ) -> List[Dict[str, Any]]:
        """Get consumption breakdown by machine."""
        # Build query
        if factory_id:
            query = """
            SELECT 
                m.id,
                m.name,
                COALESCE(SUM(e.total_energy_kwh), 0) as total_kwh
            FROM machines m
            LEFT JOIN energy_readings_1day e ON m.id = e.machine_id 
                AND e.bucket >= $1 AND e.bucket < $2
            WHERE m.factory_id = $3
            GROUP BY m.id, m.name
            ORDER BY total_kwh DESC
            """
            params = [start_date, end_date, factory_id]
        else:
            query = """
            SELECT 
                m.id,
                m.name,
                COALESCE(SUM(e.total_energy_kwh), 0) as total_kwh
            FROM machines m
            LEFT JOIN energy_readings_1day e ON m.id = e.machine_id 
                AND e.bucket >= $1 AND e.bucket < $2
            GROUP BY m.id, m.name
            ORDER BY total_kwh DESC
            """
            params = [start_date, end_date]
        
        rows = await conn.fetch(query, *params)
        
        # Calculate total for percentages
        grand_total = sum(float(row['total_kwh']) for row in rows)
        
        machines = []
        for row in rows:
            kwh = float(row['total_kwh'])
            percent = (kwh / grand_total * 100) if grand_total > 0 else 0
            
            machines.append({
                'machine_id': row['id'],
                'name': row['name'],
                'kwh': kwh,
                'percent': percent,
                'trend': '-'  # TODO: Calculate trend vs prev month
            })
        
        return machines
    
    async def _get_daily_trend(
        self,
        conn: asyncpg.Connection,
        start_date: datetime,
        end_date: datetime,
        factory_id: Optional[int]
    ) -> List[Dict[str, Any]]:
        """Get daily consumption trend."""
        factory_filter = "AND m.factory_id = $3" if factory_id else ""
        params = [start_date, end_date]
        if factory_id:
            params.append(factory_id)
        
        query = f"""
        SELECT 
            e.bucket::date as date,
            COALESCE(SUM(e.total_energy_kwh), 0) as total_kwh
        FROM energy_readings_1day e
        JOIN machines m ON e.machine_id = m.id
        WHERE e.bucket >= $1 AND e.bucket < $2
        {factory_filter}
        GROUP BY e.bucket::date
        ORDER BY date
        """
        
        rows = await conn.fetch(query, *params)
        
        return [
            {
                'date': row['date'].strftime('%Y-%m-%d'),
                'kwh': float(row['total_kwh'])
            }
            for row in rows
        ]
    
    def _calculate_daily_stats(self, daily_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate daily consumption statistics."""
        if not daily_data:
            return {}
        
        kwh_values = [d['kwh'] for d in daily_data]
        
        max_kwh = max(kwh_values)
        min_kwh = min(kwh_values)
        avg_kwh = sum(kwh_values) / len(kwh_values)
        
        max_idx = kwh_values.index(max_kwh)
        min_idx = kwh_values.index(min_kwh)
        
        return {
            'avg': avg_kwh,
            'max': max_kwh,
            'max_date': daily_data[max_idx]['date'],
            'min': min_kwh,
            'min_date': daily_data[min_idx]['date']
        }
    
    async def _get_anomalies(
        self,
        conn: asyncpg.Connection,
        start_date: datetime,
        end_date: datetime,
        factory_id: Optional[int]
    ) -> List[Dict[str, Any]]:
        """Get anomalies for the period."""
        factory_filter = "AND m.factory_id = $3" if factory_id else ""
        params = [start_date, end_date]
        if factory_id:
            params.append(factory_id)
        
        query = f"""
        SELECT 
            a.id,
            a.detected_at,
            a.severity,
            a.is_resolved,
            m.name
        FROM anomalies a
        JOIN machines m ON a.machine_id = m.id
        WHERE a.detected_at >= $1 AND a.detected_at < $2
        {factory_filter}
        ORDER BY a.detected_at DESC
        LIMIT 50
        """
        
        rows = await conn.fetch(query, *params)
        
        return [
            {
                'anomaly_id': row['id'],
                'detected_at': row['detected_at'],
                'severity': row['severity'],
                'is_resolved': row['is_resolved'],
                'machine': row['name']
            }
            for row in rows
        ]
    
    async def _get_factory_name(self, conn: asyncpg.Connection, factory_id: int) -> str:
        """Get factory name by ID."""
        query = "SELECT name FROM factories WHERE id = $1"
        row = await conn.fetchrow(query, factory_id)
        return row['name'] if row else f"Factory {factory_id}"
    
    def _generate_recommendations(
        self,
        summary: Dict[str, Any],
        machines: List[Dict[str, Any]],
        anomalies: List[Dict[str, Any]]
    ) -> List[str]:
        """Generate recommendations based on data analysis."""
        recs = []
        
        counts = summary.get('anomaly_counts', {})
        
        # Critical anomalies
        critical = counts.get('critical', 0)
        if critical > 0:
            unresolved = sum(1 for a in anomalies if a['severity'] == 'critical' and not a['is_resolved'])
            recs.append(f"⚠ {critical} critical anomalies detected - {unresolved} still open")
        
        # Warning anomalies
        warning = counts.get('warning', 0)
        if warning > 0:
            recs.append(f"⚠ {warning} warning-level anomalies require investigation")
        
        # High consumption machines
        if machines:
            top = machines[0]
            if top['percent'] > 30:
                recs.append(
                    f"{top['name']} accounts for {top['percent']:.1f}% of energy - "
                    f"prioritize for efficiency review"
                )
        
        # Month-over-month increase
        change = summary.get('prev_month_change', 0)
        if change > 10:
            recs.append(f"Consumption increased {change:.1f}% vs previous month - investigate root cause")
        
        # Generic best practices
        if not recs:
            recs.append("Continue regular monitoring of energy performance")
            recs.append("Review production schedules to optimize peak demand")
        
        return recs
