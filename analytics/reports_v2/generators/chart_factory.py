"""
Chart Factory - Plotly-based chart generation for EnMS Reports
Provides consistent, high-quality visualizations with brand theming.
"""
import plotly.graph_objects as go
import plotly.express as px
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class ChartFactory:
    """
    Factory class for creating branded, print-optimized Plotly charts.
    
    All charts use consistent:
    - Color palette (EnMS brand colors)
    - Typography (Inter font)
    - Layout settings (margins, sizing)
    - Export settings (300 DPI, PNG)
    """
    
    # EnMS Brand Color Palette
    COLORS = {
        'primary': '#00A8E8',      # Teal - Main brand color
        'secondary': '#1a365d',    # Navy - Headers, text
        'accent': '#FFA500',       # Orange - Highlights
        'success': '#48bb78',      # Green - Positive trends
        'warning': '#ed8936',      # Orange - Warnings
        'danger': '#e53e3e',       # Red - Critical items
        'excellent': '#00A8E8',    # Teal - Excellent performance
        'neutral': '#718096',      # Gray - Neutral items
        
        # Chart series colors (8-color palette)
        'chart_1': '#00A8E8',      # Teal
        'chart_2': '#FFA500',      # Orange
        'chart_3': '#32CD32',      # Lime Green
        'chart_4': '#9370DB',      # Purple
        'chart_5': '#FF6B6B',      # Coral
        'chart_6': '#4ECDC4',      # Turquoise
        'chart_7': '#FFD93D',      # Yellow
        'chart_8': '#6C5CE7',      # Indigo
        
        # Status colors
        'critical': '#e53e3e',
        'good': '#48bb78',
        'background': '#ffffff',
        'grid': '#e2e8f0',
        'text_dark': '#2d3748',
        'text_light': '#718096'
    }
    
    # Default layout settings for print
    DEFAULT_LAYOUT = {
        'font': {
            'family': 'Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
            'size': 11,
            'color': '#2d3748'
        },
        'paper_bgcolor': 'white',
        'plot_bgcolor': 'white',
        'margin': {'l': 60, 'r': 40, 't': 60, 'b': 60},
        'showlegend': True,
        'legend': {
            'orientation': 'h',
            'yanchor': 'bottom',
            'y': -0.15,
            'xanchor': 'center',
            'x': 0.5,
            'font': {'size': 10}
        },
        'xaxis': {
            'gridcolor': '#e2e8f0',
            'linecolor': '#cbd5e0',
            'showgrid': True,
            'zeroline': False
        },
        'yaxis': {
            'gridcolor': '#e2e8f0',
            'linecolor': '#cbd5e0',
            'showgrid': True,
            'zeroline': False
        }
    }
    
    # Export settings for high-quality PDF
    EXPORT_CONFIG = {
        'width': 800,
        'height': 400,
        'scale': 3,  # 300 DPI equivalent (96 DPI × 3)
        'format': 'png'
    }
    
    def __init__(self):
        """Initialize chart factory with default settings."""
        self.default_width = 800
        self.default_height = 400
    
    def _get_color_sequence(self, n: int) -> List[str]:
        """
        Get color sequence for n series.
        
        Args:
            n: Number of colors needed
            
        Returns:
            List of hex color codes
        """
        base_colors = [
            self.COLORS['chart_1'], self.COLORS['chart_2'], self.COLORS['chart_3'],
            self.COLORS['chart_4'], self.COLORS['chart_5'], self.COLORS['chart_6'],
            self.COLORS['chart_7'], self.COLORS['chart_8']
        ]
        
        # Repeat colors if needed
        return (base_colors * (n // len(base_colors) + 1))[:n]
    
    def _apply_layout(
        self,
        fig: go.Figure,
        title: str = "",
        xaxis_title: str = "",
        yaxis_title: str = "",
        height: Optional[int] = None,
        **kwargs
    ) -> go.Figure:
        """
        Apply consistent layout to figure.
        
        Args:
            fig: Plotly figure
            title: Chart title
            xaxis_title: X-axis label
            yaxis_title: Y-axis label
            height: Chart height in pixels
            **kwargs: Additional layout parameters
            
        Returns:
            Updated figure
        """
        layout_update = {**self.DEFAULT_LAYOUT}
        
        if title:
            layout_update['title'] = {
                'text': title,
                'font': {'size': 14, 'color': self.COLORS['secondary'], 'family': layout_update['font']['family']},
                'x': 0.5,
                'xanchor': 'center'
            }
        
        if xaxis_title:
            layout_update['xaxis']['title'] = xaxis_title
        
        if yaxis_title:
            layout_update['yaxis']['title'] = yaxis_title
        
        if height:
            layout_update['height'] = height
        
        # Merge custom kwargs
        layout_update.update(kwargs)
        
        fig.update_layout(**layout_update)
        return fig
    
    def export_to_html(
        self,
        fig: go.Figure,
        include_plotlyjs: str = 'cdn',
        config: Optional[Dict] = None
    ) -> str:
        """
        Export figure to HTML string for embedding.
        
        Args:
            fig: Plotly figure
            include_plotlyjs: How to include plotly.js ('cdn', False, or path)
            config: Plot config options
            
        Returns:
            HTML string
        """
        default_config = {
            'displayModeBar': False,
            'staticPlot': True  # No interactivity for PDF
        }
        
        if config:
            default_config.update(config)
        
        return fig.to_html(
            include_plotlyjs=include_plotlyjs,
            config=default_config,
            div_id=None,
            full_html=False
        )
    
    def export_to_png(
        self,
        fig: go.Figure,
        output_path: str,
        width: Optional[int] = None,
        height: Optional[int] = None
    ) -> Path:
        """
        Export figure to high-quality PNG (300 DPI equivalent).
        
        Args:
            fig: Plotly figure
            output_path: Path to save PNG
            width: Image width in pixels
            height: Image height in pixels
            
        Returns:
            Path to saved PNG file
        """
        export_config = {**self.EXPORT_CONFIG}
        
        if width:
            export_config['width'] = width
        if height:
            export_config['height'] = height
        
        fig.write_image(output_path, **export_config)
        
        output = Path(output_path)
        logger.info(f"Chart exported to {output_path} ({output.stat().st_size / 1024:.1f} KB)")
        
        return output
    
    def get_status_color(self, value: float, thresholds: Dict[str, float]) -> str:
        """
        Get status color based on value and thresholds.
        
        Args:
            value: Value to evaluate
            thresholds: Dict with 'excellent', 'good', 'warning' thresholds
            
        Returns:
            Hex color code
        """
        if value >= thresholds.get('excellent', 90):
            return self.COLORS['excellent']
        elif value >= thresholds.get('good', 70):
            return self.COLORS['good']
        elif value >= thresholds.get('warning', 50):
            return self.COLORS['warning']
        else:
            return self.COLORS['danger']
