"""
EnMS Analytics Service - SEU API Routes
========================================
REST API endpoints for ISO 50001 SEU management and EnPI reporting.

Author: EnMS Team
Phase: 3 - Analytics & ML (ISO 50001 Extension)
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from datetime import datetime
from uuid import UUID
import logging

from models.seu import (
    SEUCreate,
    SEU,
    SEUWithMeta,
    SEUListResponse,
    TrainBaselineRequest,
    TrainBaselineResponse,
    PerformanceReportRequest,
    PerformanceReport,
    EnPITrendResponse,
    ErrorResponse,
    EnergySource
)
from services.seu_baseline_service import seu_baseline_service
from services.enpi_calculator import enpi_calculator
from database import db

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# SEU MANAGEMENT ENDPOINTS
# ============================================================================

@router.post("/seus", response_model=SEU, tags=["SEU Management"])
async def create_seu(request: SEUCreate):
    """
    Create a new SEU (Significant Energy User).
    
    **ISO 50001 Requirement:**
    - Group machines by energy significance
    - Each SEU tracks one energy source type
    
    **Example Request:**
    ```json
    {
        "name": "Compressor Group",
        "description": "All industrial air compressors",
        "energy_source_id": "uuid-of-electricity",
        "machine_ids": ["uuid-1", "uuid-2"]
    }
    ```
    
    **Returns:**
    - Created SEU with ID
    - No baseline trained yet (use POST /baseline/seu/train)
    """
    try:
        logger.info(f"[SEU-API] Creating SEU: {request.name}")
        
        # Verify energy source exists
        query_source = "SELECT id FROM energy_sources WHERE id = $1"
        async with db.pool.acquire() as conn:
            source_exists = await conn.fetchval(query_source, request.energy_source_id)
        
        if not source_exists:
            raise HTTPException(
                status_code=404,
                detail=f"Energy source not found: {request.energy_source_id}"
            )
        
        # Verify all machines exist
        query_machines = """
            SELECT COUNT(*) FROM machines WHERE id = ANY($1::uuid[])
        """
        async with db.pool.acquire() as conn:
            machine_count = await conn.fetchval(query_machines, request.machine_ids)
        
        if machine_count != len(request.machine_ids):
            raise HTTPException(
                status_code=404,
                detail=f"Some machines not found. Expected {len(request.machine_ids)}, found {machine_count}"
            )
        
        # Insert SEU
        query_insert = """
            INSERT INTO seus (
                name, description, energy_source_id, machine_ids, is_active
            ) VALUES (
                $1, $2, $3, $4, true
            )
            RETURNING id, name, description, energy_source_id, machine_ids,
                      is_active, created_at, updated_at
        """
        
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(
                query_insert,
                request.name,
                request.description,
                request.energy_source_id,
                request.machine_ids
            )
        
        seu = SEU(**dict(row))
        logger.info(f"[SEU-API] SEU created: {seu.id}")
        
        return seu
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[SEU-API] Create SEU failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/seus", response_model=SEUListResponse, tags=["SEU Management"])
async def list_seus(
    energy_source: Optional[str] = Query(None, description="Filter by energy source name"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    has_baseline: Optional[bool] = Query(None, description="Filter by baseline existence")
):
    """
    List all SEUs with metadata.
    
    **Query Parameters:**
    - `energy_source`: Filter by energy source (e.g., 'electricity')
    - `is_active`: Filter active/inactive SEUs
    - `has_baseline`: Filter SEUs with/without trained baseline
    
    **Returns:**
    - List of SEUs with machine count and last report period
    """
    try:
        logger.info(f"[SEU-API] Listing SEUs: energy_source={energy_source}, has_baseline={has_baseline}")
        
        query = """
            SELECT 
                s.id,
                s.name,
                s.description,
                s.energy_source_id,
                s.machine_ids,
                s.baseline_year,
                s.baseline_start_date,
                s.baseline_end_date,
                s.regression_coefficients,
                s.intercept,
                s.feature_columns,
                s.r_squared,
                s.rmse,
                s.mae,
                s.trained_at,
                s.trained_by,
                s.is_active,
                s.created_at,
                s.updated_at,
                es.name as energy_source_name,
                array_length(s.machine_ids, 1) as machine_count,
                (
                    SELECT report_period 
                    FROM seu_energy_performance 
                    WHERE seu_id = s.id 
                    ORDER BY period_start DESC 
                    LIMIT 1
                ) as last_report_period
            FROM seus s
            JOIN energy_sources es ON s.energy_source_id = es.id
            WHERE 1=1
        """
        
        params = []
        param_idx = 1
        
        if energy_source:
            query += f" AND es.name = ${param_idx}"
            params.append(energy_source)
            param_idx += 1
        
        if is_active is not None:
            query += f" AND s.is_active = ${param_idx}"
            params.append(is_active)
            param_idx += 1
        
        if has_baseline is not None:
            if has_baseline:
                query += " AND s.baseline_year IS NOT NULL"
            else:
                query += " AND s.baseline_year IS NULL"
        
        query += " ORDER BY s.name"
        
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        
        seus = []
        for row in rows:
            row_dict = dict(row)
            # Remove conflicting keys before creating model
            machine_count = row_dict.pop('machine_count', 0) or 0
            has_baseline = row_dict['baseline_year'] is not None
            last_report_period = row_dict.pop('last_report_period', None)
            energy_source_name = row_dict.pop('energy_source_name', '')
            
            seu = SEUWithMeta(
                **row_dict,
                machine_count=machine_count,
                energy_source_name=energy_source_name,
                has_baseline=has_baseline,
                last_report_period=last_report_period
            )
            seus.append(seu)
        
        return SEUListResponse(
            success=True,
            data=seus,
            total_count=len(seus),
            timestamp=datetime.utcnow()
        )
    
    except Exception as e:
        logger.error(f"[SEU-API] List SEUs failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/energy-sources", response_model=List[EnergySource], tags=["SEU Management"])
async def list_energy_sources():
    """
    List all available energy source types.
    
    **Returns:**
    - List of energy sources (electricity, gas, compressed air, steam)
    """
    try:
        query = """
            SELECT id, name, unit, cost_per_unit, carbon_factor, description, is_active
            FROM energy_sources
            WHERE is_active = true
            ORDER BY name
        """
        
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(query)
        
        return [EnergySource(**dict(row)) for row in rows]
    
    except Exception as e:
        logger.error(f"[SEU-API] List energy sources failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# BASELINE TRAINING ENDPOINTS
# ============================================================================

@router.post("/baseline/seu/train", response_model=TrainBaselineResponse, tags=["Baseline Training"])
async def train_seu_baseline(request: TrainBaselineRequest):
    """
    Train annual baseline regression for SEU (ISO 50001 compliance).
    
    **Different from `/baseline/train` (real-time monitoring):**
    - Trains on full year (365 days) of data
    - Uses daily aggregates (not hourly)
    - Purpose: Compliance reporting (not anomaly detection)
    
    **Requirements:**
    - Minimum 30 days of data (ideally 365 for annual baseline)
    - Features: production_count, temp_c, operating_hours, etc.
    
    **Example Request:**
    ```json
    {
        "seu_id": "uuid",
        "baseline_year": 2024,
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "features": ["total_production_count", "avg_temp_c"]
    }
    ```
    
    **Returns:**
    - Regression formula
    - R², RMSE, MAE metrics
    - Coefficients for each feature
    """
    try:
        logger.info(f"[SEU-API] Training baseline for SEU {request.seu_id}")
        
        result = await seu_baseline_service.train_baseline(request)
        
        logger.info(
            f"[SEU-API] Baseline trained successfully: "
            f"R²={result.r_squared}, RMSE={result.rmse}"
        )
        
        return result
    
    except ValueError as e:
        logger.warning(f"[SEU-API] Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[SEU-API] Train baseline failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PERFORMANCE REPORTING ENDPOINTS
# ============================================================================

@router.post("/reports/seu-performance", response_model=PerformanceReport, tags=["EnPI Reporting"])
async def generate_performance_report(request: PerformanceReportRequest):
    """
    Generate SEU energy performance report (actual vs baseline).
    
    **ISO 50001 EnPI Reporting:**
    - Compares actual consumption to baseline expectation
    - Calculates deviation percentage
    - Determines compliance status (green/yellow/red)
    
    **Example Request:**
    ```json
    {
        "seu_id": "uuid",
        "report_year": 2025,
        "baseline_year": 2024,
        "period": "Q1"
    }
    ```
    
    **Period Options:**
    - `Q1`, `Q2`, `Q3`, `Q4`: Quarterly reports (with monthly breakdown)
    - `annual`: Full year report
    
    **Compliance Thresholds:**
    - ±0-3%: Compliant (green ✅)
    - ±3-5%: Warning (yellow ⚠️)
    - >±5%: Critical (red 🔴)
    
    **Returns:**
    - Actual vs expected consumption
    - Deviation percentage
    - Compliance status
    - Monthly breakdown (for quarterly reports)
    """
    try:
        logger.info(
            f"[SEU-API] Generating report for SEU {request.seu_id}: "
            f"{request.report_year}-{request.period}"
        )
        
        report = await enpi_calculator.generate_performance_report(request)
        
        logger.info(
            f"[SEU-API] Report generated: Deviation={report.deviation_percent}%, "
            f"Status={report.compliance_status}"
        )
        
        return report
    
    except ValueError as e:
        logger.warning(f"[SEU-API] Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[SEU-API] Generate report failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reports/generate-all-monthly", tags=["EnPI Reporting"])
async def generate_all_monthly_reports(
    year: int = Query(..., ge=2020, le=2100, description="Year to generate reports for"),
    baseline_year: int = Query(..., ge=2020, le=2100, description="Baseline year"),
    months: List[int] = Query(default=list(range(1, 11)), description="Months to generate (1-12)")
):
    """
    Generate monthly reports for ALL SEUs across multiple months.
    
    **Batch Report Generation:**
    - Generates reports for all 7 electricity SEUs
    - Across specified months (default: Jan-Oct, months 1-10)
    - Stores in seu_energy_performance table
    - Returns summary of generated reports
    
    **Example:**
    ```
    POST /api/v1/reports/generate-all-monthly?year=2025&baseline_year=2024&months=1&months=2&months=3
    ```
    
    **Use Case:**
    - Mr. Umut's requirement: "Compare 2024 baseline vs 2025 actual for all SEUs"
    - ISO 50001 monthly tracking
    - CUSUM trend analysis
    
    **Returns:**
    - Total reports generated
    - Success/failure count
    - List of report summaries
    """
    try:
        logger.info(
            f"[SEU-API-BATCH] Generating monthly reports: "
            f"Year={year}, Baseline={baseline_year}, Months={months}"
        )
        
        # Get all SEUs
        seus_query = "SELECT id, name FROM seus ORDER BY name"
        async with db.pool.acquire() as conn:
            seus = await conn.fetch(seus_query)
        
        if not seus:
            raise ValueError("No SEUs found in database")
        
        results = {
            "year": year,
            "baseline_year": baseline_year,
            "months": months,
            "total_seus": len(seus),
            "total_reports_requested": len(seus) * len(months),
            "reports_generated": 0,
            "reports_failed": 0,
            "reports": []
        }
        
        # Generate report for each SEU × each month
        for seu in seus:
            for month in months:
                try:
                    period = f"{year}-{month:02d}"  # Format as YYYY-MM
                    
                    request = PerformanceReportRequest(
                        seu_id=seu['id'],
                        report_year=year,
                        baseline_year=baseline_year,
                        period=period
                    )
                    
                    report = await enpi_calculator.generate_performance_report(request)
                    
                    results["reports_generated"] += 1
                    results["reports"].append({
                        "seu_id": str(seu['id']),
                        "seu_name": seu['name'],
                        "period": period,
                        "actual_consumption": report.actual_consumption,
                        "expected_consumption": report.expected_consumption,
                        "deviation_percent": report.deviation_percent,
                        "cusum_deviation": report.cusum_deviation,
                        "compliance_status": report.compliance_status.value
                    })
                    
                    logger.info(
                        f"[SEU-API-BATCH] Generated: {seu['name']} {period} - "
                        f"Deviation={report.deviation_percent:.2f}%, CUSUM={report.cusum_deviation:.2f}%"
                    )
                    
                except Exception as e:
                    results["reports_failed"] += 1
                    logger.error(
                        f"[SEU-API-BATCH] Failed: {seu['name']} {period} - {e}",
                        exc_info=True
                    )
                    results["reports"].append({
                        "seu_id": str(seu['id']),
                        "seu_name": seu['name'],
                        "period": f"{year}-{month:02d}",
                        "error": str(e)
                    })
        
        logger.info(
            f"[SEU-API-BATCH] Complete: {results['reports_generated']} generated, "
            f"{results['reports_failed']} failed"
        )
        
        return results
    
    except Exception as e:
        logger.error(f"[SEU-API-BATCH] Batch generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/enpi", response_model=EnPITrendResponse, tags=["EnPI Reporting"])
async def get_enpi_trend(
    seu_id: UUID = Query(..., description="SEU identifier"),
    start_year: int = Query(..., ge=2020, le=2100, description="Start year for trend"),
    end_year: int = Query(..., ge=2020, le=2100, description="End year for trend")
):
    """
    Get EnPI (Energy Performance Indicator) trend for multiple years.
    
    **Purpose:**
    - Track energy performance improvement/degradation over time
    - Compare multiple years against baseline
    - Identify trends for management review
    
    **EnPI Index Calculation:**
    - Baseline year = 100
    - Other years: (actual / baseline_avg) × 100
    - Higher index = worse performance (more energy consumed)
    
    **Example Response:**
    ```json
    {
        "success": true,
        "seu_id": "uuid",
        "seu_name": "Compressor Group",
        "baseline_year": 2024,
        "data_points": [
            {"year": 2024, "quarter": "Q1", "enpi_index": 100, "deviation_percent": 0},
            {"year": 2025, "quarter": "Q1", "enpi_index": 105, "deviation_percent": 5.5}
        ]
    }
    ```
    
    **Returns:**
    - List of EnPI data points (quarterly or annual)
    - Deviation percentages
    - Actual and expected consumption values
    """
    try:
        logger.info(f"[SEU-API] Fetching EnPI trend for SEU {seu_id}: {start_year}-{end_year}")
        
        if end_year < start_year:
            raise HTTPException(
                status_code=400,
                detail="end_year must be >= start_year"
            )
        
        trend = await enpi_calculator.get_enpi_trend(seu_id, start_year, end_year)
        
        logger.info(f"[SEU-API] EnPI trend retrieved: {len(trend.data_points)} data points")
        
        return trend
    
    except ValueError as e:
        logger.warning(f"[SEU-API] Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[SEU-API] Get EnPI trend failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
