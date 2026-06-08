"""
KPI Card Component
Displays key performance indicators with value, trend, and visual styling.
"""
from typing import Optional, Literal
from dataclasses import dataclass


@dataclass
class KPICard:
    """
    KPI Card component for displaying performance metrics.
    
    Usage:
        card = KPICard(
            title="Total Energy Consumption",
            value=12345.67,
            unit="kWh",
            trend=5.2,
            status="good"
        )
        html = card.render()
    """
    
    title: str
    value: float
    unit: str = ""
    trend: Optional[float] = None  # Percentage change (positive or negative)
    trend_label: Optional[str] = None  # e.g., "vs last month"
    status: Literal["critical", "warning", "good", "excellent", "neutral"] = "neutral"
    subtitle: Optional[str] = None
    icon: Optional[str] = None  # Icon name or emoji
    target: Optional[float] = None  # Target value for progress calculation
    
    def get_status_color(self) -> str:
        """Get border color based on status."""
        colors = {
            "critical": "#e53e3e",
            "warning": "#ed8936",
            "good": "#48bb78",
            "excellent": "#00A8E8",
            "neutral": "#718096"
        }
        return colors.get(self.status, colors["neutral"])
    
    def get_trend_class(self) -> str:
        """Get CSS class for trend styling."""
        if self.trend is None:
            return "neutral"
        return "positive" if self.trend >= 0 else "negative"
    
    def get_trend_arrow(self) -> str:
        """Get arrow symbol for trend."""
        if self.trend is None:
            return "•"
        return "▲" if self.trend >= 0 else "▼"
    
    def get_progress_percentage(self) -> Optional[float]:
        """Calculate progress towards target."""
        if self.target is None or self.target == 0:
            return None
        return min(100, (self.value / self.target) * 100)
    
    def format_value(self) -> str:
        """Format the value with thousands separator."""
        if isinstance(self.value, float):
            if self.value >= 1000:
                return f"{self.value:,.1f}"
            else:
                return f"{self.value:.2f}"
        return str(self.value)
    
    def format_trend(self) -> str:
        """Format trend percentage."""
        if self.trend is None:
            return ""
        sign = "+" if self.trend > 0 else ""
        return f"{sign}{self.trend:.1f}%"
    
    def render(self) -> str:
        """
        Render KPI card as HTML string.
        
        Returns:
            HTML string for the KPI card
        """
        status_color = self.get_status_color()
        trend_class = self.get_trend_class()
        trend_arrow = self.get_trend_arrow()
        formatted_value = self.format_value()
        formatted_trend = self.format_trend()
        progress = self.get_progress_percentage()
        
        # Build HTML
        html_parts = [
            f'<div class="kpi-card no-break" style="border-left-color: {status_color};">',
            '  <div class="kpi-card-header">',
        ]
        
        # Icon (if provided)
        if self.icon:
            html_parts.append(f'    <span class="kpi-card-icon" style="font-size: 1.5rem; margin-right: 0.5rem;">{self.icon}</span>')
        
        # Title
        html_parts.append(f'    <h3 class="kpi-card-title">{self.title}</h3>')
        
        html_parts.append('  </div>')
        
        # Subtitle (if provided)
        if self.subtitle:
            html_parts.append(f'  <p class="kpi-card-subtitle" style="font-size: 0.75rem; color: #718096; margin: 0.25rem 0;">{self.subtitle}</p>')
        
        # Value and unit
        html_parts.extend([
            '  <div class="kpi-card-content">',
            f'    <span class="kpi-card-value">{formatted_value}</span>',
        ])
        
        if self.unit:
            html_parts.append(f'    <span class="kpi-card-unit">{self.unit}</span>')
        
        html_parts.append('  </div>')
        
        # Trend indicator (if provided)
        if self.trend is not None:
            trend_label = self.trend_label or ""
            html_parts.extend([
                f'  <div class="kpi-card-trend {trend_class}">',
                f'    <span class="trend-arrow">{trend_arrow}</span>',
                f'    <span class="trend-value">{formatted_trend}</span>',
                f'    <span class="trend-label" style="margin-left: 0.25rem; color: #718096;">{trend_label}</span>',
                '  </div>'
            ])
        
        # Progress bar (if target provided)
        if progress is not None:
            html_parts.extend([
                '  <div class="progress-bar" style="margin-top: 0.75rem;">',
                f'    <div class="progress-bar-fill" style="width: {progress}%; background-color: {status_color};"></div>',
                '  </div>',
                f'  <p style="font-size: 0.75rem; color: #718096; margin-top: 0.25rem;">{progress:.1f}% of target ({self.target} {self.unit})</p>'
            ])
        
        html_parts.append('</div>')
        
        return '\n'.join(html_parts)


def create_kpi_grid(cards: list[KPICard], columns: int = 3) -> str:
    """
    Create a grid layout of multiple KPI cards.
    
    Args:
        cards: List of KPICard instances
        columns: Number of columns in grid (2, 3, or 4)
        
    Returns:
        HTML string with grid layout
    """
    grid_class = f"print-grid-{columns}" if columns <= 3 else "print-grid-2"
    
    html_parts = [
        f'<div class="{grid_class} no-break" style="gap: 1rem; margin: 1rem 0;">',
    ]
    
    for card in cards:
        html_parts.append(card.render())
    
    html_parts.append('</div>')
    
    return '\n'.join(html_parts)
