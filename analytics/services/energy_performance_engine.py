"""
Energy Performance Engine - Core Intelligence Layer

Orchestrates complete energy performance analysis by connecting:
- Baseline prediction service
- Anomaly detection service  
- KPI calculation service
- Root cause analysis
- Recommendation generation

This is the "brain" of EnMS v3 that provides actionable insights,
not just raw data.

Author: EnMS v3 Team
Created: November 6, 2025 (Phase 2, Milestone 2.1)
"""

from datetime import date, datetime, timedelta
from typing import List, Dict, Optional, Any
from enum import Enum
import logging
from dataclasses import dataclass

from database import db
from services.baseline_service import BaselineService
from services.anomaly_service import AnomalyService

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================

class ImprovementType(str, Enum):
    """Types of energy improvement opportunities"""
    INEFFICIENT_SCHEDULING = "inefficient_scheduling"
    EXCESSIVE_IDLE = "excessive_idle"
    BASELINE_DRIFT = "baseline_drift"
    SUBOPTIMAL_SETPOINTS = "suboptimal_setpoints"
    ANOMALY_PATTERN = "anomaly_pattern"
    PEAK_DEMAND = "peak_demand"
    LOAD_BALANCING = "load_balancing"


class ImplementationEffort(str, Enum):
    """Implementation effort levels"""
    LOW = "low"          # < 1 day, no cost
    MEDIUM = "medium"    # 1-5 days, < $1000
    HIGH = "high"        # > 5 days, > $1000


class Priority(str, Enum):
    """Recommendation priority"""
    CRITICAL = "critical"  # Immediate action required
    HIGH = "high"         # Address within week
    MEDIUM = "medium"     # Address within month
    LOW = "low"           # Nice to have


class ISO50001Status(str, Enum):
    """ISO 50001 compliance status"""
    EXCELLENT = "excellent"          # Performance better than baseline
    ON_TARGET = "on_target"          # Within ±5% of target
    REQUIRES_ATTENTION = "requires_attention"  # 5-15% over target
    NON_COMPLIANT = "non_compliant"  # >15% over target


@dataclass
class RootCauseAnalysis:
    """Root cause analysis results"""
    primary_factor: str
    impact_description: str
    contributing_factors: List[str]
    confidence: float  # 0-1


@dataclass
class Recommendation:
    """Actionable recommendation"""
    action: str
    type: str  # operational, maintenance, capital
    potential_savings_kwh: float
    potential_savings_usd: float
    implementation_effort: ImplementationEffort
    priority: Priority
    expected_roi_days: int
    detailed_steps: Optional[List[str]] = None


@dataclass
@dataclass
class PerformanceAnalysis:
    """Complete SEU performance analysis"""
    seu_name: str
    energy_source: str
    date: date
    actual_energy_kwh: float
    baseline_energy_kwh: float
    deviation_kwh: float
    deviation_percent: float
    deviation_cost_usd: float
    efficiency_score: float  # 0-1, 1 = perfect
    root_cause_analysis: RootCauseAnalysis
    recommendations: List[Recommendation]
    iso50001_status: ISO50001Status
    voice_summary: str
    timestamp: datetime


@dataclass
class ImprovementOpportunity:
    """Energy improvement opportunity"""
    rank: int
    seu_name: str
    issue_type: ImprovementType
    description: str
    potential_savings_kwh: float
    potential_savings_usd: float
    effort: ImplementationEffort
    roi_days: int
    recommended_action: str
    detailed_analysis: Optional[str] = None


@dataclass
class ActionPlan:
    """ISO 50001 action plan"""
    id: str
    seu_name: str
    problem_statement: str
    root_causes: List[str]
    actions: List[Dict[str, Any]]  # Prioritized actions
    expected_outcomes: Dict[str, float]  # energy_kwh, cost_usd, carbon_kg
    monitoring_plan: List[str]
    target_date: date
    status: str  # draft, approved, in_progress, completed


# ============================================================================
# Energy Performance Engine
# ============================================================================

class EnergyPerformanceEngine:
    """
    Core intelligence layer for EnMS v3.
    
    Provides:
    - Complete SEU performance analysis
    - Root cause identification
    - Actionable recommendations
    - Improvement opportunity detection
    - Action plan generation
    """
    
    def __init__(self):
        self.baseline_service = BaselineService()
        self.anomaly_service = AnomalyService()
        self.electricity_rate = 0.15  # USD per kWh (configurable)
        logger.info("[PERF-ENGINE] Energy Performance Engine initialized")
    
    # ========================================================================
    # Main Analysis Methods
    # ========================================================================
    
    async def analyze_seu_performance(
        self,
        seu_name: str,
        energy_source: str,
        analysis_date: date
    ) -> PerformanceAnalysis:
        """
        Complete performance analysis for a SEU on specific date.
        
        Workflow:
        1. Get actual energy consumption
        2. Get baseline prediction
        3. Calculate deviation
        4. Perform root cause analysis
        5. Generate recommendations
        6. Determine ISO 50001 status
        7. Create voice summary
        
        Args:
            seu_name: SEU name (e.g., "Compressor-1")
            energy_source: Energy source (electricity, natural_gas, etc.)
            analysis_date: Date to analyze
        
        Returns:
            Complete PerformanceAnalysis with insights and recommendations
        
        Raises:
            ValueError: If SEU not found or no data available
        """
        logger.info(f"[PERF-ENGINE] Analyzing {seu_name} ({energy_source}) for {analysis_date}")
        
        try:
            # Step 0: Check if analyzing incomplete day
            current_time = datetime.utcnow()
            is_incomplete_day = analysis_date == current_time.date()
            hours_elapsed = None
            
            if is_incomplete_day:
                start_of_day = datetime.combine(analysis_date, datetime.min.time())
                hours_elapsed = (current_time - start_of_day).total_seconds() / 3600
                
                # Require at least 2 hours of data for partial day analysis
                if hours_elapsed < 2:
                    raise ValueError(
                        f"Cannot analyze {analysis_date} - insufficient data "
                        f"({hours_elapsed:.1f}h). Please wait or analyze a previous day."
                    )
                
                logger.warning(
                    f"[PERF-ENGINE] Analyzing incomplete day {analysis_date} "
                    f"({hours_elapsed:.1f}h of 24h) - will project to full day"
                )
            
            # Step 1: Get actual energy consumption
            actual_kwh_raw = await self._get_actual_energy(seu_name, energy_source, analysis_date)
            
            # Project to 24h if incomplete day
            if is_incomplete_day:
                actual_kwh = (actual_kwh_raw / hours_elapsed) * 24
                logger.info(
                    f"[PERF-ENGINE] Projected {actual_kwh_raw:.2f} kWh ({hours_elapsed:.1f}h) "
                    f"to {actual_kwh:.2f} kWh (24h)"
                )
            else:
                actual_kwh = actual_kwh_raw
            
            # Step 2: Get baseline prediction
            baseline_kwh = await self._get_baseline_prediction(seu_name, energy_source, analysis_date)
            
            # Step 3: Calculate deviation
            deviation_kwh = actual_kwh - baseline_kwh
            deviation_percent = (deviation_kwh / baseline_kwh * 100) if baseline_kwh > 0 else 0
            deviation_cost = abs(deviation_kwh) * self.electricity_rate
            
            # Step 4: Calculate efficiency score (0-1, 1 = perfect)
            # Lower deviation from baseline = higher score
            # Penalize both over-consumption AND unusual under-consumption
            abs_deviation_percent = abs(deviation_percent)
            if abs_deviation_percent <= 5:
                efficiency_score = 1.0  # Within 5% = excellent
            elif abs_deviation_percent <= 15:
                efficiency_score = 0.8  # Within 15% = good
            elif abs_deviation_percent <= 30:
                efficiency_score = 0.6  # Within 30% = acceptable
            else:
                efficiency_score = 0.4  # Over 30% = poor
            
            # Step 5: Root cause analysis
            root_cause = await self._analyze_root_cause(
                seu_name, energy_source, analysis_date, actual_kwh, baseline_kwh
            )
            
            # Step 6: Generate recommendations
            recommendations = await self._generate_recommendations(
                seu_name, energy_source, deviation_kwh, deviation_percent, root_cause
            )
            
            # Step 7: Determine ISO 50001 status
            iso_status = self._determine_iso_status(deviation_percent)
            
            # Step 8: Create voice summary
            voice_summary = self._create_voice_summary(
                seu_name, actual_kwh, baseline_kwh, deviation_percent, 
                deviation_cost, root_cause
            )
            
            analysis = PerformanceAnalysis(
                seu_name=seu_name,
                energy_source=energy_source,
                date=analysis_date,
                actual_energy_kwh=actual_kwh,
                baseline_energy_kwh=baseline_kwh,
                deviation_kwh=deviation_kwh,
                deviation_percent=deviation_percent,
                deviation_cost_usd=deviation_cost,
                efficiency_score=efficiency_score,
                root_cause_analysis=root_cause,
                recommendations=recommendations,
                iso50001_status=iso_status,
                voice_summary=voice_summary,
                timestamp=datetime.utcnow()
            )
            
            logger.info(f"[PERF-ENGINE] Analysis complete: {deviation_percent:+.1f}% deviation")
            return analysis
            
        except Exception as e:
            logger.error(f"[PERF-ENGINE] Analysis failed: {str(e)}", exc_info=True)
            raise
    
    async def get_improvement_opportunities(
        self,
        factory_id: str,
        period: str = "month"
    ) -> List[ImprovementOpportunity]:
        """
        Proactive analysis: Find energy optimization opportunities.
        
        Scans all SEUs in factory for:
        - Inefficient scheduling patterns
        - Excessive idle time
        - Baseline drift (degradation)
        - Recurring anomaly patterns
        - Peak demand issues
        - Load balancing opportunities
        
        Args:
            factory_id: Factory UUID
            period: Analysis period (week, month, quarter)
        
        Returns:
            Ranked list of improvement opportunities (highest savings first)
        """
        logger.info(f"[PERF-ENGINE] Finding improvement opportunities for factory {factory_id}")
        
        opportunities = []
        
        # Determine date range based on period
        end_date = datetime.utcnow().date()
        if period == "week":
            start_date = end_date - timedelta(days=7)
        elif period == "quarter":
            start_date = end_date - timedelta(days=90)
        else:  # month (default)
            start_date = end_date - timedelta(days=30)
        
        # Get all SEUs in factory
        query_seus = """
            SELECT DISTINCT s.id, s.name
            FROM seus s
            JOIN machines m ON m.id = ANY(s.machine_ids)
            WHERE m.factory_id = $1 AND s.is_active = true
            ORDER BY s.name
        """
        
        async with db.pool.acquire() as conn:
            seus = await conn.fetch(query_seus, factory_id)
        
        if not seus:
            logger.warning(f"[PERF-ENGINE] No SEUs found for factory {factory_id}")
            return opportunities
        
        # Analyze each SEU for opportunities
        for seu_record in seus:
            seu_name = seu_record['name']
            
            # For MVP, analyze 'energy' type (electricity)
            # Future: Multi-energy support (gas, steam, etc.)
            energy_type = 'energy'
            
            try:
                # Pattern 1: Check for excessive idle time
                idle_opp = await self._check_excessive_idle(
                    seu_name, energy_type, start_date, end_date
                )
                if idle_opp:
                    opportunities.append(idle_opp)
                
                # Pattern 2: Check for inefficient scheduling
                schedule_opp = await self._check_inefficient_scheduling(
                    seu_name, energy_type, start_date, end_date
                )
                if schedule_opp:
                    opportunities.append(schedule_opp)
                
                # Pattern 3: Check for baseline drift (degradation)
                drift_opp = await self._check_baseline_drift(
                    seu_name, energy_type, start_date, end_date
                )
                if drift_opp:
                    opportunities.append(drift_opp)
                
            except Exception as e:
                logger.warning(
                    f"[PERF-ENGINE] Failed to analyze {seu_name} ({energy_type}): {e}"
                )
                continue
        
        # Rank by potential savings (highest first)
        opportunities.sort(key=lambda x: x.potential_savings_kwh, reverse=True)
        
        # Add rank numbers
        for i, opp in enumerate(opportunities, 1):
            opp.rank = i
        
        logger.info(
            f"[PERF-ENGINE] Found {len(opportunities)} improvement opportunities "
            f"(total savings: {sum(o.potential_savings_kwh for o in opportunities):.1f} kWh)"
        )
        
        return opportunities
    
    async def generate_action_plan(
        self,
        seu_name: str,
        issue_type: str
    ) -> ActionPlan:
        """
        Generate structured ISO 50001 action plan for energy issue.
        
        Args:
            seu_name: SEU name
            issue_type: Type of issue (from ImprovementType enum)
        
        Returns:
            Complete ActionPlan with problem statement, actions, outcomes
        """
        logger.info(f"[PERF-ENGINE] Generating action plan for {seu_name} ({issue_type})")
        
        # Validate issue type
        try:
            issue_enum = ImprovementType(issue_type)
        except ValueError:
            raise ValueError(
                f"Invalid issue_type: {issue_type}. "
                f"Valid types: {[t.value for t in ImprovementType]}"
            )
        
        # Generate plan ID
        plan_id = f"AP-{seu_name.replace(' ', '-')}-{issue_type}-{datetime.utcnow().strftime('%Y%m%d')}"
        
        # Get current performance data (last 30 days)
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=30)
        
        # Template-based action plans (MVP - rule-based)
        action_templates = {
            ImprovementType.EXCESSIVE_IDLE: {
                "problem_statement": f"{seu_name} experiences excessive idle time, consuming energy without productive output",
                "root_causes": [
                    "Equipment left running during non-production periods",
                    "No automatic shutdown timers configured",
                    "Manual operation without idle detection"
                ],
                "actions": [
                    {
                        "priority": 1,
                        "action": "Install and configure automatic idle detection",
                        "responsible": "Maintenance Team",
                        "timeline_days": 7,
                        "resources_needed": "PLC programming, sensors (if needed)"
                    },
                    {
                        "priority": 2,
                        "action": "Set auto-shutdown timer to 15 minutes of idle",
                        "responsible": "Operations Team",
                        "timeline_days": 3,
                        "resources_needed": "Control system access"
                    },
                    {
                        "priority": 3,
                        "action": "Train operators on manual shutdown procedures",
                        "responsible": "Training Coordinator",
                        "timeline_days": 14,
                        "resources_needed": "Training materials, 2 hours per shift"
                    }
                ],
                "expected_outcomes": {
                    "energy_kwh": 500,  # Estimated monthly savings
                    "cost_usd": 75,
                    "carbon_kg": 250
                },
                "monitoring_plan": [
                    "Track idle time percentage weekly",
                    "Monitor auto-shutdown events daily",
                    "Review energy consumption trend monthly",
                    "Operator feedback on usability"
                ]
            },
            ImprovementType.INEFFICIENT_SCHEDULING: {
                "problem_statement": f"{seu_name} operates during off-hours with unnecessary energy consumption",
                "root_causes": [
                    "No time-based control schedule configured",
                    "Equipment runs 24/7 regardless of production needs",
                    "Setpoints not optimized for off-hours"
                ],
                "actions": [
                    {
                        "priority": 1,
                        "action": "Implement time-based setback schedule (reduced capacity 8pm-6am)",
                        "responsible": "Controls Engineer",
                        "timeline_days": 5,
                        "resources_needed": "BMS/PLC programming"
                    },
                    {
                        "priority": 2,
                        "action": "Configure weekend shutdown or reduced operation",
                        "responsible": "Operations Manager",
                        "timeline_days": 7,
                        "resources_needed": "Production schedule coordination"
                    },
                    {
                        "priority": 3,
                        "action": "Install occupancy sensors for automatic control",
                        "responsible": "Facilities Team",
                        "timeline_days": 21,
                        "resources_needed": "$500 sensors, 8 hours installation"
                    }
                ],
                "expected_outcomes": {
                    "energy_kwh": 800,
                    "cost_usd": 120,
                    "carbon_kg": 400
                },
                "monitoring_plan": [
                    "Track off-hours energy consumption weekly",
                    "Verify schedule execution daily",
                    "Compare monthly totals to baseline",
                    "Review production impact (should be zero)"
                ]
            },
            ImprovementType.BASELINE_DRIFT: {
                "problem_statement": f"{seu_name} shows gradual increase in energy consumption indicating equipment degradation",
                "root_causes": [
                    "Wear and tear on mechanical components",
                    "Sensor calibration drift",
                    "Fouling or blockages reducing efficiency",
                    "Control system parameter drift"
                ],
                "actions": [
                    {
                        "priority": 1,
                        "action": "Schedule comprehensive maintenance inspection",
                        "responsible": "Maintenance Team",
                        "timeline_days": 7,
                        "resources_needed": "4 hours downtime, inspection tools"
                    },
                    {
                        "priority": 2,
                        "action": "Calibrate sensors and verify control loops",
                        "responsible": "Instrumentation Technician",
                        "timeline_days": 10,
                        "resources_needed": "Calibration equipment, 2 hours"
                    },
                    {
                        "priority": 3,
                        "action": "Replace worn components identified in inspection",
                        "responsible": "Maintenance Team",
                        "timeline_days": 21,
                        "resources_needed": "Parts budget $500-2000"
                    }
                ],
                "expected_outcomes": {
                    "energy_kwh": 600,
                    "cost_usd": 90,
                    "carbon_kg": 300
                },
                "monitoring_plan": [
                    "Monitor daily energy consumption trend",
                    "Track equipment efficiency weekly",
                    "Verify post-maintenance improvement",
                    "Schedule quarterly preventive maintenance"
                ]
            },
            ImprovementType.SUBOPTIMAL_SETPOINTS: {
                "problem_statement": f"{seu_name} operating setpoints not optimized for current conditions",
                "root_causes": [
                    "Setpoints based on design conditions, not actual needs",
                    "Seasonal adjustments not implemented",
                    "Control deadbands too wide"
                ],
                "actions": [
                    {
                        "priority": 1,
                        "action": "Review and optimize temperature/pressure setpoints",
                        "responsible": "Process Engineer",
                        "timeline_days": 5,
                        "resources_needed": "Process analysis, 4 hours"
                    },
                    {
                        "priority": 2,
                        "action": "Implement seasonal adjustment schedule",
                        "responsible": "Controls Engineer",
                        "timeline_days": 10,
                        "resources_needed": "BMS programming"
                    },
                    {
                        "priority": 3,
                        "action": "Tighten control deadbands to reduce cycling",
                        "responsible": "Controls Engineer",
                        "timeline_days": 7,
                        "resources_needed": "Control tuning, testing"
                    }
                ],
                "expected_outcomes": {
                    "energy_kwh": 400,
                    "cost_usd": 60,
                    "carbon_kg": 200
                },
                "monitoring_plan": [
                    "Monitor setpoint performance daily",
                    "Track energy vs production correlation",
                    "Review quarterly for optimization",
                    "Validate comfort/quality not impacted"
                ]
            }
        }
        
        # Get template or use generic
        template = action_templates.get(issue_enum, {
            "problem_statement": f"{seu_name} has identified energy efficiency opportunity: {issue_type}",
            "root_causes": ["Requires detailed analysis"],
            "actions": [
                {
                    "priority": 1,
                    "action": "Conduct detailed energy audit",
                    "responsible": "Energy Manager",
                    "timeline_days": 14,
                    "resources_needed": "Audit equipment, 8 hours"
                }
            ],
            "expected_outcomes": {"energy_kwh": 300, "cost_usd": 45, "carbon_kg": 150},
            "monitoring_plan": ["Track weekly energy consumption"]
        })
        
        # Create action plan
        action_plan = ActionPlan(
            id=plan_id,
            seu_name=seu_name,
            problem_statement=template["problem_statement"],
            root_causes=template["root_causes"],
            actions=template["actions"],
            expected_outcomes=template["expected_outcomes"],
            monitoring_plan=template["monitoring_plan"],
            target_date=end_date + timedelta(days=30),
            status="draft"
        )
        
        logger.info(
            f"[PERF-ENGINE] Generated action plan {plan_id} with "
            f"{len(action_plan.actions)} actions"
        )
        
        return action_plan
    
    # ========================================================================
    # Internal Helper Methods
    # ========================================================================
    
    async def _get_actual_energy(
        self,
        seu_name: str,
        energy_source: str,
        analysis_date: date
    ) -> float:
        """Get actual energy consumption for SEU on specific date."""
        
        start_time = datetime.combine(analysis_date, datetime.min.time())
        end_time = start_time + timedelta(days=1)
        
        # BUGFIX (Phase 4.1): Handle 'energy' as alias for 'electricity'
        # Node-RED flow maps all energy types to 'energy' for routing,
        # causing energy_type mismatch. Accept both for backward compatibility.
        if energy_source == 'electricity':
            energy_types = ['electricity', 'energy']
        else:
            energy_types = [energy_source]
        
        query = """
            SELECT COALESCE(SUM(energy_kwh), 0) as total_energy
            FROM energy_readings er
            JOIN machines m ON er.machine_id = m.id
            JOIN seus s ON m.id = ANY(s.machine_ids)
            WHERE s.name = $1
              AND er.energy_type = ANY($2::text[])
              AND er.time >= $3
              AND er.time < $4
        """
        
        async with db.pool.acquire() as conn:
            result = await conn.fetchrow(query, seu_name, energy_types, start_time, end_time)
            
        if result is None or result['total_energy'] == 0:
            raise ValueError(f"No data found for {seu_name} on {analysis_date}")
        
        return float(result['total_energy'])
    
    async def _get_baseline_prediction(
        self,
        seu_name: str,
        energy_source: str,
        analysis_date: date
    ) -> float:
        """Get baseline prediction for SEU on specific date."""
        
        # Use baseline service to get prediction
        # For MVP, use simple historical average
        # Later: Use trained ML models with features
        
        start_date = analysis_date - timedelta(days=30)
        end_date = analysis_date - timedelta(days=1)
        
        # BUGFIX (Phase 4.1): Handle 'energy' as alias for 'electricity'
        if energy_source == 'electricity':
            energy_types = ['electricity', 'energy']
        else:
            energy_types = [energy_source]
        
        query = """
            SELECT AVG(daily_energy) as avg_energy
            FROM (
                SELECT DATE(er.time) as date, SUM(er.energy_kwh) as daily_energy
                FROM energy_readings er
                JOIN machines m ON er.machine_id = m.id
                JOIN seus s ON m.id = ANY(s.machine_ids)
                WHERE s.name = $1
                  AND er.energy_type = ANY($2::text[])
                  AND DATE(er.time) >= $3
                  AND DATE(er.time) <= $4
                GROUP BY DATE(er.time)
            ) daily_data
        """
        
        async with db.pool.acquire() as conn:
            result = await conn.fetchrow(query, seu_name, energy_types, start_date, end_date)
        
        if result is None or result['avg_energy'] is None:
            raise ValueError(f"No baseline data available for {seu_name}")
        
        return float(result['avg_energy'])
    
    async def _analyze_root_cause(
        self,
        seu_name: str,
        energy_source: str,
        analysis_date: date,
        actual_kwh: float,
        baseline_kwh: float
    ) -> RootCauseAnalysis:
        """
        Perform root cause analysis for energy deviation.
        
        MVP: Simple heuristics based on available data
        Future: ML-based attribution analysis
        """
        
        deviation_percent = ((actual_kwh - baseline_kwh) / baseline_kwh * 100) if baseline_kwh > 0 else 0
        
        # Check if analyzing incomplete day (projected data)
        current_time = datetime.utcnow()
        is_incomplete_day = analysis_date == current_time.date()
        
        # Simple rule-based root cause (MVP)
        if abs(deviation_percent) < 5:
            primary_factor = "normal_variation"
            impact_description = "Energy consumption within expected range"
            contributing_factors = []
            confidence = 0.9
            
            if is_incomplete_day:
                impact_description += f" (projected from {current_time.hour}h of data)"
                confidence = 0.7  # Lower confidence for projections
                
        elif deviation_percent > 0:
            # Over consumption
            primary_factor = "increased_load"
            impact_description = f"Energy consumption {abs(deviation_percent):.1f}% above baseline"
            contributing_factors = [
                "Possible production increase",
                "Equipment degradation",
                "Inefficient operation"
            ]
            confidence = 0.7
            
            if is_incomplete_day:
                impact_description += f" (projected from {current_time.hour}h of data)"
                contributing_factors.insert(0, "⚠️ Projection based on partial day - may change")
                confidence = 0.6  # Lower confidence for projections
                
        else:
            # Under consumption
            primary_factor = "reduced_load"
            impact_description = f"Energy consumption {abs(deviation_percent):.1f}% below baseline"
            contributing_factors = [
                "Production decrease",
                "Equipment offline",
                "Process optimization"
            ]
            confidence = 0.7
            
            if is_incomplete_day:
                impact_description += f" (projected from {current_time.hour}h of data)"
                contributing_factors.insert(0, "⚠️ Projection based on partial day - may change")
                confidence = 0.6  # Lower confidence for projections
        
        return RootCauseAnalysis(
            primary_factor=primary_factor,
            impact_description=impact_description,
            contributing_factors=contributing_factors,
            confidence=confidence
        )
    
    async def _generate_recommendations(
        self,
        seu_name: str,
        energy_source: str,
        deviation_kwh: float,
        deviation_percent: float,
        root_cause: RootCauseAnalysis
    ) -> List[Recommendation]:
        """Generate actionable recommendations based on analysis."""
        
        recommendations = []
        
        # Rule-based recommendations (MVP)
        if abs(deviation_percent) < 5:
            # Performance is good, no recommendations
            pass
        
        elif deviation_percent > 15:
            # Significant overconsumption
            recommendations.append(Recommendation(
                action="Investigate equipment efficiency",
                type="maintenance",
                potential_savings_kwh=abs(deviation_kwh) * 0.3,
                potential_savings_usd=abs(deviation_kwh) * 0.3 * self.electricity_rate,
                implementation_effort=ImplementationEffort.MEDIUM,
                priority=Priority.HIGH,
                expected_roi_days=30,
                detailed_steps=[
                    "Schedule equipment inspection",
                    "Check for air leaks or wear",
                    "Review operating parameters"
                ]
            ))
            
            recommendations.append(Recommendation(
                action="Optimize operating schedule",
                type="operational",
                potential_savings_kwh=abs(deviation_kwh) * 0.2,
                potential_savings_usd=abs(deviation_kwh) * 0.2 * self.electricity_rate,
                implementation_effort=ImplementationEffort.LOW,
                priority=Priority.HIGH,
                expected_roi_days=7,
                detailed_steps=[
                    "Review production schedule",
                    "Identify off-peak operations",
                    "Implement load shifting"
                ]
            ))
        
        elif deviation_percent > 5:
            # Moderate overconsumption
            recommendations.append(Recommendation(
                action="Review operational parameters",
                type="operational",
                potential_savings_kwh=abs(deviation_kwh) * 0.5,
                potential_savings_usd=abs(deviation_kwh) * 0.5 * self.electricity_rate,
                implementation_effort=ImplementationEffort.LOW,
                priority=Priority.MEDIUM,
                expected_roi_days=14
            ))
        
        return recommendations
    
    def _determine_iso_status(self, deviation_percent: float) -> ISO50001Status:
        """Determine ISO 50001 compliance status based on deviation."""
        
        if deviation_percent < -5:
            return ISO50001Status.EXCELLENT
        elif deviation_percent <= 5:
            return ISO50001Status.ON_TARGET
        elif deviation_percent <= 15:
            return ISO50001Status.REQUIRES_ATTENTION
        else:
            return ISO50001Status.NON_COMPLIANT
    
    def _create_voice_summary(
        self,
        seu_name: str,
        actual_kwh: float,
        baseline_kwh: float,
        deviation_percent: float,
        deviation_cost: float,
        root_cause: RootCauseAnalysis
    ) -> str:
        """Create voice-friendly summary for TTS."""
        
        # Check if this is a projection
        current_time = datetime.utcnow()
        projection_note = ""
        if "projected from" in root_cause.impact_description:
            projection_note = f" This is a projection based on data through {current_time.hour} hours today."
        
        if abs(deviation_percent) < 5:
            return (
                f"{seu_name} is performing as expected. "
                f"Energy consumption is {actual_kwh:.1f} kilowatt hours, "
                f"which is within normal range.{projection_note}"
            )
        elif deviation_percent > 0:
            return (
                f"{seu_name} used {abs(deviation_percent):.1f}% more energy than expected. "
                f"Actual consumption was {actual_kwh:.1f} kilowatt hours "
                f"compared to a baseline of {baseline_kwh:.1f}. "
                f"This cost an extra ${deviation_cost:.2f}.{projection_note} "
                f"{root_cause.impact_description}."
            )
        else:
            return (
                f"{seu_name} used {abs(deviation_percent):.1f}% less energy than expected. "
                f"Actual consumption was {actual_kwh:.1f} kilowatt hours "
                f"compared to a baseline of {baseline_kwh:.1f}. "
                f"This saved ${deviation_cost:.2f}.{projection_note} "
                f"{root_cause.impact_description}."
            )
    
    # ========================================================================
    # Opportunity Detection Helper Methods
    # ========================================================================
    
    async def _check_excessive_idle(
        self,
        seu_name: str,
        energy_type: str,
        start_date: date,
        end_date: date
    ) -> Optional[ImprovementOpportunity]:
        """Check for excessive idle time (low power consumption for extended periods)."""
        
        # Query for idle time detection (power < 10% of rated power)
        query = """
            SELECT 
                COUNT(*) as idle_count,
                COUNT(*) * 100.0 / NULLIF((SELECT COUNT(*) FROM energy_readings er2
                    JOIN machines m2 ON er2.machine_id = m2.id
                    JOIN seus s2 ON m2.id = ANY(s2.machine_ids)
                    WHERE s2.name = $1
                      AND er2.energy_type = $2
                      AND er2.time >= $3
                      AND er2.time < $4), 0) as idle_percent,
                AVG(er.power_kw) as avg_idle_power
            FROM energy_readings er
            JOIN machines m ON er.machine_id = m.id
            JOIN seus s ON m.id = ANY(s.machine_ids)
            WHERE s.name = $1
              AND er.energy_type = $2
              AND er.time >= $3
              AND er.time < $4
              AND er.power_kw < (m.rated_power_kw * 0.1)
        """
        
        async with db.pool.acquire() as conn:
            result = await conn.fetchrow(
                query, seu_name, energy_type,
                datetime.combine(start_date, datetime.min.time()),
                datetime.combine(end_date, datetime.min.time())
            )
        
        if not result or result['idle_percent'] is None:
            return None
        
        idle_percent = float(result['idle_percent'])
        
        # Only flag if idle time > 30%
        if idle_percent > 30:
            # Estimate savings: reduce idle by 50%
            idle_power = float(result['avg_idle_power']) if result['avg_idle_power'] else 5.0
            hours_idle = (idle_percent / 100) * 24 * (end_date - start_date).days
            potential_savings_kwh = idle_power * hours_idle * 0.5
            potential_savings_usd = potential_savings_kwh * self.electricity_rate
            
            return ImprovementOpportunity(
                rank=0,  # Will be set later
                seu_name=seu_name,
                issue_type=ImprovementType.EXCESSIVE_IDLE,
                description=f"{seu_name} idle {idle_percent:.1f}% of time - potential for auto-shutdown",
                potential_savings_kwh=potential_savings_kwh,
                potential_savings_usd=potential_savings_usd,
                effort=ImplementationEffort.MEDIUM,
                roi_days=int((1000 / potential_savings_usd) * 30) if potential_savings_usd > 0 else 999,
                recommended_action=f"Implement auto-shutdown after 15min idle or reduce idle power setpoint",
                detailed_analysis=f"System idle {idle_percent:.1f}% of time at {idle_power:.1f} kW average"
            )
        
        return None
    
    async def _check_inefficient_scheduling(
        self,
        seu_name: str,
        energy_type: str,
        start_date: date,
        end_date: date
    ) -> Optional[ImprovementOpportunity]:
        """Check for energy use during non-production hours."""
        
        # Query for off-hours consumption (8pm-6am + weekends)
        query = """
            SELECT 
                SUM(er.energy_kwh) as offhours_energy,
                SUM(er.energy_kwh) * 100.0 / NULLIF((
                    SELECT SUM(energy_kwh) FROM energy_readings er2
                    JOIN machines m2 ON er2.machine_id = m2.id
                    JOIN seus s2 ON m2.id = ANY(s2.machine_ids)
                    WHERE s2.name = $1
                      AND er2.energy_type = $2
                      AND er2.time >= $3
                      AND er2.time < $4
                ), 0) as offhours_percent,
                AVG(er.power_kw) as avg_offhours_power
            FROM energy_readings er
            JOIN machines m ON er.machine_id = m.id
            JOIN seus s ON m.id = ANY(s.machine_ids)
            WHERE s.name = $1
              AND er.energy_type = $2
              AND er.time >= $3
              AND er.time < $4
              AND (
                  EXTRACT(HOUR FROM er.time) < 6 
                  OR EXTRACT(HOUR FROM er.time) >= 20
                  OR EXTRACT(DOW FROM er.time) IN (0, 6)
              )
        """
        
        async with db.pool.acquire() as conn:
            result = await conn.fetchrow(
                query, seu_name, energy_type,
                datetime.combine(start_date, datetime.min.time()),
                datetime.combine(end_date, datetime.min.time())
            )
        
        if not result or result['offhours_percent'] is None:
            return None
        
        offhours_percent = float(result['offhours_percent'])
        offhours_energy = float(result['offhours_energy']) if result['offhours_energy'] else 0
        
        # Only flag if off-hours consumption > 20%
        if offhours_percent > 20 and offhours_energy > 50:
            # Estimate savings: reduce off-hours by 60%
            potential_savings_kwh = offhours_energy * 0.6
            potential_savings_usd = potential_savings_kwh * self.electricity_rate
            
            return ImprovementOpportunity(
                rank=0,
                seu_name=seu_name,
                issue_type=ImprovementType.INEFFICIENT_SCHEDULING,
                description=f"{seu_name} uses {offhours_percent:.1f}% energy during off-hours",
                potential_savings_kwh=potential_savings_kwh,
                potential_savings_usd=potential_savings_usd,
                effort=ImplementationEffort.LOW,
                roi_days=int((500 / potential_savings_usd) * 30) if potential_savings_usd > 0 else 999,
                recommended_action="Implement time-based setback schedule for off-hours operation",
                detailed_analysis=f"{offhours_energy:.1f} kWh used outside 6am-8pm M-F"
            )
        
        return None
    
    async def _check_baseline_drift(
        self,
        seu_name: str,
        energy_type: str,
        start_date: date,
        end_date: date
    ) -> Optional[ImprovementOpportunity]:
        """Check for gradual increase in energy consumption (equipment degradation)."""
        
        # Compare recent week vs older data
        mid_date = start_date + (end_date - start_date) / 2
        
        # Get average daily energy for first half vs second half
        query = """
            SELECT 
                AVG(CASE WHEN DATE(er.time) < $4 THEN er.energy_kwh END) as early_avg,
                AVG(CASE WHEN DATE(er.time) >= $4 THEN er.energy_kwh END) as recent_avg,
                COUNT(DISTINCT DATE(er.time)) as days
            FROM energy_readings er
            JOIN machines m ON er.machine_id = m.id
            JOIN seus s ON m.id = ANY(s.machine_ids)
            WHERE s.name = $1
              AND er.energy_type = $2
              AND er.time >= $3
              AND er.time < $5
            GROUP BY DATE(er.time)
        """
        
        async with db.pool.acquire() as conn:
            result = await conn.fetchrow(
                query, seu_name, energy_type,
                datetime.combine(start_date, datetime.min.time()),
                datetime.combine(mid_date, datetime.min.time()),
                datetime.combine(end_date, datetime.min.time())
            )
        
        if not result or not result['early_avg'] or not result['recent_avg']:
            return None
        
        early_avg = float(result['early_avg'])
        recent_avg = float(result['recent_avg'])
        drift_percent = ((recent_avg - early_avg) / early_avg * 100) if early_avg > 0 else 0
        
        # Only flag if drift > 10% increase
        if drift_percent > 10:
            # Estimate savings: restore to baseline efficiency
            days_in_period = (end_date - start_date).days
            excess_daily = recent_avg - early_avg
            potential_savings_kwh = excess_daily * days_in_period * 0.7
            potential_savings_usd = potential_savings_kwh * self.electricity_rate
            
            return ImprovementOpportunity(
                rank=0,
                seu_name=seu_name,
                issue_type=ImprovementType.EQUIPMENT_DEGRADATION,
                description=f"{seu_name} energy consumption increased {drift_percent:.1f}% over period",
                potential_savings_kwh=potential_savings_kwh,
                potential_savings_usd=potential_savings_usd,
                effort=ImplementationEffort.MEDIUM,
                roi_days=int((2000 / potential_savings_usd) * 30) if potential_savings_usd > 0 else 999,
                recommended_action="Schedule maintenance inspection - check for wear, leaks, or calibration drift",
                detailed_analysis=f"Daily average increased from {early_avg:.1f} to {recent_avg:.1f} kWh/day"
            )
        
        return None


# ============================================================================
# Singleton Instance
# ============================================================================

_engine_instance = None

def get_performance_engine() -> EnergyPerformanceEngine:
    """Get singleton instance of Energy Performance Engine."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = EnergyPerformanceEngine()
    return _engine_instance
