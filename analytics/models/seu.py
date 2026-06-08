"""
EnMS Analytics Service - SEU Models
====================================
Pydantic models for ISO 50001 SEU (Significant Energy User) management.

Author: EnMS Team
Phase: 3 - Analytics & ML (ISO 50001 Extension)
"""

from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime, date
from uuid import UUID
from enum import Enum


class ComplianceStatus(str, Enum):
    """ISO 50001 compliance status levels."""
    COMPLIANT = "compliant"      # ±0-3% deviation (green)
    WARNING = "warning"           # ±3-5% deviation (yellow)
    CRITICAL = "critical"         # >±5% deviation (red)


class EnergySource(BaseModel):
    """Energy source type (electricity, gas, etc.)."""
    id: UUID
    name: str
    unit: str
    cost_per_unit: Optional[float] = None
    carbon_factor: Optional[float] = None
    description: Optional[str] = None
    is_active: bool = True


class SEUBase(BaseModel):
    """Base model for SEU (Significant Energy User)."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    energy_source_id: UUID
    machine_ids: List[UUID] = Field(..., min_items=1)
    
    @validator('machine_ids')
    def validate_machine_ids(cls, v):
        """Ensure machine_ids list is not empty."""
        if not v or len(v) == 0:
            raise ValueError("At least one machine_id is required")
        return v


class SEUCreate(SEUBase):
    """Request model for creating a new SEU."""
    pass


class SEU(SEUBase):
    """Full SEU model with baseline data."""
    id: UUID
    baseline_year: Optional[int] = None
    baseline_start_date: Optional[date] = None
    baseline_end_date: Optional[date] = None
    regression_coefficients: Optional[Dict[str, float]] = None
    intercept: Optional[float] = None
    feature_columns: Optional[List[str]] = None
    r_squared: Optional[float] = None
    rmse: Optional[float] = None
    mae: Optional[float] = None
    trained_at: Optional[datetime] = None
    trained_by: Optional[str] = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True


class SEUWithMeta(SEU):
    """SEU with additional metadata (machine count, last report)."""
    machine_count: int
    energy_source_name: str
    has_baseline: bool
    last_report_period: Optional[str] = None


class TrainBaselineRequest(BaseModel):
    """Request model for training SEU baseline."""
    seu_id: UUID
    baseline_year: int = Field(..., ge=2020, le=2100)
    start_date: date
    end_date: date
    features: List[str] = Field(
        default=["production_count", "outdoor_temp_c", "is_weekend"],
        min_items=1
    )
    
    @validator('end_date')
    def validate_date_range(cls, v, values):
        """Ensure end_date is after start_date."""
        if 'start_date' in values and v <= values['start_date']:
            raise ValueError("end_date must be after start_date")
        return v
    
    @validator('baseline_year')
    def validate_baseline_year(cls, v, values):
        """Ensure baseline_year matches date range."""
        if 'start_date' in values and values['start_date'].year != v:
            raise ValueError("baseline_year must match start_date year")
        return v


class TrainBaselineResponse(BaseModel):
    """Response model for baseline training."""
    success: bool
    seu_id: UUID
    seu_name: str
    baseline_year: int
    training_period: str
    samples_count: int
    r_squared: float
    rmse: float
    mae: float
    coefficients: Dict[str, float]
    intercept: float
    formula: str
    trained_at: datetime


class PerformanceReportRequest(BaseModel):
    """Request model for generating SEU performance report."""
    seu_id: UUID
    report_year: int = Field(..., ge=2020, le=2100)
    baseline_year: int = Field(..., ge=2020, le=2100)
    period: str = Field(..., description="Period: Q1-Q4, annual, month number (1-12), or 'YYYY-MM' format (e.g., '2025-01')")
    
    @validator('report_year')
    def validate_report_year(cls, v, values):
        """Ensure report_year is after or equal to baseline_year."""
        if 'baseline_year' in values and v < values['baseline_year']:
            raise ValueError("report_year must be >= baseline_year")
        return v
    
    @validator('period')
    def validate_period(cls, v):
        """Validate period format."""
        # Check if it's a quarter
        if v in ['Q1', 'Q2', 'Q3', 'Q4', 'annual']:
            return v
        
        # Check if it's 'YYYY-MM' format
        if '-' in v:
            parts = v.split('-')
            if len(parts) == 2:
                try:
                    year = int(parts[0])
                    month = int(parts[1])
                    if 2020 <= year <= 2100 and 1 <= month <= 12:
                        return v
                except ValueError:
                    pass
        
        # Check if it's a month number (1-12)
        try:
            month = int(v)
            if 1 <= month <= 12:
                return v
        except ValueError:
            pass
        
        raise ValueError(
            "period must be Q1-Q4, annual, month number (1-12), "
            "or 'YYYY-MM' format (e.g., '2025-01')"
        )


class MonthlyBreakdown(BaseModel):
    """Monthly performance breakdown."""
    month: str
    actual: float
    expected: float
    deviation_kwh: float
    deviation_percent: float


class PerformanceReport(BaseModel):
    """SEU energy performance report."""
    seu_id: UUID
    seu_name: str
    energy_source: str
    report_period: str
    period_start: date
    period_end: date
    baseline_year: int
    actual_consumption: float
    expected_consumption: float
    deviation_kwh: float
    deviation_percent: float
    cusum_deviation: Optional[float] = None  # Cumulative sum of deviation percentages
    compliance_status: ComplianceStatus
    monthly_breakdown: Optional[List[MonthlyBreakdown]] = None
    notes: Optional[str] = None
    generated_at: datetime


class EnPIDataPoint(BaseModel):
    """Single EnPI trend data point."""
    year: int
    quarter: Optional[str] = None
    enpi_index: float
    deviation_percent: float
    actual_consumption: float
    expected_consumption: float


class EnPITrendResponse(BaseModel):
    """EnPI trend data for multiple periods."""
    success: bool
    seu_id: UUID
    seu_name: str
    baseline_year: int
    data_points: List[EnPIDataPoint]
    timestamp: datetime


class SEUListResponse(BaseModel):
    """Response model for listing SEUs."""
    success: bool
    data: List[SEUWithMeta]
    total_count: int
    timestamp: datetime


class ErrorResponse(BaseModel):
    """Standard error response."""
    success: bool = False
    error: str
    details: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
