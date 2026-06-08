"""
Carbon Analysis Component - Environmental impact tracking
Carbon footprint analysis and sustainability metrics.
"""
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


class CarbonAnalysis:
    """
    Carbon analysis generator for environmental impact reporting.
    
    Features:
    - Total emissions breakdown
    - Carbon intensity metrics
    - Emissions trends
    - Reduction targets tracking
    - Equivalent comparisons (trees, cars, etc.)
    - Renewable energy credits
    """
    
    def prepare_data(self,
                     # Total emissions
                     total_emissions_kg: float,
                     total_emissions_previous_kg: float,
                     period_name: str,
                     
                     # Targets
                     reduction_target_kg: float,
                     target_deadline: str,
                     
                     # Breakdown
                     emissions_by_category: List[Dict[str, Any]],
                     
                     # Intensity
                     carbon_intensity: float,  # kg CO2/kWh
                     carbon_intensity_baseline: float,
                     
                     # Energy mix
                     grid_emissions_factor: float,
                     renewable_percentage: float,
                     
                     # Projections
                     projected_annual_emissions_kg: float,
                     reduction_vs_baseline_kg: float,
                     
                     # Equivalents
                     tree_months: float,
                     car_miles: float,
                     
                     # Charts
                     emissions_breakdown_chart_html: Optional[str] = None,
                     emissions_trend_chart_html: Optional[str] = None,
                     intensity_gauge_html: Optional[str] = None,
                     
                     # Recommendations
                     reduction_initiatives: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Prepare carbon analysis data.
        
        Args:
            total_emissions_kg: Total CO2 emissions in kg
            total_emissions_previous_kg: Previous period emissions
            period_name: Reporting period
            reduction_target_kg: Target emissions reduction
            target_deadline: Target deadline
            emissions_by_category: List of emissions by category
            carbon_intensity: Current carbon intensity
            carbon_intensity_baseline: Baseline carbon intensity
            grid_emissions_factor: Grid emissions factor
            renewable_percentage: Percentage of renewable energy
            projected_annual_emissions_kg: Projected annual emissions
            reduction_vs_baseline_kg: Reduction vs baseline
            tree_months: Equivalent tree-months to absorb
            car_miles: Equivalent car miles
            emissions_breakdown_chart_html: Emissions breakdown chart
            emissions_trend_chart_html: Emissions trend chart
            intensity_gauge_html: Carbon intensity gauge
            reduction_initiatives: List of reduction initiatives
            
        Returns:
            Dictionary with carbon analysis data
        """
        if reduction_initiatives is None:
            reduction_initiatives = []
        
        # Calculate changes
        emissions_change = total_emissions_kg - total_emissions_previous_kg
        emissions_change_pct = (emissions_change / total_emissions_previous_kg * 100) if total_emissions_previous_kg > 0 else 0
        
        # Target progress
        target_progress_pct = (reduction_vs_baseline_kg / reduction_target_kg * 100) if reduction_target_kg > 0 else 0
        on_track = target_progress_pct >= 50  # Simple heuristic
        
        # Intensity improvement
        intensity_improvement = carbon_intensity_baseline - carbon_intensity
        intensity_improvement_pct = (intensity_improvement / carbon_intensity_baseline * 100) if carbon_intensity_baseline > 0 else 0
        
        # Format category breakdowns
        formatted_categories = []
        for cat in emissions_by_category:
            emissions = cat.get('emissions_kg', 0)
            percentage = (emissions / total_emissions_kg * 100) if total_emissions_kg > 0 else 0
            
            formatted_categories.append({
                'name': cat.get('name', 'Unknown'),
                'emissions_kg': emissions,
                'emissions_formatted': self._format_weight(emissions),
                'percentage': percentage,
                'kwh': cat.get('kwh', 0),
                'kwh_formatted': self._format_energy(cat.get('kwh', 0))
            })
        
        # Sort by emissions descending
        formatted_categories.sort(key=lambda x: x['emissions_kg'], reverse=True)
        
        # Renewable status
        renewable_status = 'excellent' if renewable_percentage >= 80 else 'good' if renewable_percentage >= 50 else 'fair' if renewable_percentage >= 25 else 'poor'
        
        data = {
            # Overview metrics
            'total_emissions': self._format_weight(total_emissions_kg),
            'total_emissions_raw': total_emissions_kg,
            'emissions_change': self._format_weight(abs(emissions_change)),
            'emissions_change_pct': abs(emissions_change_pct),
            'emissions_positive': emissions_change < 0,
            'period_name': period_name,
            
            # Intensity
            'carbon_intensity': f"{carbon_intensity:.3f}",
            'carbon_intensity_baseline': f"{carbon_intensity_baseline:.3f}",
            'intensity_improvement': f"{abs(intensity_improvement):.3f}",
            'intensity_improvement_pct': abs(intensity_improvement_pct),
            'intensity_positive': intensity_improvement > 0,
            
            # Grid & renewable
            'grid_factor': f"{grid_emissions_factor:.3f}",
            'renewable_pct': renewable_percentage,
            'renewable_status': renewable_status,
            'fossil_pct': 100 - renewable_percentage,
            
            # Target tracking
            'reduction_target': self._format_weight(reduction_target_kg),
            'target_deadline': target_deadline,
            'reduction_achieved': self._format_weight(reduction_vs_baseline_kg),
            'target_progress_pct': target_progress_pct,
            'on_track': on_track,
            'target_status': 'success' if on_track else 'warning',
            
            # Projections
            'projected_annual': self._format_weight(projected_annual_emissions_kg),
            
            # Equivalents
            'tree_months': f"{tree_months:,.0f}",
            'car_miles': f"{car_miles:,.0f}",
            
            # Breakdowns
            'categories': formatted_categories,
            'top_emitter': formatted_categories[0] if formatted_categories else None,
            
            # Charts
            'emissions_breakdown_chart_html': emissions_breakdown_chart_html,
            'has_breakdown_chart': emissions_breakdown_chart_html is not None,
            'emissions_trend_chart_html': emissions_trend_chart_html,
            'has_trend_chart': emissions_trend_chart_html is not None,
            'intensity_gauge_html': intensity_gauge_html,
            'has_intensity_gauge': intensity_gauge_html is not None,
            
            # Initiatives
            'reduction_initiatives': reduction_initiatives,
            'has_initiatives': len(reduction_initiatives) > 0,
            'initiative_count': len(reduction_initiatives)
        }
        
        return data
    
    def _format_weight(self, kg: float) -> str:
        """Format weight values."""
        if kg >= 1_000_000:
            return f"{kg / 1_000_000:.2f}M"
        elif kg >= 1_000:
            return f"{kg / 1_000:.1f}K"
        else:
            return f"{kg:.0f}"
    
    def _format_energy(self, kwh: float) -> str:
        """Format energy values."""
        if kwh >= 1_000_000:
            return f"{kwh / 1_000_000:.2f}M"
        elif kwh >= 1_000:
            return f"{kwh / 1_000:.1f}K"
        else:
            return f"{kwh:.0f}"
