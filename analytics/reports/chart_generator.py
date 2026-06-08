"""
Report Chart Generator
======================
Generates matplotlib charts for reports.
"""

from typing import List, Dict, Any
from io import BytesIO
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime


class ReportChartGenerator:
    """Generate charts for PDF reports."""
    
    def __init__(self):
        # Set style
        plt.style.use('seaborn-v0_8-darkgrid')
        
        # Colors matching industrial theme
        self.color_navy = '#1a365d'
        self.color_teal = '#00A8E8'
        self.color_success = '#48bb78'
        self.color_warning = '#ed8936'
    
    def generate_machine_consumption_chart(
        self,
        machines: List[Dict[str, Any]],
        top_n: int = 8
    ) -> BytesIO:
        """
        Generate horizontal bar chart for machine consumption.
        
        Args:
            machines: List of machine data dicts
            top_n: Number of top machines to show
        
        Returns:
            BytesIO buffer with PNG image
        """
        # Take top N machines
        top_machines = machines[:top_n]
        
        # Extract data
        names = [m['name'] for m in top_machines]
        kwh = [m['kwh'] for m in top_machines]
        
        # Create figure (smaller size)
        fig, ax = plt.subplots(figsize=(6, 3.2))
        
        # Horizontal bar chart
        bars = ax.barh(names, kwh, color=self.color_teal)
        
        # Customize
        ax.set_xlabel('Energy Consumption (kWh)', fontsize=10, fontweight='bold')
        ax.set_title('Top Machines by Energy Consumption', fontsize=12, fontweight='bold', color=self.color_navy)
        ax.grid(axis='x', alpha=0.3)
        
        # Add value labels
        for i, bar in enumerate(bars):
            width = bar.get_width()
            ax.text(width, bar.get_y() + bar.get_height()/2, 
                   f'{kwh[i]:,.0f}', 
                   ha='left', va='center', fontsize=9, fontweight='bold')
        
        # Tight layout
        plt.tight_layout()
        
        # Save to buffer
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
        buffer.seek(0)
        plt.close(fig)
        
        return buffer
    
    def generate_daily_trend_chart(
        self,
        daily_data: List[Dict[str, Any]]
    ) -> BytesIO:
        """
        Generate line chart for daily consumption trend.
        
        Args:
            daily_data: List of daily consumption dicts
        
        Returns:
            BytesIO buffer with PNG image
        """
        # Extract data
        dates = [datetime.strptime(d['date'], '%Y-%m-%d') for d in daily_data]
        kwh = [d['kwh'] for d in daily_data]
        
        # Create figure (smaller size)
        fig, ax = plt.subplots(figsize=(6, 2.5))
        
        # Line chart
        ax.plot(dates, kwh, color=self.color_teal, linewidth=2, marker='o', markersize=4)
        
        # Fill area under curve
        ax.fill_between(dates, kwh, alpha=0.2, color=self.color_teal)
        
        # Customize
        ax.set_xlabel('Date', fontsize=10, fontweight='bold')
        ax.set_ylabel('Energy Consumption (kWh)', fontsize=10, fontweight='bold')
        ax.set_title('Daily Energy Consumption Trend', fontsize=12, fontweight='bold', color=self.color_navy)
        ax.grid(alpha=0.3)
        
        # Format x-axis
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, len(dates)//10)))
        plt.xticks(rotation=45, ha='right')
        
        # Tight layout
        plt.tight_layout()
        
        # Save to buffer
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
        buffer.seek(0)
        plt.close(fig)
        
        return buffer
    
    def cleanup(self):
        """Close all matplotlib figures."""
        plt.close('all')
