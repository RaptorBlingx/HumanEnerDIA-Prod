"""
Cover Page Component - Hero design for EnMS Reports v2
Creates stunning first impression with key metrics and hero visualization.
"""
from datetime import datetime
from typing import Dict, Any, Optional
import logging
import base64
import os

logger = logging.getLogger(__name__)


class CoverPage:
    """
    Cover page generator with hero design.
    
    Features:
    - Large branding area
    - Report period and metadata
    - 4 key metric highlights (KPI cards)
    - Hero chart (energy trend)
    - Professional gradient background
    """
    
    def __init__(self):
        self.template_name = "cover_page.html"
    
    def prepare_data(self,
                    factory_name: str,
                    report_period: str,
                    total_energy_kwh: float,
                    total_cost: float,
                    total_carbon_kg: float,
                    efficiency_score: float,
                    energy_trend: str = "↑ 12.5%",
                    cost_trend: str = "↓ 5.2%",
                    carbon_trend: str = "↓ 8.1%",
                    efficiency_trend: str = "↑ 3.7%",
                    hero_chart_html: Optional[str] = None,
                    generated_date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Prepare cover page data.
        
        Args:
            factory_name: Factory/facility name
            report_period: e.g., "November 2025" or "Q4 2025"
            total_energy_kwh: Total energy consumption
            total_cost: Total energy cost
            total_carbon_kg: Total carbon emissions
            efficiency_score: Overall efficiency (0-100)
            energy_trend: Trend indicator (e.g., "↑ 12.5%")
            cost_trend: Cost trend vs previous period
            carbon_trend: Carbon trend
            efficiency_trend: Efficiency improvement
            hero_chart_html: HTML for hero chart (6-month trend)
            generated_date: Report generation timestamp
            
        Returns:
            Dictionary with all cover page data
        """
        generated_date = generated_date or datetime.now()
        
        # Format numbers with proper units
        data = {
            'factory_name': factory_name,
            'report_period': report_period,
            'generated_date': generated_date.strftime("%B %d, %Y"),
            'generated_time': generated_date.strftime("%I:%M %p"),
            
            # Key metrics (KPI cards)
            'metrics': [
                {
                    'title': 'Total Energy',
                    'value': self._format_energy(total_energy_kwh),
                    'unit': 'kWh',
                    'trend': energy_trend,
                    'trend_positive': '↓' in energy_trend,  # Less energy is good
                    'icon': 'kWh',
                    'color': 'primary'  # Teal
                },
                {
                    'title': 'Energy Cost',
                    'value': self._format_currency(total_cost),
                    'unit': 'USD',
                    'trend': cost_trend,
                    'trend_positive': '↓' in cost_trend,  # Less cost is good
                    'icon': '$',
                    'color': 'warning'  # Orange
                },
                {
                    'title': 'Carbon Emissions',
                    'value': self._format_weight(total_carbon_kg),
                    'unit': 'kg CO₂',
                    'trend': carbon_trend,
                    'trend_positive': '↓' in carbon_trend,  # Less carbon is good
                    'icon': 'CO₂',
                    'color': 'success'  # Green
                },
                {
                    'title': 'Efficiency Score',
                    'value': f"{efficiency_score:.1f}",
                    'unit': '%',
                    'trend': efficiency_trend,
                    'trend_positive': '↑' in efficiency_trend,  # More efficiency is good
                    'icon': '%',
                    'color': 'secondary'  # Navy
                }
            ],
            
            # Hero chart
            'hero_chart_html': hero_chart_html,
            'has_hero_chart': hero_chart_html is not None,
            
            # Logo as base64
            'logo_base64': self._get_logo_base64(),
            
            # Metadata
            'report_version': 'v2.0.0',
            'iso_standard': 'ISO 50001:2018',
            'report_type': 'Energy Management Report'
        }
        
        return data
    
    def _format_energy(self, kwh: float) -> str:
        """Format energy values with appropriate units."""
        if kwh >= 1_000_000:
            return f"{kwh / 1_000_000:.2f}"
        elif kwh >= 1_000:
            return f"{kwh / 1_000:.1f}"
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
    
    def _get_logo_base64(self) -> str:
        """Load logo and encode as base64 for embedding in HTML."""
        try:
            logo_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'images', 'aplus-logo.png')
            with open(logo_path, 'rb') as f:
                logo_data = base64.b64encode(f.read()).decode()
                return f"data:image/png;base64,{logo_data}"
        except Exception as e:
            logger.error(f"Failed to load logo: {e}")
            return ""
