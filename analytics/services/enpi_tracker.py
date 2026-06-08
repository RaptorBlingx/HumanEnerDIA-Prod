"""
EnPI (Energy Performance Indicator) Tracker Service

ISO 50001 Compliance Engine - Tracks energy performance vs baseline year,
calculates cumulative savings, monitors targets, and generates compliance reports.

Phase 3 Milestone 3.1
"""

import logging
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from decimal import Decimal
from database import db

logger = logging.getLogger(__name__)


@dataclass
class EnPIBaseline:
    """EnPI baseline period data"""
    id: str
    seu_id: str
    seu_name: str
    baseline_year: int
    baseline_start_date: date
    baseline_end_date: date
    baseline_energy_kwh: float
    baseline_production_units: int
    baseline_operating_hours: float
    baseline_sec: float  # Specific Energy Consumption (kWh/unit)
    is_active: bool


@dataclass
class EnPIPerformance:
    """EnPI performance tracking data"""
    id: str
    seu_id: str
    seu_name: str
    period_start: date
    period_end: date
    period_type: str  # monthly, quarterly, annual
    
    # Actual performance
    actual_energy_kwh: float
    actual_production_units: int
    actual_sec: float
    
    # Expected performance (based on baseline)
    expected_energy_kwh: float
    expected_sec: float
    
    # Deviation metrics
    deviation_kwh: float
    deviation_percent: float
    cumulative_savings_kwh: float
    cumulative_savings_usd: float
    
    # ISO 50001 status
    iso_status: str  # excellent, on_track, requires_attention, critical
    compliance_notes: Optional[str] = None


@dataclass
class EnergyTarget:
    """Energy reduction target"""
    id: str
    target_type: str  # seu or factory
    target_year: int
    target_description: str
    baseline_year: int
    baseline_energy_kwh: float
    target_reduction_percent: float
    target_energy_kwh: float
    target_savings_kwh: float
    current_energy_kwh: Optional[float]
    current_savings_kwh: Optional[float]
    progress_percent: Optional[float]
    status: str  # active, achieved, missed, cancelled
    deadline: Optional[date]


class EnPITracker:
    """
    EnPI Tracker Service - ISO 50001 Compliance Engine
    
    Responsibilities:
    - Track baseline year energy performance
    - Calculate expected vs actual energy consumption
    - Compute cumulative savings
    - Monitor energy reduction targets
    - Generate ISO 50001 compliance reports
    """
    
    def __init__(self):
        self.electricity_rate = 0.15  # USD per kWh (configurable)
    
    # ========================================================================
    # Baseline Management
    # ========================================================================
    
    async def create_baseline(
        self,
        seu_id: str,
        baseline_year: int,
        baseline_start_date: date,
        baseline_end_date: date,
        created_by: str = "system"
    ) -> EnPIBaseline:
        """
        Create EnPI baseline for SEU from historical data.
        
        Automatically calculates baseline metrics from actual data:
        - Total energy consumption
        - Total production units
        - Operating hours
        - Specific Energy Consumption (SEC)
        
        Args:
            seu_id: SEU UUID
            baseline_year: Baseline year (e.g., 2024)
            baseline_start_date: Start of baseline period
            baseline_end_date: End of baseline period
            created_by: User creating baseline
        
        Returns:
            Created EnPI baseline
        
        Raises:
            ValueError: If insufficient data or invalid dates
        """
        logger.info(f"[EnPI] Creating baseline for SEU {seu_id}, year {baseline_year}")
        
        # Validate dates
        if baseline_end_date <= baseline_start_date:
            raise ValueError("Baseline end date must be after start date")
        
        if baseline_year != baseline_start_date.year:
            raise ValueError("Baseline year must match start date year")
        
        # Get SEU name
        query_seu = "SELECT name FROM seus WHERE id = $1"
        async with db.pool.acquire() as conn:
            seu_record = await conn.fetchrow(query_seu, seu_id)
            if not seu_record:
                raise ValueError(f"SEU {seu_id} not found")
            seu_name = seu_record['name']
        
        # Calculate baseline metrics from historical data (use 1-day aggregates for performance)
        query_metrics = """
            SELECT 
                COALESCE(SUM(er.total_energy_kwh), 0) as total_energy,
                COUNT(DISTINCT er.bucket) * 24 as operating_hours
            FROM energy_readings_1day er
            JOIN machines m ON er.machine_id = m.id
            JOIN seus s ON m.id = ANY(s.machine_ids)
            WHERE s.id = $1
              AND er.bucket >= $2::date
              AND er.bucket <= $3::date
        """
        
        # Get production count separately (from production_data 1-day aggregate if exists)
        query_production = """
            SELECT COALESCE(SUM(pd.production_count), 0) as total_production
            FROM production_data pd
            JOIN machines m ON pd.machine_id = m.id
            JOIN seus s ON m.id = ANY(s.machine_ids)
            WHERE s.id = $1
              AND DATE(pd.time) >= $2
              AND DATE(pd.time) <= $3
        """
        
        async with db.pool.acquire() as conn:
            # Get energy metrics
            metrics = await conn.fetchrow(
                query_metrics,
                seu_id,
                baseline_start_date,
                baseline_end_date
            )
            
            # Get production count
            production = await conn.fetchrow(
                query_production,
                seu_id,
                baseline_start_date,
                baseline_end_date
            )
        
        if not metrics or metrics['total_energy'] == 0:
            raise ValueError(
                f"No energy data found for {seu_name} in baseline period "
                f"{baseline_start_date} to {baseline_end_date}"
            )
        
        baseline_energy = float(metrics['total_energy'])
        baseline_production = int(production['total_production']) if production and production['total_production'] else 0
        baseline_hours = float(metrics['operating_hours'])
        
        # Calculate SEC (Specific Energy Consumption)
        baseline_sec = (baseline_energy / baseline_production) if baseline_production > 0 else 0
        
        # Insert baseline record
        query_insert = """
            INSERT INTO enpi_baselines (
                seu_id, baseline_year, baseline_start_date, baseline_end_date,
                baseline_energy_kwh, baseline_production_units, baseline_operating_hours,
                baseline_sec, is_active, created_by
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, true, $9)
            RETURNING id
        """
        
        async with db.pool.acquire() as conn:
            baseline_id = await conn.fetchval(
                query_insert,
                seu_id, baseline_year, baseline_start_date, baseline_end_date,
                baseline_energy, baseline_production, baseline_hours,
                baseline_sec, created_by
            )
        
        logger.info(
            f"[EnPI] Created baseline {baseline_id} for {seu_name}: "
            f"{baseline_energy:.2f} kWh, {baseline_production} units, SEC={baseline_sec:.4f}"
        )
        
        return EnPIBaseline(
            id=str(baseline_id),
            seu_id=str(seu_id),
            seu_name=seu_name,
            baseline_year=baseline_year,
            baseline_start_date=baseline_start_date,
            baseline_end_date=baseline_end_date,
            baseline_energy_kwh=baseline_energy,
            baseline_production_units=baseline_production,
            baseline_operating_hours=baseline_hours,
            baseline_sec=baseline_sec,
            is_active=True
        )
    
    async def get_baseline(self, seu_id: str, baseline_year: Optional[int] = None) -> Optional[EnPIBaseline]:
        """
        Get active EnPI baseline for SEU.
        
        Args:
            seu_id: SEU UUID
            baseline_year: Specific year (optional, defaults to most recent active)
        
        Returns:
            EnPI baseline or None if not found
        """
        if baseline_year:
            query = """
                SELECT eb.*, s.name as seu_name
                FROM enpi_baselines eb
                JOIN seus s ON eb.seu_id = s.id
                WHERE eb.seu_id = $1 AND eb.baseline_year = $2 AND eb.is_active = true
            """
            params = [seu_id, baseline_year]
        else:
            query = """
                SELECT eb.*, s.name as seu_name
                FROM enpi_baselines eb
                JOIN seus s ON eb.seu_id = s.id
                WHERE eb.seu_id = $1 AND eb.is_active = true
                ORDER BY eb.baseline_year DESC
                LIMIT 1
            """
            params = [seu_id]
        
        async with db.pool.acquire() as conn:
            record = await conn.fetchrow(query, *params)
        
        if not record:
            return None
        
        return EnPIBaseline(
            id=str(record['id']),
            seu_id=str(record['seu_id']),
            seu_name=record['seu_name'],
            baseline_year=record['baseline_year'],
            baseline_start_date=record['baseline_start_date'],
            baseline_end_date=record['baseline_end_date'],
            baseline_energy_kwh=float(record['baseline_energy_kwh']),
            baseline_production_units=int(record['baseline_production_units']) if record['baseline_production_units'] else 0,
            baseline_operating_hours=float(record['baseline_operating_hours']) if record['baseline_operating_hours'] else 0,
            baseline_sec=float(record['baseline_sec']) if record['baseline_sec'] else 0,
            is_active=record['is_active']
        )
    
    # ========================================================================
    # Performance Tracking
    # ========================================================================
    
    async def track_performance(
        self,
        seu_id: str,
        period_start: date,
        period_end: date,
        period_type: str = "monthly"
    ) -> EnPIPerformance:
        """
        Track EnPI performance for period vs baseline.
        
        Calculates:
        - Actual energy consumption and SEC
        - Expected energy consumption (based on baseline SEC × actual production)
        - Deviation from baseline
        - Cumulative savings (year-to-date)
        - ISO 50001 compliance status
        
        Args:
            seu_id: SEU UUID
            period_start: Period start date
            period_end: Period end date
            period_type: monthly, quarterly, or annual
        
        Returns:
            EnPI performance record
        
        Raises:
            ValueError: If no baseline exists or insufficient data
        """
        logger.info(f"[EnPI] Tracking performance for SEU {seu_id}, period {period_start} to {period_end}")
        
        # Get baseline
        baseline = await self.get_baseline(seu_id)
        if not baseline:
            raise ValueError(f"No active baseline found for SEU {seu_id}")
        
        # Get actual performance for period (use 1-day aggregates)
        query_actual = """
            SELECT 
                COALESCE(SUM(er.total_energy_kwh), 0) as total_energy,
                COUNT(DISTINCT er.bucket) * 24 as operating_hours
            FROM energy_readings_1day er
            JOIN machines m ON er.machine_id = m.id
            JOIN seus s ON m.id = ANY(s.machine_ids)
            WHERE s.id = $1
              AND er.bucket >= $2::date
              AND er.bucket <= $3::date
        """
        
        query_production_actual = """
            SELECT COALESCE(SUM(pd.production_count), 0) as total_production
            FROM production_data pd
            JOIN machines m ON pd.machine_id = m.id
            JOIN seus s ON m.id = ANY(s.machine_ids)
            WHERE s.id = $1
              AND DATE(pd.time) >= $2
              AND DATE(pd.time) <= $3
        """
        
        async with db.pool.acquire() as conn:
            actual = await conn.fetchrow(query_actual, seu_id, period_start, period_end)
            production_actual = await conn.fetchrow(query_production_actual, seu_id, period_start, period_end)
        
        if not actual or actual['total_energy'] == 0:
            raise ValueError(f"No energy data found for period {period_start} to {period_end}")
        
        actual_energy = float(actual['total_energy'])
        actual_production = int(production_actual['total_production']) if production_actual and production_actual['total_production'] else 0
        actual_sec = (actual_energy / actual_production) if actual_production > 0 else 0
        
        # Calculate expected energy (based on baseline SEC × actual production)
        expected_energy = baseline.baseline_sec * actual_production if actual_production > 0 else baseline.baseline_energy_kwh
        expected_sec = baseline.baseline_sec
        
        # Calculate deviation
        deviation_kwh = actual_energy - expected_energy
        deviation_percent = (deviation_kwh / expected_energy * 100) if expected_energy > 0 else 0
        
        # Calculate cumulative savings (year-to-date)
        year_start = date(period_end.year, 1, 1)
        cumulative_savings_kwh = await self._calculate_cumulative_savings(
            seu_id, year_start, period_end, baseline
        )
        cumulative_savings_usd = cumulative_savings_kwh * self.electricity_rate
        
        # Determine ISO 50001 status
        iso_status = self._determine_enpi_status(deviation_percent)
        
        # Insert performance record
        query_insert = """
            INSERT INTO enpi_performance (
                seu_id, baseline_id, period_start, period_end, period_type,
                actual_energy_kwh, actual_production_units, actual_operating_hours, actual_sec,
                expected_energy_kwh, expected_sec,
                deviation_kwh, deviation_percent,
                cumulative_savings_kwh, cumulative_savings_usd,
                iso_status
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
            RETURNING id
        """
        
        async with db.pool.acquire() as conn:
            performance_id = await conn.fetchval(
                query_insert,
                seu_id, baseline.id, period_start, period_end, period_type,
                actual_energy, actual_production, float(actual['operating_hours']), actual_sec,
                expected_energy, expected_sec,
                deviation_kwh, deviation_percent,
                cumulative_savings_kwh, cumulative_savings_usd,
                iso_status
            )
        
        logger.info(
            f"[EnPI] Performance tracked: actual={actual_energy:.2f} kWh, "
            f"expected={expected_energy:.2f} kWh, deviation={deviation_percent:.1f}%, "
            f"status={iso_status}"
        )
        
        return EnPIPerformance(
            id=str(performance_id),
            seu_id=str(seu_id),
            seu_name=baseline.seu_name,
            period_start=period_start,
            period_end=period_end,
            period_type=period_type,
            actual_energy_kwh=actual_energy,
            actual_production_units=actual_production,
            actual_sec=actual_sec,
            expected_energy_kwh=expected_energy,
            expected_sec=expected_sec,
            deviation_kwh=deviation_kwh,
            deviation_percent=deviation_percent,
            cumulative_savings_kwh=cumulative_savings_kwh,
            cumulative_savings_usd=cumulative_savings_usd,
            iso_status=iso_status
        )
    
    async def _calculate_cumulative_savings(
        self,
        seu_id: str,
        year_start: date,
        period_end: date,
        baseline: EnPIBaseline
    ) -> float:
        """Calculate year-to-date cumulative savings (use 1-day aggregates)."""
        query_ytd_energy = """
            SELECT COALESCE(SUM(er.total_energy_kwh), 0) as ytd_energy
            FROM energy_readings_1day er
            JOIN machines m ON er.machine_id = m.id
            JOIN seus s ON m.id = ANY(s.machine_ids)
            WHERE s.id = $1
              AND er.bucket >= $2::date
              AND er.bucket <= $3::date
        """
        
        query_ytd_production = """
            SELECT COALESCE(SUM(pd.production_count), 0) as ytd_production
            FROM production_data pd
            JOIN machines m ON pd.machine_id = m.id
            JOIN seus s ON m.id = ANY(s.machine_ids)
            WHERE s.id = $1
              AND DATE(pd.time) >= $2
              AND DATE(pd.time) <= $3
        """
        
        async with db.pool.acquire() as conn:
            ytd_energy_result = await conn.fetchrow(query_ytd_energy, seu_id, year_start, period_end)
            ytd_production_result = await conn.fetchrow(query_ytd_production, seu_id, year_start, period_end)
        
        ytd_energy = float(ytd_energy_result['ytd_energy']) if ytd_energy_result else 0
        ytd_production = int(ytd_production_result['ytd_production']) if ytd_production_result and ytd_production_result['ytd_production'] else 0
        
        # Expected energy = baseline SEC × actual production
        expected_ytd = baseline.baseline_sec * ytd_production if ytd_production > 0 else ytd_energy
        
        # Cumulative savings = expected - actual (negative if overconsumption)
        return expected_ytd - ytd_energy
    
    def _determine_enpi_status(self, deviation_percent: float) -> str:
        """
        Determine ISO 50001 compliance status based on deviation from baseline.
        
        Status definitions:
        - excellent: >5% improvement (below baseline)
        - on_track: ±5% of baseline
        - requires_attention: 5-15% above baseline
        - critical: >15% above baseline
        """
        if deviation_percent < -5:
            return "excellent"
        elif deviation_percent <= 5:
            return "on_track"
        elif deviation_percent <= 15:
            return "requires_attention"
        else:
            return "critical"
    
    # ========================================================================
    # Target Management
    # ========================================================================
    
    async def create_target(
        self,
        target_type: str,
        seu_id: Optional[str],
        factory_id: Optional[str],
        target_year: int,
        target_description: str,
        baseline_year: int,
        target_reduction_percent: float,
        deadline: Optional[date] = None,
        created_by: str = "system"
    ) -> EnergyTarget:
        """
        Create energy reduction target.
        
        Args:
            target_type: 'seu' or 'factory'
            seu_id: SEU UUID (if SEU target)
            factory_id: Factory UUID (if factory target)
            target_year: Target year
            target_description: Description
            baseline_year: Reference baseline year
            target_reduction_percent: Target reduction % (e.g., 10 for 10% reduction)
            deadline: Target deadline
            created_by: User creating target
        
        Returns:
            Created energy target
        """
        logger.info(f"[EnPI] Creating {target_type} target: {target_reduction_percent}% reduction by {target_year}")
        
        # Get baseline energy
        if target_type == "seu":
            baseline = await self.get_baseline(seu_id, baseline_year)
            if not baseline:
                raise ValueError(f"No baseline found for SEU {seu_id}, year {baseline_year}")
            baseline_energy = baseline.baseline_energy_kwh
        else:
            # Factory-wide baseline (sum of all SEUs)
            query = """
                SELECT COALESCE(SUM(baseline_energy_kwh), 0) as total_baseline
                FROM enpi_baselines eb
                JOIN seus s ON eb.seu_id = s.id
                JOIN machines m ON m.id = ANY(s.machine_ids)
                WHERE m.factory_id = $1 AND eb.baseline_year = $2 AND eb.is_active = true
            """
            async with db.pool.acquire() as conn:
                result = await conn.fetchval(query, factory_id, baseline_year)
            baseline_energy = float(result) if result else 0
            
            if baseline_energy == 0:
                raise ValueError(f"No baselines found for factory {factory_id}, year {baseline_year}")
        
        # Calculate target values
        target_savings_kwh = baseline_energy * (target_reduction_percent / 100)
        target_energy_kwh = baseline_energy - target_savings_kwh
        
        # Insert target
        query_insert = """
            INSERT INTO energy_targets (
                target_type, seu_id, factory_id, target_year, target_description,
                baseline_year, baseline_energy_kwh,
                target_reduction_percent, target_energy_kwh, target_savings_kwh,
                status, deadline, created_by
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 'active', $11, $12)
            RETURNING id
        """
        
        async with db.pool.acquire() as conn:
            target_id = await conn.fetchval(
                query_insert,
                target_type, seu_id, factory_id, target_year, target_description,
                baseline_year, baseline_energy,
                target_reduction_percent, target_energy_kwh, target_savings_kwh,
                deadline, created_by
            )
        
        logger.info(
            f"[EnPI] Created target {target_id}: reduce {target_reduction_percent}% "
            f"({target_savings_kwh:.2f} kWh) from {baseline_energy:.2f} kWh"
        )
        
        return EnergyTarget(
            id=str(target_id),
            target_type=target_type,
            target_year=target_year,
            target_description=target_description,
            baseline_year=baseline_year,
            baseline_energy_kwh=baseline_energy,
            target_reduction_percent=target_reduction_percent,
            target_energy_kwh=target_energy_kwh,
            target_savings_kwh=target_savings_kwh,
            current_energy_kwh=None,
            current_savings_kwh=None,
            progress_percent=None,
            status="active",
            deadline=deadline
        )
    
    async def update_target_progress(self, target_id: str) -> EnergyTarget:
        """
        Update energy target progress with current year-to-date data.
        
        Calculates:
        - Current year-to-date energy consumption
        - Current savings vs baseline
        - Progress % towards target
        - Updates status (active, achieved, at risk)
        """
        # Get target details
        query_target = """
            SELECT * FROM energy_targets WHERE id = $1
        """
        
        async with db.pool.acquire() as conn:
            target = await conn.fetchrow(query_target, target_id)
        
        if not target:
            raise ValueError(f"Target {target_id} not found")
        
        # Calculate current YTD energy
        year_start = date(target['target_year'], 1, 1)
        today = date.today()
        
        if target['target_type'] == 'seu':
            query_ytd = """
                SELECT COALESCE(SUM(total_energy_kwh), 0) as ytd_energy
                FROM energy_readings_1day er
                JOIN machines m ON er.machine_id = m.id
                JOIN seus s ON m.id = ANY(s.machine_ids)
                WHERE s.id = $1
                  AND er.bucket >= $2::date
                  AND er.bucket <= $3::date
            """
            params = [target['seu_id'], year_start, today]
        else:
            query_ytd = """
                SELECT COALESCE(SUM(total_energy_kwh), 0) as ytd_energy
                FROM energy_readings_1day er
                JOIN machines m ON er.machine_id = m.id
                WHERE m.factory_id = $1
                  AND er.bucket >= $2::date
                  AND er.bucket <= $3::date
            """
            params = [target['factory_id'], year_start, today]
        
        async with db.pool.acquire() as conn:
            ytd_energy = float(await conn.fetchval(query_ytd, *params))
        
        # Calculate savings and progress
        baseline_energy = float(target['baseline_energy_kwh'])
        current_savings = baseline_energy - ytd_energy
        target_savings = float(target['target_savings_kwh'])
        
        # Calculate progress (cap at 999.99% to fit NUMERIC(5,2) constraint)
        progress_percent = (current_savings / target_savings * 100) if target_savings > 0 else 0
        progress_percent = min(999.99, max(-999.99, progress_percent))  # Cap to field limits
        
        # Determine status
        if progress_percent >= 100:
            status = "achieved"
        elif progress_percent < 50 and today.month > 6:  # Behind at mid-year
            status = "at_risk"
        else:
            status = "active"
        
        # Update target
        query_update = """
            UPDATE energy_targets
            SET current_energy_kwh = $1,
                current_savings_kwh = $2,
                progress_percent = $3,
                status = $4,
                updated_at = NOW()
            WHERE id = $5
        """
        
        async with db.pool.acquire() as conn:
            await conn.execute(
                query_update,
                ytd_energy, current_savings, progress_percent, status, target_id
            )
        
        logger.info(
            f"[EnPI] Target {target_id} progress: {progress_percent:.1f}% "
            f"({current_savings:.2f}/{target_savings:.2f} kWh), status={status}"
        )
        
        return EnergyTarget(
            id=str(target_id),
            target_type=target['target_type'],
            target_year=target['target_year'],
            target_description=target['target_description'],
            baseline_year=target['baseline_year'],
            baseline_energy_kwh=baseline_energy,
            target_reduction_percent=float(target['target_reduction_percent']),
            target_energy_kwh=float(target['target_energy_kwh']),
            target_savings_kwh=target_savings,
            current_energy_kwh=ytd_energy,
            current_savings_kwh=current_savings,
            progress_percent=progress_percent,
            status=status,
            deadline=target['deadline']
        )
    
    # ========================================================================
    # ISO 50001 REPORTING METHODS (Phase 3 Milestone 3.2)
    # ========================================================================
    
    async def generate_enpi_report(
        self,
        factory_id: str,
        period: str,  # Format: "2025-Q3" or "2025" for annual
        baseline_year: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Generate comprehensive ISO 50001 EnPI compliance report
        
        Args:
            factory_id: Factory UUID
            period: Report period ("YYYY-QN" for quarterly or "YYYY" for annual)
            baseline_year: Baseline year (auto-detected if None)
        
        Returns:
            Complete EnPI report with overall performance and SEU breakdown
        """
        logger.info(f"[EnPI Report] Generating report for factory {factory_id}, period {period}")
        
        # Parse period
        period_info = self._parse_report_period(period)
        period_start = period_info['start_date']
        period_end = period_info['end_date']
        period_year = period_info['year']
        period_type = period_info['type']
        
        # Get all SEUs for factory
        query_seus = """
            SELECT DISTINCT s.id, s.name, es.name as energy_source
            FROM seus s
            JOIN energy_sources es ON s.energy_source_id = es.id
            JOIN machines m ON m.id = ANY(s.machine_ids)
            WHERE m.factory_id = $1
        """
        
        async with db.pool.acquire() as conn:
            seus = await conn.fetch(query_seus, factory_id)
        
        if not seus:
            raise ValueError(f"No SEUs found for factory {factory_id}")
        
        # Aggregate performance across all SEUs
        seu_breakdown = []
        total_baseline_energy = 0
        total_actual_energy = 0
        total_savings_kwh = 0
        total_savings_usd = 0
        seus_analyzed = 0
        
        for seu in seus:
            seu_id = str(seu['id'])
            seu_name = seu['name']
            
            # Get baseline
            baseline = await self.get_baseline(seu_id, baseline_year)
            if not baseline:
                logger.warning(f"[EnPI Report] No baseline for {seu_name}, skipping")
                continue
            
            # Track performance for the period
            try:
                performance = await self.track_performance(
                    seu_id=seu_id,
                    period_start=period_start,
                    period_end=period_end,
                    period_type=period_type
                )
                
                # BUGFIX (Phase 4.1): Use expected_energy_kwh (period-specific) not baseline_energy_kwh (historical)
                # baseline_energy_kwh is historical reference, expected_energy_kwh is baseline × actual production
                seu_breakdown.append({
                    "seu_name": seu_name,
                    "energy_source": seu['energy_source'],
                    "baseline_energy_kwh": round(performance.expected_energy_kwh, 2),  # FIX: was baseline.baseline_energy_kwh
                    "actual_energy_kwh": round(performance.actual_energy_kwh, 2),
                    "deviation_kwh": round(performance.deviation_kwh, 2),
                    "deviation_percent": round(performance.deviation_percent, 2),
                    "savings_kwh": round(-performance.deviation_kwh if performance.deviation_kwh < 0 else 0, 2),
                    "iso_status": performance.iso_status
                })
                
                total_baseline_energy += performance.expected_energy_kwh
                total_actual_energy += performance.actual_energy_kwh
                total_savings_kwh += performance.cumulative_savings_kwh
                total_savings_usd += performance.cumulative_savings_usd
                seus_analyzed += 1
                
            except Exception as e:
                logger.error(f"[EnPI Report] Error tracking {seu_name}: {e}")
                continue
        
        # Calculate overall deviation
        overall_deviation_kwh = total_actual_energy - total_baseline_energy
        overall_deviation_percent = (overall_deviation_kwh / total_baseline_energy * 100) if total_baseline_energy > 0 else 0
        
        # Determine overall ISO status
        overall_status = self._determine_enpi_status(overall_deviation_percent)
        
        # Get action plans summary
        action_plans_summary = await self._get_action_plans_summary(factory_id)
        
        report = {
            "factory_id": factory_id,
            "report_period": period,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "baseline_year": baseline_year or (period_year - 1),
            "seus_analyzed": seus_analyzed,
            "overall_performance": {
                "total_energy_baseline_kwh": round(total_baseline_energy, 2),
                "total_energy_actual_kwh": round(total_actual_energy, 2),
                "deviation_kwh": round(overall_deviation_kwh, 2),
                "deviation_percent": round(overall_deviation_percent, 2),
                "cumulative_savings_kwh": round(total_savings_kwh, 2),
                "cumulative_savings_usd": round(total_savings_usd, 2),
                "iso_status": overall_status
            },
            "seu_breakdown": seu_breakdown,
            "action_plans_status": action_plans_summary,
            "generated_at": datetime.now().isoformat()
        }
        
        logger.info(
            f"[EnPI Report] Complete: {seus_analyzed} SEUs, "
            f"deviation {overall_deviation_percent:.2f}%, status={overall_status}"
        )
        
        return report
    
    def _parse_report_period(self, period: str) -> Dict[str, Any]:
        """Parse period string into start/end dates"""
        if 'Q' in period:  # Quarterly: "2025-Q3"
            year, quarter = period.split('-Q')
            year = int(year)
            quarter = int(quarter)
            
            quarter_starts = {
                1: (1, 1), 2: (4, 1), 3: (7, 1), 4: (10, 1)
            }
            quarter_ends = {
                1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)
            }
            
            start_month, start_day = quarter_starts[quarter]
            end_month, end_day = quarter_ends[quarter]
            
            return {
                'year': year,
                'type': 'quarterly',
                'start_date': date(year, start_month, start_day),
                'end_date': date(year, end_month, end_day)
            }
        else:  # Annual: "2025"
            year = int(period)
            return {
                'year': year,
                'type': 'annual',
                'start_date': date(year, 1, 1),
                'end_date': date(year, 12, 31)
            }
    
    async def _get_action_plans_summary(self, factory_id: str) -> Dict[str, int]:
        """Get action plans status summary for factory"""
        query = """
            SELECT 
                COUNT(*) FILTER (WHERE status = 'completed') as completed,
                COUNT(*) FILTER (WHERE status = 'in_progress') as in_progress,
                COUNT(*) FILTER (WHERE status = 'planned') as planned,
                COUNT(*) FILTER (WHERE status = 'cancelled') as cancelled,
                COUNT(*) FILTER (WHERE status = 'on_hold') as on_hold,
                COUNT(*) as total_plans
            FROM action_plans
            WHERE factory_id = $1
        """
        
        async with db.pool.acquire() as conn:
            result = await conn.fetchrow(query, factory_id)
        
        return {
            "total_plans": result['total_plans'] or 0,
            "completed": result['completed'] or 0,
            "in_progress": result['in_progress'] or 0,
            "planned": result['planned'] or 0,
            "cancelled": result['cancelled'] or 0,
            "on_hold": result['on_hold'] or 0
        }
    
    # ========================================================================
    # ACTION PLAN MANAGEMENT (Phase 3 Milestone 3.2)
    # ========================================================================
    
    async def create_action_plan(
        self,
        title: str,
        objective: str,
        target_savings_kwh: float,
        responsible_person: str,
        target_date: date,
        seu_id: Optional[str] = None,
        factory_id: Optional[str] = None,
        description: Optional[str] = None,
        priority: str = "medium",
        estimated_investment_usd: Optional[float] = None,
        created_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create new energy improvement action plan
        
        Args:
            title: Action plan title
            objective: Improvement objective
            target_savings_kwh: Expected annual energy savings (kWh/year)
            responsible_person: Person responsible for execution
            target_date: Target completion date
            seu_id: SEU ID if action is SEU-specific
            factory_id: Factory ID if action is factory-wide
            description: Detailed description
            priority: Priority level (low, medium, high, critical)
            estimated_investment_usd: Estimated cost
            created_by: User creating the plan
        
        Returns:
            Created action plan details
        """
        logger.info(f"[Action Plan] Creating: {title}")
        
        # Calculate target savings USD (assuming $0.15/kWh)
        target_savings_usd = target_savings_kwh * 0.15
        
        query = """
            INSERT INTO action_plans (
                seu_id, factory_id, title, objective, description,
                target_savings_kwh, target_savings_usd,
                status, priority,
                responsible_person, target_date,
                estimated_investment_usd, created_by
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            RETURNING id, created_at, payback_period_months
        """
        
        async with db.pool.acquire() as conn:
            result = await conn.fetchrow(
                query,
                seu_id, factory_id, title, objective, description,
                target_savings_kwh, target_savings_usd,
                'planned', priority,
                responsible_person, target_date,
                estimated_investment_usd, created_by
            )
        
        action_plan = {
            "id": str(result['id']),
            "title": title,
            "objective": objective,
            "description": description,
            "target_savings_kwh": target_savings_kwh,
            "target_savings_usd": target_savings_usd,
            "status": "planned",
            "priority": priority,
            "responsible_person": responsible_person,
            "target_date": target_date.isoformat(),
            "estimated_investment_usd": estimated_investment_usd,
            "payback_period_months": float(result['payback_period_months']) if result['payback_period_months'] else None,
            "created_at": result['created_at'].isoformat()
        }
        
        logger.info(f"[Action Plan] Created: {action_plan['id']} - {title}")
        return action_plan
    
    async def get_action_plans(
        self,
        factory_id: Optional[str] = None,
        seu_id: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get action plans with optional filtering
        
        Args:
            factory_id: Filter by factory
            seu_id: Filter by SEU
            status: Filter by status (planned, in_progress, completed, etc.)
            priority: Filter by priority (low, medium, high, critical)
        
        Returns:
            List of action plans
        """
        conditions = []
        params = []
        param_count = 1
        
        if factory_id:
            conditions.append(f"factory_id = ${param_count}")
            params.append(factory_id)
            param_count += 1
        
        if seu_id:
            conditions.append(f"seu_id = ${param_count}")
            params.append(seu_id)
            param_count += 1
        
        if status:
            conditions.append(f"status = ${param_count}")
            params.append(status)
            param_count += 1
        
        if priority:
            conditions.append(f"priority = ${param_count}")
            params.append(priority)
            param_count += 1
        
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        
        query = f"""
            SELECT 
                ap.id, ap.title, ap.objective, ap.description,
                ap.target_savings_kwh, ap.target_savings_usd,
                ap.actual_savings_kwh, ap.actual_savings_usd,
                ap.status, ap.priority, ap.progress_percent,
                ap.responsible_person, ap.responsible_department,
                ap.start_date, ap.target_date, ap.completion_date,
                ap.estimated_investment_usd, ap.actual_investment_usd,
                ap.payback_period_months,
                ap.completion_notes,
                ap.created_at, ap.updated_at,
                s.name as seu_name
            FROM action_plans ap
            LEFT JOIN seus s ON ap.seu_id = s.id
            {where_clause}
            ORDER BY 
                CASE ap.priority 
                    WHEN 'critical' THEN 1
                    WHEN 'high' THEN 2
                    WHEN 'medium' THEN 3
                    WHEN 'low' THEN 4
                END,
                ap.target_date ASC
        """
        
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        
        action_plans = []
        for row in rows:
            action_plans.append({
                "id": str(row['id']),
                "title": row['title'],
                "objective": row['objective'],
                "description": row['description'],
                "seu_name": row['seu_name'],
                "target_savings_kwh": float(row['target_savings_kwh']) if row['target_savings_kwh'] else None,
                "target_savings_usd": float(row['target_savings_usd']) if row['target_savings_usd'] else None,
                "actual_savings_kwh": float(row['actual_savings_kwh']) if row['actual_savings_kwh'] else None,
                "actual_savings_usd": float(row['actual_savings_usd']) if row['actual_savings_usd'] else None,
                "status": row['status'],
                "priority": row['priority'],
                "progress_percent": float(row['progress_percent']) if row['progress_percent'] else 0,
                "responsible_person": row['responsible_person'],
                "responsible_department": row['responsible_department'],
                "start_date": row['start_date'].isoformat() if row['start_date'] else None,
                "target_date": row['target_date'].isoformat() if row['target_date'] else None,
                "completion_date": row['completion_date'].isoformat() if row['completion_date'] else None,
                "estimated_investment_usd": float(row['estimated_investment_usd']) if row['estimated_investment_usd'] else None,
                "actual_investment_usd": float(row['actual_investment_usd']) if row['actual_investment_usd'] else None,
                "payback_period_months": float(row['payback_period_months']) if row['payback_period_months'] else None,
                "completion_notes": row['completion_notes'],
                "created_at": row['created_at'].isoformat(),
                "updated_at": row['updated_at'].isoformat()
            })
        
        logger.info(f"[Action Plans] Retrieved {len(action_plans)} plans")
        return action_plans
    
    async def update_action_plan_progress(
        self,
        action_plan_id: str,
        status: Optional[str] = None,
        progress_percent: Optional[float] = None,
        actual_savings_kwh: Optional[float] = None,
        actual_investment_usd: Optional[float] = None,
        completion_notes: Optional[str] = None,
        start_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Update action plan progress and status
        
        Args:
            action_plan_id: Action plan UUID
            status: New status (planned, in_progress, completed, cancelled, on_hold)
            progress_percent: Progress percentage (0-100)
            actual_savings_kwh: Measured energy savings achieved
            actual_investment_usd: Actual investment cost
            completion_notes: Notes on completion or cancellation
            start_date: Actual start date
        
        Returns:
            Updated action plan details
        """
        logger.info(f"[Action Plan] Updating {action_plan_id}: status={status}, progress={progress_percent}%")
        
        # Build dynamic update query
        updates = []
        params = []
        param_count = 1
        
        if status:
            updates.append(f"status = ${param_count}")
            params.append(status)
            param_count += 1
        
        if progress_percent is not None:
            updates.append(f"progress_percent = ${param_count}")
            params.append(min(100, max(0, progress_percent)))  # Clamp 0-100
            param_count += 1
        
        if actual_savings_kwh is not None:
            updates.append(f"actual_savings_kwh = ${param_count}")
            params.append(actual_savings_kwh)
            param_count += 1
            # Calculate USD
            updates.append(f"actual_savings_usd = ${param_count}")
            params.append(actual_savings_kwh * 0.15)
            param_count += 1
        
        if actual_investment_usd is not None:
            updates.append(f"actual_investment_usd = ${param_count}")
            params.append(actual_investment_usd)
            param_count += 1
        
        if completion_notes:
            updates.append(f"completion_notes = ${param_count}")
            params.append(completion_notes)
            param_count += 1
        
        if start_date:
            updates.append(f"start_date = ${param_count}")
            params.append(start_date)
            param_count += 1
        
        if not updates:
            raise ValueError("No updates provided")
        
        # Add action_plan_id as last parameter
        params.append(action_plan_id)
        
        query = f"""
            UPDATE action_plans
            SET {', '.join(updates)}
            WHERE id = ${param_count}
            RETURNING 
                id, title, status, progress_percent,
                actual_savings_kwh, actual_savings_usd,
                payback_period_months, completion_date,
                updated_at
        """
        
        async with db.pool.acquire() as conn:
            result = await conn.fetchrow(query, *params)
        
        if not result:
            raise ValueError(f"Action plan {action_plan_id} not found")
        
        updated_plan = {
            "id": str(result['id']),
            "title": result['title'],
            "status": result['status'],
            "progress_percent": float(result['progress_percent']),
            "actual_savings_kwh": float(result['actual_savings_kwh']) if result['actual_savings_kwh'] else None,
            "actual_savings_usd": float(result['actual_savings_usd']) if result['actual_savings_usd'] else None,
            "payback_period_months": float(result['payback_period_months']) if result['payback_period_months'] else None,
            "completion_date": result['completion_date'].isoformat() if result['completion_date'] else None,
            "updated_at": result['updated_at'].isoformat()
        }
        
        logger.info(f"[Action Plan] Updated {action_plan_id}: {updated_plan['status']}, {updated_plan['progress_percent']}%")
        return updated_plan
