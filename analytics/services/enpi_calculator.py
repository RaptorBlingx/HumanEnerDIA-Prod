"""
EnMS Analytics Service - EnPI Calculator
=========================================
Business logic for ISO 50001 Energy Performance Indicator (EnPI) calculations.
Generates quarterly and annual compliance reports.

Author: EnMS Team
Phase: 3 - Analytics & ML (ISO 50001 Extension)
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, date
from uuid import UUID
import logging
from dateutil.relativedelta import relativedelta

from database import db
from models.seu import (
    PerformanceReportRequest,
    PerformanceReport,
    MonthlyBreakdown,
    ComplianceStatus,
    EnPIDataPoint,
    EnPITrendResponse
)
from services.seu_baseline_service import seu_baseline_service

logger = logging.getLogger(__name__)


class EnPICalculator:
    """
    Service for generating ISO 50001 EnPI reports.
    
    Calculates:
    - Actual energy consumption vs baseline expectation
    - Deviation percentage
    - Compliance status (green/yellow/red)
    - Quarterly and annual breakdowns
    """
    
    _instance = None
    
    def __new__(cls):
        """Singleton pattern to reuse instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def generate_performance_report(
        self,
        request: PerformanceReportRequest
    ) -> PerformanceReport:
        """
        Generate SEU energy performance report for a period.
        
        Args:
            request: Report parameters (seu_id, year, period)
            
        Returns:
            Performance report with actual vs expected consumption
            
        Raises:
            ValueError: If SEU not found or baseline not trained
        """
        logger.info(
            f"[ENPI-REPORT] Generating report for SEU {request.seu_id}: "
            f"{request.report_year}-{request.period}"
        )
        
        # Step 1: Get SEU details
        seu = await self._get_seu(request.seu_id)
        if not seu:
            raise ValueError(f"SEU not found: {request.seu_id}")
        
        # Step 2: Verify baseline exists
        baseline = await seu_baseline_service.get_seu_baseline(request.seu_id)
        if not baseline:
            raise ValueError(
                f"No baseline trained for SEU {request.seu_id}. "
                f"Train baseline first using POST /api/v1/baseline/seu/train"
            )
        
        if baseline['baseline_year'] != request.baseline_year:
            raise ValueError(
                f"Baseline year mismatch. SEU has baseline for {baseline['baseline_year']}, "
                f"requested {request.baseline_year}"
            )
        
        # Step 3: Calculate period dates
        period_start, period_end = self._calculate_period_dates(
            request.report_year,
            request.period
        )
        
        logger.info(f"[ENPI-REPORT] Period: {period_start} to {period_end}")
        
        # Step 4: Get actual consumption
        actual_consumption = await self._get_actual_consumption(
            request.seu_id,
            period_start,
            period_end
        )
        
        # Step 5: Calculate expected consumption using baseline formula
        expected_consumption = await seu_baseline_service.calculate_expected_consumption(
            request.seu_id,
            period_start,
            period_end
        )
        
        # Step 6: Calculate deviation
        deviation_kwh = actual_consumption - expected_consumption
        deviation_percent = (deviation_kwh / expected_consumption * 100) if expected_consumption > 0 else 0
        
        # Step 7: Determine compliance status
        compliance_status = self._get_compliance_status(deviation_percent)
        
        # Step 8: Calculate CUSUM before saving (needed for report and database)
        # Build report_period from the original period (may already include year)
        if '-' in str(request.period) and len(str(request.period).split('-')) == 2:
            # Period is in 'YYYY-MM' format, use as-is
            report_period = str(request.period)
        else:
            # Period is Q1-Q4, annual, or month number - prepend year
            report_period = f"{request.report_year}-{request.period}"
        
        cusum_deviation = await self._calculate_cusum(
            request.seu_id,
            report_period,
            deviation_percent
        )
        
        logger.info(
            f"[ENPI-REPORT] Actual: {actual_consumption:.2f} kWh, "
            f"Expected: {expected_consumption:.2f} kWh, "
            f"Deviation: {deviation_percent:.2f}%, "
            f"CUSUM: {cusum_deviation:.2f}%, "
            f"Status: {compliance_status}"
        )
        
        # Step 9: Generate monthly breakdown if quarterly report
        monthly_breakdown = None
        if request.period.startswith('Q'):
            monthly_breakdown = await self._generate_monthly_breakdown(
                request.seu_id,
                period_start,
                period_end
            )
        
        # Step 10: Save report to database
        await self._save_performance_report(
            seu_id=request.seu_id,
            report_period=report_period,
            period_start=period_start,
            period_end=period_end,
            baseline_year=request.baseline_year,
            actual_consumption=actual_consumption,
            expected_consumption=expected_consumption,
            deviation_kwh=deviation_kwh,
            deviation_percent=deviation_percent,
            cusum_deviation=cusum_deviation,
            compliance_status=compliance_status
        )
        
        return PerformanceReport(
            seu_id=request.seu_id,
            seu_name=seu['name'],
            energy_source=seu['energy_source_name'],
            report_period=report_period,
            period_start=period_start,
            period_end=period_end,
            baseline_year=request.baseline_year,
            actual_consumption=round(actual_consumption, 2),
            expected_consumption=round(expected_consumption, 2),
            deviation_kwh=round(deviation_kwh, 2),
            deviation_percent=round(deviation_percent, 2),
            cusum_deviation=round(cusum_deviation, 2),
            compliance_status=compliance_status,
            monthly_breakdown=monthly_breakdown,
            generated_at=datetime.utcnow()
        )
    
    async def get_enpi_trend(
        self,
        seu_id: UUID,
        start_year: int,
        end_year: int
    ) -> EnPITrendResponse:
        """
        Get EnPI trend data for multiple years.
        
        Args:
            seu_id: SEU identifier
            start_year: Start year for trend
            end_year: End year for trend
            
        Returns:
            EnPI trend data points
        """
        logger.info(
            f"[ENPI-TREND] Fetching trend for SEU {seu_id}: "
            f"{start_year} to {end_year}"
        )
        
        # Get SEU details
        seu = await self._get_seu(seu_id)
        if not seu:
            raise ValueError(f"SEU not found: {seu_id}")
        
        # Get baseline year
        baseline = await seu_baseline_service.get_seu_baseline(seu_id)
        if not baseline:
            raise ValueError(f"No baseline trained for SEU {seu_id}")
        
        baseline_year = baseline['baseline_year']
        
        # Fetch stored performance reports
        query = """
            SELECT 
                report_period,
                period_start,
                period_end,
                actual_consumption,
                expected_consumption,
                deviation_percent
            FROM seu_energy_performance
            WHERE seu_id = $1
              AND EXTRACT(YEAR FROM period_start) >= $2
              AND EXTRACT(YEAR FROM period_start) <= $3
            ORDER BY period_start
        """
        
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(query, seu_id, start_year, end_year)
        
        # Calculate baseline average for EnPI index
        baseline_avg = await self._get_baseline_average(seu_id, baseline_year)
        
        # Build data points
        data_points = []
        for row in rows:
            # Parse report_period (e.g., "2025-Q1" or "2025-annual")
            parts = row['report_period'].split('-')
            year = int(parts[0])
            quarter = parts[1] if len(parts) > 1 and parts[1].startswith('Q') else None
            
            # EnPI index: (actual / baseline_avg) * 100
            enpi_index = (row['actual_consumption'] / baseline_avg * 100) if baseline_avg > 0 else 100
            
            data_points.append(EnPIDataPoint(
                year=year,
                quarter=quarter,
                enpi_index=round(enpi_index, 2),
                deviation_percent=round(float(row['deviation_percent']), 2),
                actual_consumption=round(float(row['actual_consumption']), 2),
                expected_consumption=round(float(row['expected_consumption']), 2)
            ))
        
        return EnPITrendResponse(
            success=True,
            seu_id=seu_id,
            seu_name=seu['name'],
            baseline_year=baseline_year,
            data_points=data_points,
            timestamp=datetime.utcnow()
        )
    
    def _calculate_period_dates(
        self,
        year: int,
        period: str
    ) -> tuple[date, date]:
        """
        Calculate start and end dates for a reporting period.
        
        Args:
            year: Year
            period: 'Q1', 'Q2', 'Q3', 'Q4', 'annual', or month number (1-12) or 'YYYY-MM' format
            
        Returns:
            (start_date, end_date)
        """
        if period == 'annual':
            return date(year, 1, 1), date(year, 12, 31)
        
        # Check if period is in 'YYYY-MM' format (e.g., '2025-01')
        if '-' in str(period) and len(str(period).split('-')) == 2:
            try:
                period_year, period_month = str(period).split('-')
                period_year = int(period_year)
                period_month = int(period_month)
                
                # Use the year from the period format
                year = period_year
                period = period_month
            except ValueError:
                raise ValueError(f"Invalid period format: {period}. Use 'YYYY-MM' format (e.g., '2025-01')")
        
        # Check if period is a month number (1-12)
        try:
            month_num = int(period)
            if 1 <= month_num <= 12:
                start_date = date(year, month_num, 1)
                # Last day of the month
                if month_num == 12:
                    end_date = date(year, 12, 31)
                else:
                    end_date = date(year, month_num + 1, 1) - relativedelta(days=1)
                return start_date, end_date
        except (ValueError, TypeError):
            pass  # Not a month number, try quarter
        
        # Check if it's a quarter
        quarter_map = {
            'Q1': (1, 3),
            'Q2': (4, 6),
            'Q3': (7, 9),
            'Q4': (10, 12)
        }
        
        if period in quarter_map:
            start_month, end_month = quarter_map[period]
            start_date = date(year, start_month, 1)
            
            # Last day of end_month
            if end_month == 12:
                end_date = date(year, 12, 31)
            else:
                end_date = date(year, end_month + 1, 1) - relativedelta(days=1)
            
            return start_date, end_date
        
        raise ValueError(
            f"Invalid period: {period}. Must be Q1, Q2, Q3, Q4, annual, "
            f"month number (1-12), or 'YYYY-MM' format (e.g., '2025-01')"
        )
    
    async def _get_seu(self, seu_id: UUID) -> Optional[Dict[str, Any]]:
        """Get SEU details."""
        query = """
            SELECT 
                s.id,
                s.name,
                s.machine_ids,
                es.name as energy_source_name
            FROM seus s
            JOIN energy_sources es ON s.energy_source_id = es.id
            WHERE s.id = $1
        """
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(query, seu_id)
            return dict(row) if row else None
    
    async def _get_actual_consumption(
        self,
        seu_id: UUID,
        period_start: date,
        period_end: date
    ) -> float:
        """Get actual energy consumption for period using PostgreSQL function."""
        query = """
            SELECT get_seu_energy($1, $2::timestamptz, $3::timestamptz) as total_energy
        """
        async with db.pool.acquire() as conn:
            result = await conn.fetchval(query, seu_id, period_start, period_end)
            return float(result) if result else 0.0
    
    def _get_compliance_status(self, deviation_percent: float) -> ComplianceStatus:
        """
        Determine compliance status from deviation percentage.
        
        ISO 50001 thresholds:
        - ±0-3%: Compliant (green)
        - ±3-5%: Warning (yellow)
        - >±5%: Critical (red)
        """
        abs_dev = abs(deviation_percent)
        
        if abs_dev <= 3.0:
            return ComplianceStatus.COMPLIANT
        elif abs_dev <= 5.0:
            return ComplianceStatus.WARNING
        else:
            return ComplianceStatus.CRITICAL
    
    async def _generate_monthly_breakdown(
        self,
        seu_id: UUID,
        period_start: date,
        period_end: date
    ) -> List[MonthlyBreakdown]:
        """Generate monthly breakdown for quarterly report."""
        breakdown = []
        
        current = period_start
        while current <= period_end:
            # Calculate month boundaries
            month_start = current.replace(day=1)
            if current.month == 12:
                month_end = date(current.year, 12, 31)
            else:
                month_end = date(current.year, current.month + 1, 1) - relativedelta(days=1)
            
            # Get actual consumption
            actual = await self._get_actual_consumption(seu_id, month_start, month_end)
            
            # Get expected consumption
            expected = await seu_baseline_service.calculate_expected_consumption(
                seu_id,
                month_start,
                month_end
            )
            
            # Calculate deviation
            deviation_kwh = actual - expected
            deviation_percent = (deviation_kwh / expected * 100) if expected > 0 else 0
            
            breakdown.append(MonthlyBreakdown(
                month=month_start.strftime('%b'),
                actual=round(actual, 2),
                expected=round(expected, 2),
                deviation_kwh=round(deviation_kwh, 2),
                deviation_percent=round(deviation_percent, 2)
            ))
            
            # Move to next month
            current = month_end + relativedelta(days=1)
        
        return breakdown
    
    async def _save_performance_report(
        self,
        seu_id: UUID,
        report_period: str,
        period_start: date,
        period_end: date,
        baseline_year: int,
        actual_consumption: float,
        expected_consumption: float,
        deviation_kwh: float,
        deviation_percent: float,
        cusum_deviation: float,
        compliance_status: ComplianceStatus
    ):
        """Save or update performance report in database."""
        query = """
            INSERT INTO seu_energy_performance (
                seu_id, report_period, period_start, period_end, baseline_year,
                actual_consumption, expected_consumption,
                deviation_kwh, deviation_percent, cusum_deviation, compliance_status,
                generated_at, generated_by
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW(), 'analytics-service'
            )
            ON CONFLICT (seu_id, report_period)
            DO UPDATE SET
                actual_consumption = EXCLUDED.actual_consumption,
                expected_consumption = EXCLUDED.expected_consumption,
                deviation_kwh = EXCLUDED.deviation_kwh,
                deviation_percent = EXCLUDED.deviation_percent,
                cusum_deviation = EXCLUDED.cusum_deviation,
                compliance_status = EXCLUDED.compliance_status,
                generated_at = NOW()
        """
        
        async with db.pool.acquire() as conn:
            await conn.execute(
                query,
                seu_id,
                report_period,
                period_start,
                period_end,
                baseline_year,
                actual_consumption,
                expected_consumption,
                deviation_kwh,
                deviation_percent,
                cusum_deviation,
                compliance_status.value
            )
        
        logger.info(
            f"[ENPI-REPORT] Saved report: {report_period}, "
            f"Status: {compliance_status.value}, CUSUM: {cusum_deviation:.2f}%"
        )
    
    async def _calculate_cusum(
        self,
        seu_id: UUID,
        current_period: str,
        current_deviation: float
    ) -> float:
        """
        Calculate cumulative sum of deviation percentages.
        
        CUSUM helps detect persistent drift in energy performance.
        Alert if |CUSUM| > 50% (indicates 5+ months of consistent over/under consumption)
        
        Args:
            seu_id: SEU identifier
            current_period: Current report period (e.g., '2025-01')
            current_deviation: Current period deviation percentage
            
        Returns:
            Cumulative sum of deviation percentages
        """
        # Get previous periods' deviations (chronological order)
        query = """
            SELECT deviation_percent, cusum_deviation
            FROM seu_energy_performance
            WHERE seu_id = $1
              AND report_period < $2
            ORDER BY period_start DESC
            LIMIT 1
        """
        
        async with db.pool.acquire() as conn:
            previous = await conn.fetchrow(query, seu_id, current_period)
        
        if previous and previous['cusum_deviation'] is not None:
            # Continue CUSUM from previous period
            return float(previous['cusum_deviation']) + current_deviation
        else:
            # First period - CUSUM equals current deviation
            return current_deviation
    
    async def _get_baseline_average(
        self,
        seu_id: UUID,
        baseline_year: int
    ) -> float:
        """Get average consumption during baseline year."""
        query = """
            SELECT actual_consumption
            FROM seu_energy_performance
            WHERE seu_id = $1
              AND report_period = $2
        """
        
        report_period = f"{baseline_year}-annual"
        
        async with db.pool.acquire() as conn:
            result = await conn.fetchval(query, seu_id, report_period)
            
            if result:
                return float(result)
            
            # If annual report doesn't exist, calculate from quarterly
            query_quarterly = """
                SELECT SUM(actual_consumption)
                FROM seu_energy_performance
                WHERE seu_id = $1
                  AND EXTRACT(YEAR FROM period_start) = $2
                  AND report_period LIKE '%Q%'
            """
            
            result = await conn.fetchval(query_quarterly, seu_id, baseline_year)
            return float(result) if result else 0.0


# Global singleton instance
enpi_calculator = EnPICalculator()
