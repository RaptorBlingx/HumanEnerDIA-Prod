"""
Cost Analysis Component - Energy cost breakdown and optimization
Financial analysis of energy consumption and cost-saving opportunities.
"""
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


class CostAnalysis:
    """
    Cost analysis generator for energy cost insights.
    
    Features:
    - Total cost breakdown by category/machine/tariff
    - Cost trends over time
    - Peak vs off-peak cost analysis
    - Budget vs actual comparison
    - Cost-saving opportunities
    - ROI projections for efficiency improvements
    """
    
    def prepare_data(self,
                     # Total costs
                     total_cost: float,
                     total_cost_previous: float,
                     budget: float,
                     period_name: str,
                     
                     # Cost breakdown
                     cost_by_category: List[Dict[str, Any]],
                     cost_by_tariff: Dict[str, float],
                     
                     # Time-based analysis
                     peak_cost: float,
                     peak_kwh: float,
                     off_peak_cost: float,
                     off_peak_kwh: float,
                     
                     # Rates
                     avg_rate: float,
                     peak_rate: float,
                     off_peak_rate: float,
                     
                     # Projections
                     projected_annual_cost: float,
                     potential_savings: float,
                     
                     # Charts
                     cost_breakdown_chart_html: Optional[str] = None,
                     cost_trend_chart_html: Optional[str] = None,
                     tariff_comparison_chart_html: Optional[str] = None,
                     
                     # Savings opportunities
                     savings_opportunities: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Prepare cost analysis data.
        
        Args:
            total_cost: Total energy cost for period
            total_cost_previous: Previous period cost
            budget: Budget allocation
            period_name: Reporting period
            cost_by_category: List of cost breakdowns by category
            cost_by_tariff: Dict of tariff costs (on-peak, off-peak, shoulder)
            peak_cost: Cost during peak hours
            peak_kwh: Consumption during peak hours
            off_peak_cost: Cost during off-peak hours
            off_peak_kwh: Consumption during off-peak hours
            avg_rate: Average cost per kWh
            peak_rate: Peak tariff rate
            off_peak_rate: Off-peak tariff rate
            projected_annual_cost: Projected annual cost
            potential_savings: Potential cost savings
            cost_breakdown_chart_html: Cost breakdown chart
            cost_trend_chart_html: Cost trend over time
            tariff_comparison_chart_html: Tariff comparison chart
            savings_opportunities: List of cost-saving opportunities
            
        Returns:
            Dictionary with cost analysis data
        """
        if savings_opportunities is None:
            savings_opportunities = []
        
        # Calculate changes
        cost_change = total_cost - total_cost_previous
        cost_change_pct = (cost_change / total_cost_previous * 100) if total_cost_previous > 0 else 0
        
        # Budget variance
        budget_variance = total_cost - budget
        budget_variance_pct = (budget_variance / budget * 100) if budget > 0 else 0
        over_budget = budget_variance > 0
        
        # Format category breakdowns
        formatted_categories = []
        for cat in cost_by_category:
            cost = cat.get('cost', 0)
            percentage = (cost / total_cost * 100) if total_cost > 0 else 0
            
            formatted_categories.append({
                'name': cat.get('name', 'Unknown'),
                'cost': cost,
                'cost_formatted': self._format_currency(cost),
                'percentage': percentage,
                'kwh': cat.get('kwh', 0),
                'kwh_formatted': self._format_energy(cat.get('kwh', 0)),
                'avg_rate': (cost / cat.get('kwh', 1)) if cat.get('kwh', 0) > 0 else 0
            })
        
        # Sort by cost descending
        formatted_categories.sort(key=lambda x: x['cost'], reverse=True)
        
        # Tariff analysis
        total_tariff_cost = sum(cost_by_tariff.values())
        formatted_tariffs = []
        for tariff, cost in cost_by_tariff.items():
            percentage = (cost / total_tariff_cost * 100) if total_tariff_cost > 0 else 0
            formatted_tariffs.append({
                'name': tariff,
                'cost': cost,
                'cost_formatted': self._format_currency(cost),
                'percentage': percentage
            })
        
        # Peak vs off-peak efficiency
        peak_avg_rate = (peak_cost / peak_kwh) if peak_kwh > 0 else 0
        off_peak_avg_rate = (off_peak_cost / off_peak_kwh) if off_peak_kwh > 0 else 0
        
        # Savings potential
        savings_pct = (potential_savings / total_cost * 100) if total_cost > 0 else 0
        
        data = {
            # Overview metrics
            'total_cost': self._format_currency(total_cost),
            'total_cost_raw': total_cost,
            'cost_change': self._format_currency(abs(cost_change)),
            'cost_change_pct': abs(cost_change_pct),
            'cost_positive': cost_change < 0,
            'period_name': period_name,
            
            # Budget
            'budget': self._format_currency(budget),
            'budget_variance': self._format_currency(abs(budget_variance)),
            'budget_variance_pct': abs(budget_variance_pct),
            'over_budget': over_budget,
            'budget_status': 'danger' if over_budget else 'success',
            
            # Rates
            'avg_rate': f"${avg_rate:.3f}",
            'peak_rate': f"${peak_rate:.3f}",
            'off_peak_rate': f"${off_peak_rate:.3f}",
            
            # Peak vs off-peak
            'peak_cost': self._format_currency(peak_cost),
            'peak_kwh': self._format_energy(peak_kwh),
            'peak_avg_rate': f"${peak_avg_rate:.3f}",
            'off_peak_cost': self._format_currency(off_peak_cost),
            'off_peak_kwh': self._format_energy(off_peak_kwh),
            'off_peak_avg_rate': f"${off_peak_avg_rate:.3f}",
            'peak_cost_pct': (peak_cost / total_cost * 100) if total_cost > 0 else 0,
            'off_peak_cost_pct': (off_peak_cost / total_cost * 100) if total_cost > 0 else 0,
            
            # Breakdowns
            'categories': formatted_categories,
            'tariffs': formatted_tariffs,
            'top_cost_category': formatted_categories[0] if formatted_categories else None,
            
            # Projections
            'projected_annual': self._format_currency(projected_annual_cost),
            'potential_savings': self._format_currency(potential_savings),
            'savings_pct': savings_pct,
            
            # Charts
            'cost_breakdown_chart_html': cost_breakdown_chart_html,
            'has_breakdown_chart': cost_breakdown_chart_html is not None,
            'cost_trend_chart_html': cost_trend_chart_html,
            'has_trend_chart': cost_trend_chart_html is not None,
            'tariff_comparison_chart_html': tariff_comparison_chart_html,
            'has_tariff_chart': tariff_comparison_chart_html is not None,
            
            # Opportunities
            'savings_opportunities': savings_opportunities,
            'has_opportunities': len(savings_opportunities) > 0,
            'opportunity_count': len(savings_opportunities)
        }
        
        return data
    
    def _format_currency(self, amount: float) -> str:
        """Format currency values."""
        if amount >= 1_000_000:
            return f"${amount / 1_000_000:.2f}M"
        elif amount >= 1_000:
            return f"${amount / 1_000:.1f}K"
        else:
            return f"${amount:.2f}"
    
    def _format_energy(self, kwh: float) -> str:
        """Format energy values."""
        if kwh >= 1_000_000:
            return f"{kwh / 1_000_000:.2f}M"
        elif kwh >= 1_000:
            return f"{kwh / 1_000:.1f}K"
        else:
            return f"{kwh:.0f}"
