"""
Executive Dashboard Component - High-level KPI overview
Shows key metrics, trends, top consumers, and anomalies.
"""
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


class ExecutiveDashboard:
    """
    Executive dashboard generator for C-suite overview.
    
    Features:
    - 4 primary KPIs with sparklines
    - 6-month consumption trend
    - Top 5 energy consumers
    - Recent anomaly summary
    - Month-over-month comparisons
    """
    
    def __init__(self):
        self.template_name = "executive_dashboard.html"
    
    def prepare_data(self,
                    # Primary KPIs
                    total_energy_kwh: float,
                    total_cost: float,
                    total_carbon_kg: float,
                    efficiency_score: float,
                    
                    # Trends vs previous period
                    energy_change_pct: float,
                    cost_change_pct: float,
                    carbon_change_pct: float,
                    efficiency_change_pct: float,
                    
                    # Sparkline data (6-month history)
                    energy_sparkline_data: List[float],
                    cost_sparkline_data: List[float],
                    carbon_sparkline_data: List[float],
                    efficiency_sparkline_data: List[float],
                    
                    # Trend chart HTML (embedded)
                    trend_chart_html: Optional[str] = None,
                    
                    # Top consumers
                    top_consumers: Optional[List[Dict[str, Any]]] = None,
                    
                    # Anomalies
                    anomaly_count: int = 0,
                    recent_anomalies: Optional[List[Dict[str, Any]]] = None,
                    
                    # Peak demand
                    peak_demand_kw: float = 0,
                    peak_demand_time: Optional[str] = None,
                    
                    # Cost breakdown
                    baseline_cost: float = 0,
                    actual_cost: float = 0,
                    cost_savings: float = 0) -> Dict[str, Any]:
        """
        Prepare executive dashboard data.
        
        Args:
            total_energy_kwh: Total energy consumption
            total_cost: Total energy cost
            total_carbon_kg: Total carbon emissions
            efficiency_score: Overall efficiency (0-100)
            energy_change_pct: Energy trend vs previous period
            cost_change_pct: Cost trend
            carbon_change_pct: Carbon trend
            efficiency_change_pct: Efficiency improvement
            energy_sparkline_data: 6-month energy history for sparkline
            cost_sparkline_data: 6-month cost history
            carbon_sparkline_data: 6-month carbon history
            efficiency_sparkline_data: 6-month efficiency history
            trend_chart_html: Main trend chart (optional)
            top_consumers: List of top 5 machines
            anomaly_count: Number of anomalies detected
            recent_anomalies: List of recent anomaly events
            peak_demand_kw: Peak power demand
            peak_demand_time: When peak occurred
            baseline_cost: Expected cost (baseline)
            actual_cost: Actual cost
            cost_savings: Savings vs baseline
            
        Returns:
            Dictionary with all dashboard data
        """
        # Prepare top consumers (default to empty if not provided)
        if top_consumers is None:
            top_consumers = []
        
        # Prepare anomalies (default to empty if not provided)
        if recent_anomalies is None:
            recent_anomalies = []
        
        # Format KPI cards with sparklines
        kpi_cards = [
            {
                'title': 'Total Energy Consumption',
                'value': self._format_energy(total_energy_kwh),
                'unit': 'kWh',
                'change_pct': energy_change_pct,
                'is_positive': energy_change_pct < 0,  # Less energy is good
                'icon': 'kWh',
                'color': 'primary',
                'sparkline_data': energy_sparkline_data,
                'description': 'vs previous month'
            },
            {
                'title': 'Energy Cost',
                'value': self._format_currency(total_cost),
                'unit': '',
                'change_pct': cost_change_pct,
                'is_positive': cost_change_pct < 0,  # Less cost is good
                'icon': '$',
                'color': 'warning',
                'sparkline_data': cost_sparkline_data,
                'description': 'vs previous month'
            },
            {
                'title': 'Carbon Emissions',
                'value': self._format_weight(total_carbon_kg),
                'unit': 'kg CO₂',
                'change_pct': carbon_change_pct,
                'is_positive': carbon_change_pct < 0,  # Less carbon is good
                'icon': 'CO₂',
                'color': 'success',
                'sparkline_data': carbon_sparkline_data,
                'description': 'vs previous month'
            },
            {
                'title': 'Energy Efficiency',
                'value': f"{efficiency_score:.1f}",
                'unit': '%',
                'change_pct': efficiency_change_pct,
                'is_positive': efficiency_change_pct > 0,  # More efficiency is good
                'icon': '%',
                'color': 'secondary',
                'sparkline_data': efficiency_sparkline_data,
                'description': 'vs previous month'
            }
        ]
        
        # Determine anomaly status color
        anomaly_status = 'success' if anomaly_count == 0 else 'warning' if anomaly_count < 5 else 'danger'
        
        data = {
            'kpi_cards': kpi_cards,
            'trend_chart_html': trend_chart_html,
            'has_trend_chart': trend_chart_html is not None,
            
            # Top consumers
            'top_consumers': top_consumers[:5],  # Limit to top 5
            'has_consumers': len(top_consumers) > 0,
            
            # Anomaly summary
            'anomaly_count': anomaly_count,
            'anomaly_status': anomaly_status,
            'recent_anomalies': recent_anomalies[:3],  # Show latest 3
            'has_anomalies': len(recent_anomalies) > 0,
            
            # Peak demand
            'peak_demand_kw': f"{peak_demand_kw:,.1f}",
            'peak_demand_time': peak_demand_time or 'N/A',
            
            # Cost analysis
            'baseline_cost': self._format_currency(baseline_cost),
            'actual_cost': self._format_currency(actual_cost),
            'cost_savings': self._format_currency(abs(cost_savings)),
            'is_saving': cost_savings < 0,
            'savings_pct': abs((cost_savings / baseline_cost * 100)) if baseline_cost > 0 else 0
        }
        
        return data
    
    def _format_energy(self, kwh: float) -> str:
        """Format energy values with appropriate units."""
        if kwh >= 1_000_000:
            return f"{kwh / 1_000_000:.2f}M"
        elif kwh >= 1_000:
            return f"{kwh / 1_000:.1f}K"
        else:
            return f"{kwh:.0f}"
    
    def _format_currency(self, amount: float) -> str:
        """Format currency values."""
        if amount >= 1_000_000:
            return f"${amount / 1_000_000:.2f}M"
        elif amount >= 1_000:
            return f"${amount / 1_000:.1f}K"
        else:
            return f"${amount:.2f}"
    
    def _format_weight(self, kg: float) -> str:
        """Format weight/emissions."""
        if kg >= 1_000_000:
            return f"{kg / 1_000_000:.2f}M"
        elif kg >= 1_000:
            return f"{kg / 1_000:.1f}K"
        else:
            return f"{kg:.0f}"
