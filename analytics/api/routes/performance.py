"""
Performance Analysis API Routes

Provides endpoints for Energy Performance Engine:
- Complete SEU performance analysis (actual vs baseline)
- Improvement opportunity detection
- Action plan generation

Author: EnMS v3 Team
Created: November 6, 2025 (Phase 2, Milestone 2.2)
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import List, Optional
import logging

from services.energy_performance_engine import (
    get_performance_engine,
    PerformanceAnalysis,
    ImprovementOpportunity,
    ActionPlan,
    ISO50001Status,
    ImplementationEffort,
    Priority
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/performance", tags=["Performance Analysis"])


# ============================================================================
# Request/Response Models
# ============================================================================

class AnalyzeRequest(BaseModel):
    """Request model for performance analysis"""
    seu_name: str = Field(..., description="SEU name (e.g., 'Compressor-1')")
    energy_source: str = Field(..., description="Energy source (electricity, natural_gas, steam, compressed_air)")
    analysis_date: date = Field(..., description="Date to analyze (YYYY-MM-DD)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "seu_name": "Compressor-1",
                "energy_source": "electricity",
                "analysis_date": "2025-11-05"
            }
        }


class RootCauseResponse(BaseModel):
    """Root cause analysis response"""
    primary_factor: str
    impact_description: str
    contributing_factors: List[str]
    confidence: float


class RecommendationResponse(BaseModel):
    """Recommendation response"""
    action: str
    type: str
    potential_savings_kwh: float
    potential_savings_usd: float
    implementation_effort: str
    priority: str
    expected_roi_days: int
    detailed_steps: Optional[List[str]] = None


class AnalyzeResponse(BaseModel):
    """Complete performance analysis response"""
    seu_name: str
    energy_source: str
    date: date
    actual_energy_kwh: float
    baseline_energy_kwh: float
    deviation_kwh: float
    deviation_percent: float
    deviation_cost_usd: float
    efficiency_score: float
    root_cause_analysis: RootCauseResponse
    recommendations: List[RecommendationResponse]
    iso50001_status: str
    voice_summary: str
    timestamp: datetime


class OpportunityResponse(BaseModel):
    """Improvement opportunity response"""
    rank: int
    seu_name: str
    issue_type: str
    description: str
    potential_savings_kwh: float
    potential_savings_usd: float
    effort: str
    roi_days: int
    recommended_action: str
    detailed_analysis: Optional[str] = None


class OpportunitiesResponse(BaseModel):
    """List of improvement opportunities"""
    factory_id: str
    period: str
    total_opportunities: int
    total_potential_savings_kwh: float
    total_potential_savings_usd: float
    opportunities: List[OpportunityResponse]
    timestamp: datetime


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_seu_performance(request: AnalyzeRequest):
    """
    **Analyze SEU Performance (Complete Analysis)**
    
    Performs comprehensive energy performance analysis:
    1. Compares actual vs baseline energy consumption
    2. Identifies root causes of deviation
    3. Generates actionable recommendations with ROI
    4. Determines ISO 50001 compliance status
    5. Creates voice-friendly summary for OVOS
    
    **Use Cases:**
    - "How did Compressor-1 perform yesterday?"
    - "Analyze HVAC energy usage for today"
    - "Why is the boiler using more energy?"
    
    **Returns:**
    - Complete performance analysis with:
        - Actual vs baseline comparison
        - Deviation analysis (%, cost)
        - Root cause identification
        - Prioritized recommendations
        - ISO 50001 status
        - Voice summary for TTS
    
    **Example Response:**
    ```json
    {
      "seu_name": "Compressor-1",
      "date": "2025-11-05",
      "actual_energy_kwh": 1200.5,
      "baseline_energy_kwh": 950.0,
      "deviation_percent": 26.4,
      "deviation_cost_usd": 37.58,
      "efficiency_score": 0.79,
      "root_cause_analysis": {
        "primary_factor": "increased_load",
        "impact_description": "Energy consumption 26.4% above baseline",
        "confidence": 0.7
      },
      "recommendations": [
        {
          "action": "Investigate equipment efficiency",
          "type": "maintenance",
          "potential_savings_kwh": 75.2,
          "potential_savings_usd": 11.28,
          "priority": "high",
          "expected_roi_days": 30
        }
      ],
      "iso50001_status": "requires_attention",
      "voice_summary": "Compressor-1 used 26% more energy..."
    }
    ```
    """
    logger.info(f"[API] Performance analysis request: {request.seu_name} ({request.energy_source}) on {request.analysis_date}")
    
    try:
        engine = get_performance_engine()
        analysis = await engine.analyze_seu_performance(
            seu_name=request.seu_name,
            energy_source=request.energy_source,
            analysis_date=request.analysis_date
        )
        
        # Convert to response model
        response = AnalyzeResponse(
            seu_name=analysis.seu_name,
            energy_source=analysis.energy_source,
            date=analysis.date,
            actual_energy_kwh=analysis.actual_energy_kwh,
            baseline_energy_kwh=analysis.baseline_energy_kwh,
            deviation_kwh=analysis.deviation_kwh,
            deviation_percent=analysis.deviation_percent,
            deviation_cost_usd=analysis.deviation_cost_usd,
            efficiency_score=analysis.efficiency_score,
            root_cause_analysis=RootCauseResponse(
                primary_factor=analysis.root_cause_analysis.primary_factor,
                impact_description=analysis.root_cause_analysis.impact_description,
                contributing_factors=analysis.root_cause_analysis.contributing_factors,
                confidence=analysis.root_cause_analysis.confidence
            ),
            recommendations=[
                RecommendationResponse(
                    action=rec.action,
                    type=rec.type,
                    potential_savings_kwh=rec.potential_savings_kwh,
                    potential_savings_usd=rec.potential_savings_usd,
                    implementation_effort=rec.implementation_effort.value,
                    priority=rec.priority.value,
                    expected_roi_days=rec.expected_roi_days,
                    detailed_steps=rec.detailed_steps
                )
                for rec in analysis.recommendations
            ],
            iso50001_status=analysis.iso50001_status.value,
            voice_summary=analysis.voice_summary,
            timestamp=analysis.timestamp
        )
        
        logger.info(f"[API] Analysis complete: {analysis.deviation_percent:+.1f}% deviation, {len(analysis.recommendations)} recommendations")
        return response
        
    except ValueError as e:
        logger.error(f"[API] Validation error: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"[API] Analysis failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Performance analysis failed: {str(e)}"
        )


@router.get("/opportunities", response_model=OpportunitiesResponse)
async def get_improvement_opportunities(
    factory_id: str = Query(..., description="Factory UUID"),
    period: str = Query("month", description="Analysis period (week, month, quarter)")
):
    """
    **Get Improvement Opportunities (Proactive Analysis)**
    
    Identifies energy optimization opportunities across factory:
    - Inefficient scheduling patterns
    - Excessive idle time
    - Baseline drift (degradation)
    - Recurring anomaly patterns
    - Peak demand issues
    - Load balancing opportunities
    
    **Use Cases:**
    - "What energy improvements can we make?"
    - "Show me optimization opportunities"
    - "Where can we save energy this month?"
    
    **Returns:**
    - Ranked list of opportunities (highest savings first)
    - Potential savings (kWh, USD)
    - Implementation effort (low, medium, high)
    - ROI calculation
    - Recommended actions
    
    **Status:** ✅ OPERATIONAL (Milestone 2.2)
    """
    logger.info(f"[API] Improvement opportunities request: factory={factory_id}, period={period}")
    
    try:
        # Validate period
        valid_periods = ["week", "month", "quarter"]
        if period not in valid_periods:
            raise ValueError(f"Invalid period: {period}. Valid options: {valid_periods}")
        
        # Get opportunities from Performance Engine
        engine = get_performance_engine()
        opportunities = await engine.get_improvement_opportunities(factory_id, period)
        
        # Calculate totals
        total_savings_kwh = sum(opp.potential_savings_kwh for opp in opportunities)
        total_savings_usd = sum(opp.potential_savings_usd for opp in opportunities)
        
        # Convert to response model
        response = OpportunitiesResponse(
            factory_id=factory_id,
            period=period,
            total_opportunities=len(opportunities),
            total_potential_savings_kwh=total_savings_kwh,
            total_potential_savings_usd=total_savings_usd,
            opportunities=[
                OpportunityResponse(
                    rank=opp.rank,
                    seu_name=opp.seu_name,
                    issue_type=opp.issue_type.value,
                    description=opp.description,
                    potential_savings_kwh=opp.potential_savings_kwh,
                    potential_savings_usd=opp.potential_savings_usd,
                    effort=opp.effort.value,
                    roi_days=opp.roi_days,
                    recommended_action=opp.recommended_action,
                    detailed_analysis=opp.detailed_analysis
                )
                for opp in opportunities
            ],
            timestamp=datetime.utcnow().isoformat()
        )
        
        logger.info(
            f"[API] Found {len(opportunities)} opportunities "
            f"(total savings: {total_savings_kwh:.1f} kWh, ${total_savings_usd:.2f})"
        )
        return response
        
    except ValueError as e:
        logger.error(f"[API] Validation error: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"[API] Failed to get opportunities: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get improvement opportunities: {str(e)}"
        )


@router.post("/action-plan")
async def generate_action_plan(
    seu_name: str = Query(..., description="SEU name"),
    issue_type: str = Query(..., description="Issue type (from ImprovementType enum)")
):
    """
    **Generate Action Plan (ISO 50001 Compliance)**
    
    Creates structured action plan for energy issue:
    - Problem statement
    - Root causes
    - Prioritized actions
    - Expected outcomes (energy, cost, carbon)
    - Monitoring plan
    - Target completion date
    
    **Use Cases:**
    - "Create action plan for HVAC efficiency"
    - "Generate improvement plan for compressor"
    - "What steps to fix this energy issue?"
    
    **Valid Issue Types:**
    - inefficient_scheduling
    - excessive_idle
    - suboptimal_setpoints
    - equipment_degradation
    - process_inefficiency
    - external_factors
    
    **Status:** ✅ OPERATIONAL (Milestone 2.2)
    """
    logger.info(f"[API] Action plan request: {seu_name}, issue={issue_type}")
    
    try:
        # Generate action plan
        engine = get_performance_engine()
        action_plan = await engine.generate_action_plan(seu_name, issue_type)
        
        # Convert to response dict
        response = {
            "id": action_plan.id,
            "seu_name": action_plan.seu_name,
            "problem_statement": action_plan.problem_statement,
            "root_causes": action_plan.root_causes,
            "actions": action_plan.actions,
            "expected_outcomes": action_plan.expected_outcomes,
            "monitoring_plan": action_plan.monitoring_plan,
            "target_date": action_plan.target_date.isoformat(),
            "status": action_plan.status,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info(f"[API] Generated action plan {action_plan.id} with {len(action_plan.actions)} actions")
        return response
        
    except ValueError as e:
        logger.error(f"[API] Validation error: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"[API] Failed to generate action plan: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate action plan: {str(e)}"
        )


@router.get("/health")
async def performance_engine_health():
    """
    **Performance Engine Health Check**
    
    Checks if Performance Engine is operational.
    """
    try:
        engine = get_performance_engine()
        return {
            "status": "healthy",
            "service": "Energy Performance Engine",
            "version": "1.0.0",
            "features": {
                "performance_analysis": "operational",
                "improvement_opportunities": "coming_soon",
                "action_plans": "coming_soon"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"[API] Health check failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=503, detail="Performance Engine unavailable")
