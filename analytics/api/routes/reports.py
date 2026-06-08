"""
Reports API Router
==================
Endpoints for generating and retrieving reports.
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from pathlib import Path
import logging
import uuid

from services.report_service import ReportService
from reports.monthly_enpi_report import MonthlyEnPIReport
from reports.chart_generator import ReportChartGenerator

# V2 Report imports
from reports_v2.services.report_service import ReportGenerationService
from database import db

logger = logging.getLogger(__name__)

router = APIRouter()
report_service = ReportService()
chart_generator = ReportChartGenerator()


@router.get("/types")
async def get_report_types():
    """
    Get available report types.
    
    Returns:
        List of report type metadata
    """
    return {
        "success": True,
        "data": [
            {
                "type": "monthly_enpi",
                "name": "Monthly Energy Performance Report",
                "description": "Comprehensive monthly report with EnPIs, machine consumption, and anomalies",
                "format": "PDF",
                "parameters": {
                    "year": "Required - Report year (integer)",
                    "month": "Required - Report month 1-12 (integer)",
                    "factory_id": "Optional - Filter by factory ID (integer)"
                }
            }
        ],
        "timestamp": datetime.utcnow().isoformat()
    }


@router.post("/generate")
async def generate_report(
    report_type: str = Query(..., description="Type of report to generate"),
    year: int = Query(..., description="Report year"),
    month: int = Query(..., ge=1, le=12, description="Report month (1-12)"),
    factory_id: Optional[int] = Query(None, description="Optional factory filter")
):
    """
    Generate a report and return PDF.
    
    Args:
        report_type: Type of report (currently only 'monthly_enpi')
        year: Year for the report
        month: Month for the report (1-12)
        factory_id: Optional factory filter
    
    Returns:
        PDF file stream
    """
    try:
        if report_type != "monthly_enpi":
            raise HTTPException(status_code=400, detail=f"Unsupported report type: {report_type}")
        
        logger.info(f"Generating {report_type} report for {year}-{month:02d}, factory={factory_id}")
        
        # Fetch report data
        data = await report_service.generate_monthly_enpi_data(year, month, factory_id)
        
        # Generate charts
        if data.get('machines'):
            machine_chart = chart_generator.generate_machine_consumption_chart(data['machines'])
            data['machine_chart'] = machine_chart
        
        if data.get('daily_data'):
            daily_chart = chart_generator.generate_daily_trend_chart(data['daily_data'])
            data['daily_trend_chart'] = daily_chart
        
        # Generate PDF
        report = MonthlyEnPIReport(data)
        pdf_buffer = report.generate()
        
        # Cleanup
        chart_generator.cleanup()
        
        # Return PDF
        headers = {
            'Content-Disposition': f'attachment; filename="{report.filename}"'
        }
        
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers=headers
        )
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating report: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")


@router.get("/preview")
async def preview_report_data(
    report_type: str = Query(..., description="Type of report"),
    year: int = Query(..., description="Report year"),
    month: int = Query(..., ge=1, le=12, description="Report month (1-12)"),
    factory_id: Optional[int] = Query(None, description="Optional factory filter")
):
    """
    Get report data as JSON (preview without generating PDF).
    
    Args:
        report_type: Type of report
        year: Year for the report
        month: Month for the report (1-12)
        factory_id: Optional factory filter
    
    Returns:
        JSON data that would be used in the report
    """
    try:
        if report_type != "monthly_enpi":
            raise HTTPException(status_code=400, detail=f"Unsupported report type: {report_type}")
        
        logger.info(f"Previewing {report_type} data for {year}-{month:02d}, factory={factory_id}")
        
        # Fetch report data
        data = await report_service.generate_monthly_enpi_data(year, month, factory_id)
        
        # Remove chart buffers from response (not JSON serializable)
        data.pop('machine_chart', None)
        data.pop('daily_trend_chart', None)
        
        return {
            "success": True,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error previewing report: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to preview report: {str(e)}")


# ============================================================================
# V2 REPORT API (New SOTA Report System)
# ============================================================================

class ReportGenerationRequest(BaseModel):
    """Request model for V2 report generation."""
    factory_id: str = Field(..., description="Factory UUID")
    year: int = Field(..., ge=2020, le=2030, description="Report year")
    month: int = Field(..., ge=1, le=12, description="Report month (1-12)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "factory_id": "123e4567-e89b-12d3-a456-426614174000",
                "year": 2025,
                "month": 11
            }
        }


class ReportGenerationResponse(BaseModel):
    """Response model for V2 report generation."""
    success: bool
    message: str
    report_id: str
    download_url: Optional[str] = None
    file_size_kb: Optional[float] = None


@router.post(
    "/v2/generate",
    response_model=ReportGenerationResponse,
    summary="Generate Monthly Energy Report (V2 - SOTA)",
    description="Generate a complete PDF energy report using new world-class report system",
    tags=["Reports V2"]
)
async def generate_v2_report(
    request: ReportGenerationRequest,
    background_tasks: BackgroundTasks
):
    """
    Generate a comprehensive monthly energy report with the new SOTA system.
    
    This endpoint generates a complete PDF report including:
    - Professional cover page with hero chart
    - Executive dashboard with KPIs and sparklines
    - Energy consumption analysis with heatmaps
    - Machine performance profiles with detailed charts
    - Cost analysis with budget tracking
    - Carbon footprint analysis with reduction initiatives
    
    The report is generated synchronously and can be downloaded immediately.
    """
    try:
        logger.info(f"V2 Report generation requested: {request.factory_id}, {request.year}-{request.month:02d}")
        
        # Generate unique report ID
        report_id = str(uuid.uuid4())
        output_path = Path(f"/tmp/enms_report_v2_{report_id}.pdf")
        
        # Create report service
        service = ReportGenerationService(db)
        
        # Generate report
        result_path = await service.generate_monthly_report(
            factory_id=request.factory_id,
            year=request.year,
            month=request.month,
            output_path=output_path
        )
        
        # Get file size
        file_size_kb = result_path.stat().st_size / 1024
        
        # Construct download URL
        download_url = f"/api/v1/reports/v2/download/{report_id}"
        
        logger.info(f"✅ V2 Report generated successfully: {result_path} ({file_size_kb:.1f} KB)")
        
        return ReportGenerationResponse(
            success=True,
            message=f"Report generated successfully for {request.year}-{request.month:02d}",
            report_id=report_id,
            download_url=download_url,
            file_size_kb=round(file_size_kb, 2)
        )
        
    except ValueError as e:
        logger.error(f"Invalid request: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"V2 Report generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")


@router.get(
    "/v2/download/{report_id}",
    response_class=FileResponse,
    summary="Download Generated V2 Report",
    description="Download a previously generated PDF report (V2 system)",
    tags=["Reports V2"]
)
async def download_v2_report(report_id: str):
    """
    Download a generated PDF report by its ID.
    
    The report file must exist in /tmp/ directory.
    """
    try:
        file_path = Path(f"/tmp/enms_report_v2_{report_id}.pdf")
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Report not found")
        
        return FileResponse(
            path=str(file_path),
            media_type="application/pdf",
            filename=f"enms_energy_report_{report_id}.pdf"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"V2 Report download failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


@router.get(
    "/v2/status",
    summary="V2 Report API Status",
    description="Check if the V2 report generation API is operational",
    tags=["Reports V2"]
)
async def get_v2_status():
    """Get the status of the V2 report generation API."""
    return {
        "success": True,
        "service": "EnMS Report Generation API V2 (SOTA)",
        "version": "2.0.0",
        "status": "operational",
        "features": [
            "Professional cover pages with hero charts",
            "Executive dashboards with sparklines",
            "Energy analysis with heatmaps",
            "Machine performance profiles",
            "Cost and budget tracking",
            "Carbon footprint analysis",
            "Real-time data integration",
            "300 DPI print quality"
        ],
        "timestamp": datetime.utcnow().isoformat()
    }

