"""
Machine Analysis Component - Individual machine deep dives
Comprehensive performance analysis for each machine/SEU.
"""
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


class MachineAnalysis:
    """
    Machine analysis generator for detailed equipment performance.
    
    Features:
    - Machine ranking (top consumers)
    - Individual machine profiles
    - Performance metrics and trends
    - Anomaly detection results
    - Efficiency analysis
    - Actionable recommendations
    """
    
    def __init__(self):
        self.ranking_template = "machine_ranking.html"
        self.profile_template = "machine_profile.html"
    
    def prepare_ranking_data(self,
                            machines: List[Dict[str, Any]],
                            total_consumption: float,
                            period_name: str,
                            ranking_chart_html: Optional[str] = None) -> Dict[str, Any]:
        """
        Prepare machine ranking data.
        
        Args:
            machines: List of machine data dictionaries
            total_consumption: Total facility consumption
            period_name: Reporting period
            ranking_chart_html: Horizontal bar chart of top machines
            
        Returns:
            Dictionary with ranking data
        """
        # Calculate percentages and format
        formatted_machines = []
        for idx, machine in enumerate(machines, 1):
            consumption = machine.get('consumption_kwh', 0)
            percentage = (consumption / total_consumption * 100) if total_consumption > 0 else 0
            
            formatted_machines.append({
                'rank': idx,
                'name': machine.get('name', 'Unknown'),
                'type': machine.get('type', 'N/A'),
                'location': machine.get('location', 'N/A'),
                'consumption_kwh': consumption,
                'consumption_formatted': self._format_energy(consumption),
                'percentage': percentage,
                'cost': machine.get('cost', 0),
                'cost_formatted': self._format_currency(machine.get('cost', 0)),
                'efficiency': machine.get('efficiency_pct', 0),
                'status': machine.get('status', 'Normal'),
                'status_color': self._get_status_color(machine.get('status', 'Normal')),
                'anomaly_count': machine.get('anomaly_count', 0),
                'operating_hours': machine.get('operating_hours', 0),
                'sec': machine.get('sec', 0),  # Specific Energy Consumption
                'sec_formatted': f"{machine.get('sec', 0):.2f}"
            })
        
        data = {
            'machines': formatted_machines,
            'machine_count': len(formatted_machines),
            'period_name': period_name,
            'total_consumption': self._format_energy(total_consumption),
            'top_consumer': formatted_machines[0] if formatted_machines else None,
            'has_ranking_chart': ranking_chart_html is not None,
            'ranking_chart_html': ranking_chart_html
        }
        
        return data
    
    def prepare_profile_data(self,
                            # Machine identification
                            machine_name: str,
                            machine_type: str,
                            machine_id: str,
                            location: str,
                            
                            # Performance metrics
                            consumption_kwh: float,
                            consumption_change_pct: float,
                            baseline_kwh: float,
                            efficiency_pct: float,
                            efficiency_change_pct: float,
                            
                            # Operating metrics
                            operating_hours: int,
                            total_hours: int,
                            avg_power_kw: float,
                            peak_power_kw: float,
                            
                            # Energy metrics
                            sec: float,  # Specific Energy Consumption
                            sec_baseline: float,
                            production_units: float,
                            production_unit_name: str,
                            
                            # Cost & carbon
                            energy_cost: float,
                            carbon_emissions_kg: float,
                            
                            # Anomalies
                            anomaly_count: int,
                            recent_anomalies: List[Dict[str, Any]],
                            
                            # Charts
                            trend_chart_html: Optional[str] = None,
                            efficiency_gauge_html: Optional[str] = None,
                            daily_pattern_chart_html: Optional[str] = None,
                            
                            # Recommendations
                            recommendations: Optional[List[Dict[str, Any]]] = None,
                            
                            # Additional specs
                            specs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Prepare individual machine profile data.
        
        Args:
            machine_name: Machine name/identifier
            machine_type: Equipment type
            machine_id: Unique ID
            location: Physical location
            consumption_kwh: Total consumption
            consumption_change_pct: Change vs previous period
            baseline_kwh: Expected consumption
            efficiency_pct: Overall efficiency
            efficiency_change_pct: Efficiency improvement
            operating_hours: Hours operated
            total_hours: Total hours in period
            avg_power_kw: Average power demand
            peak_power_kw: Peak power demand
            sec: Specific Energy Consumption (kWh/unit)
            sec_baseline: SEC baseline
            production_units: Units produced
            production_unit_name: Unit name (e.g., "parts", "tons")
            energy_cost: Energy cost
            carbon_emissions_kg: Carbon emissions
            anomaly_count: Number of anomalies
            recent_anomalies: List of anomaly events
            trend_chart_html: Consumption trend chart
            efficiency_gauge_html: Efficiency gauge chart
            daily_pattern_chart_html: Daily usage pattern
            recommendations: List of actionable recommendations
            specs: Machine specifications
            
        Returns:
            Dictionary with profile data
        """
        if recommendations is None:
            recommendations = []
        
        if specs is None:
            specs = {}
        
        if recent_anomalies is None:
            recent_anomalies = []
        
        # Calculate utilization
        utilization_pct = (operating_hours / total_hours * 100) if total_hours > 0 else 0
        
        # Calculate variance from baseline
        vs_baseline_kwh = consumption_kwh - baseline_kwh
        vs_baseline_pct = (vs_baseline_kwh / baseline_kwh * 100) if baseline_kwh > 0 else 0
        
        # SEC performance
        sec_vs_baseline_pct = ((sec - sec_baseline) / sec_baseline * 100) if sec_baseline > 0 else 0
        sec_status = 'excellent' if sec_vs_baseline_pct < -10 else 'good' if sec_vs_baseline_pct < 0 else 'fair' if sec_vs_baseline_pct < 10 else 'poor'
        
        # Anomaly status
        anomaly_status = 'success' if anomaly_count == 0 else 'warning' if anomaly_count < 3 else 'danger'
        
        data = {
            # Identification
            'machine_name': machine_name,
            'machine_type': machine_type,
            'machine_id': machine_id,
            'location': location,
            
            # Primary metrics
            'consumption': self._format_energy(consumption_kwh),
            'consumption_raw': consumption_kwh,
            'consumption_change_pct': consumption_change_pct,
            'consumption_positive': consumption_change_pct < 0,
            'baseline': self._format_energy(baseline_kwh),
            'vs_baseline_kwh': self._format_energy(abs(vs_baseline_kwh)),
            'vs_baseline_pct': abs(vs_baseline_pct),
            'vs_baseline_positive': vs_baseline_kwh < 0,
            
            # Efficiency
            'efficiency_pct': efficiency_pct,
            'efficiency_change_pct': efficiency_change_pct,
            'efficiency_positive': efficiency_change_pct > 0,
            'efficiency_status': 'excellent' if efficiency_pct >= 90 else 'good' if efficiency_pct >= 75 else 'fair' if efficiency_pct >= 60 else 'poor',
            
            # Operating metrics
            'operating_hours': operating_hours,
            'total_hours': total_hours,
            'utilization_pct': utilization_pct,
            'avg_power_kw': f"{avg_power_kw:,.1f}",
            'peak_power_kw': f"{peak_power_kw:,.1f}",
            
            # SEC metrics
            'sec': f"{sec:.3f}",
            'sec_baseline': f"{sec_baseline:.3f}",
            'sec_vs_baseline_pct': abs(sec_vs_baseline_pct),
            'sec_positive': sec_vs_baseline_pct < 0,
            'sec_status': sec_status,
            'production_units': f"{production_units:,.0f}",
            'production_unit_name': production_unit_name,
            
            # Cost & carbon
            'energy_cost': self._format_currency(energy_cost),
            'carbon_emissions': self._format_weight(carbon_emissions_kg),
            
            # Anomalies
            'anomaly_count': anomaly_count,
            'anomaly_status': anomaly_status,
            'recent_anomalies': recent_anomalies[:5],  # Top 5
            'has_anomalies': len(recent_anomalies) > 0,
            
            # Charts
            'trend_chart_html': trend_chart_html,
            'has_trend_chart': trend_chart_html is not None,
            'efficiency_gauge_html': efficiency_gauge_html,
            'has_efficiency_gauge': efficiency_gauge_html is not None,
            'daily_pattern_chart_html': daily_pattern_chart_html,
            'has_daily_pattern': daily_pattern_chart_html is not None,
            
            # Recommendations
            'recommendations': recommendations,
            'has_recommendations': len(recommendations) > 0,
            'recommendation_count': len(recommendations),
            
            # Specs
            'specs': specs,
            'has_specs': len(specs) > 0
        }
        
        return data
    
    def _format_energy(self, kwh: float) -> str:
        """Format energy values."""
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
        """Format weight values."""
        if kg >= 1_000_000:
            return f"{kg / 1_000_000:.2f}M"
        elif kg >= 1_000:
            return f"{kg / 1_000:.1f}K"
        else:
            return f"{kg:.0f}"
    
    def _get_status_color(self, status: str) -> str:
        """Get color for machine status."""
        status_colors = {
            'Normal': '#48bb78',
            'Warning': '#ed8936',
            'Critical': '#e53e3e',
            'Offline': '#718096',
            'Maintenance': '#4299e1'
        }
        return status_colors.get(status, '#718096')
