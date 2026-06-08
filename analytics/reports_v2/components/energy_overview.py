"""
Energy Overview Component - Total consumption analysis
Detailed breakdown of energy usage patterns and distributions.
"""
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


class EnergyOverview:
    """
    Energy overview generator for detailed consumption analysis.
    
    Features:
    - Total consumption with period comparison
    - Breakdown by machine type/category
    - Time-based analysis (hourly, daily patterns)
    - Peak consumption identification
    - Load factor analysis
    """
    
    def __init__(self):
        self.template_name = "energy_overview.html"
    
    def prepare_data(self,
                    # Total consumption
                    total_consumption_kwh: float,
                    previous_period_kwh: float,
                    baseline_kwh: float,
                    
                    # Period info
                    period_name: str,
                    period_days: int,
                    
                    # Breakdown by category
                    category_breakdown: List[Dict[str, Any]],
                    
                    # Time patterns
                    hourly_avg_kwh: float,
                    daily_avg_kwh: float,
                    peak_hour_consumption: float,
                    peak_hour_time: str,
                    off_peak_consumption: float,
                    
                    # Load factor
                    peak_demand_kw: float,
                    average_demand_kw: float,
                    load_factor_pct: float,
                    
                    # Charts
                    breakdown_chart_html: Optional[str] = None,
                    hourly_pattern_chart_html: Optional[str] = None,
                    daily_trend_chart_html: Optional[str] = None,
                    
                    # Additional metrics
                    operating_hours: int = 0,
                    downtime_hours: int = 0) -> Dict[str, Any]:
        """
        Prepare energy overview data.
        
        Args:
            total_consumption_kwh: Total energy consumption
            previous_period_kwh: Previous period consumption for comparison
            baseline_kwh: Baseline/expected consumption
            period_name: e.g., "November 2025"
            period_days: Number of days in period
            category_breakdown: List of categories with consumption data
            hourly_avg_kwh: Average consumption per hour
            daily_avg_kwh: Average consumption per day
            peak_hour_consumption: Consumption during peak hour
            peak_hour_time: When peak occurred
            off_peak_consumption: Off-peak consumption
            peak_demand_kw: Maximum demand (kW)
            average_demand_kw: Average demand
            load_factor_pct: Load factor percentage
            breakdown_chart_html: Pie/bar chart for category breakdown
            hourly_pattern_chart_html: Heatmap of hourly patterns
            daily_trend_chart_html: Line chart of daily consumption
            operating_hours: Total operating hours
            downtime_hours: Total downtime
            
        Returns:
            Dictionary with all overview data
        """
        # Calculate changes
        vs_previous_pct = ((total_consumption_kwh - previous_period_kwh) / previous_period_kwh * 100) if previous_period_kwh > 0 else 0
        vs_baseline_pct = ((total_consumption_kwh - baseline_kwh) / baseline_kwh * 100) if baseline_kwh > 0 else 0
        
        # Format category breakdown with percentages
        total_category_consumption = sum(cat.get('consumption', 0) for cat in category_breakdown)
        formatted_categories = []
        
        for cat in category_breakdown:
            consumption = cat.get('consumption', 0)
            percentage = (consumption / total_category_consumption * 100) if total_category_consumption > 0 else 0
            
            formatted_categories.append({
                'name': cat.get('name', 'Unknown'),
                'consumption': consumption,
                'consumption_formatted': self._format_energy(consumption),
                'percentage': percentage,
                'machine_count': cat.get('machine_count', 0),
                'avg_per_machine': consumption / cat.get('machine_count', 1) if cat.get('machine_count', 0) > 0 else 0,
                'color': cat.get('color', '#00A8E8')
            })
        
        # Sort by consumption descending
        formatted_categories.sort(key=lambda x: x['consumption'], reverse=True)
        
        # Calculate utilization
        total_hours = period_days * 24
        utilization_pct = (operating_hours / total_hours * 100) if total_hours > 0 else 0
        
        data = {
            # Main KPIs
            'total_consumption': self._format_energy(total_consumption_kwh),
            'total_consumption_raw': total_consumption_kwh,
            'previous_period': self._format_energy(previous_period_kwh),
            'baseline': self._format_energy(baseline_kwh),
            'period_name': period_name,
            'period_days': period_days,
            
            # Comparisons
            'vs_previous_pct': vs_previous_pct,
            'vs_previous_positive': vs_previous_pct < 0,  # Less is good
            'vs_baseline_pct': vs_baseline_pct,
            'vs_baseline_positive': vs_baseline_pct < 0,
            
            # Averages
            'hourly_avg': self._format_energy(hourly_avg_kwh),
            'daily_avg': self._format_energy(daily_avg_kwh),
            
            # Peak analysis
            'peak_hour_consumption': self._format_energy(peak_hour_consumption),
            'peak_hour_time': peak_hour_time,
            'off_peak_consumption': self._format_energy(off_peak_consumption),
            'peak_vs_offpeak_pct': ((peak_hour_consumption - off_peak_consumption) / off_peak_consumption * 100) if off_peak_consumption > 0 else 0,
            
            # Load factor
            'peak_demand_kw': f"{peak_demand_kw:,.1f}",
            'average_demand_kw': f"{average_demand_kw:,.1f}",
            'load_factor_pct': load_factor_pct,
            'load_factor_status': 'excellent' if load_factor_pct >= 80 else 'good' if load_factor_pct >= 60 else 'fair' if load_factor_pct >= 40 else 'poor',
            
            # Operating metrics
            'operating_hours': operating_hours,
            'downtime_hours': downtime_hours,
            'utilization_pct': utilization_pct,
            'total_hours': total_hours,
            
            # Category breakdown
            'categories': formatted_categories,
            'top_category': formatted_categories[0] if formatted_categories else None,
            'category_count': len(formatted_categories),
            
            # Charts
            'breakdown_chart_html': breakdown_chart_html,
            'has_breakdown_chart': breakdown_chart_html is not None,
            'hourly_pattern_chart_html': hourly_pattern_chart_html,
            'has_hourly_chart': hourly_pattern_chart_html is not None,
            'daily_trend_chart_html': daily_trend_chart_html,
            'has_daily_chart': daily_trend_chart_html is not None
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
