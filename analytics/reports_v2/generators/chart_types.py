"""
Gauge Chart Generator
Creates KPI gauge visualizations with color-coded zones.
"""
import plotly.graph_objects as go
from typing import Optional, Dict, List
from .chart_factory import ChartFactory


class GaugeChart(ChartFactory):
    """Generate gauge charts for KPI visualization."""
    
    def create(
        self,
        value: float,
        title: str,
        max_value: float = 100,
        unit: str = "%",
        thresholds: Optional[Dict[str, float]] = None,
        show_target: bool = False,
        target_value: Optional[float] = None,
        height: int = 300
    ) -> go.Figure:
        """
        Create a gauge chart.
        
        Args:
            value: Current value to display
            title: Chart title
            max_value: Maximum value on gauge (default 100)
            unit: Unit label (default "%")
            thresholds: Dict with 'critical', 'warning', 'good', 'excellent' values
            show_target: Whether to show target line
            target_value: Target value (if show_target=True)
            height: Chart height in pixels
            
        Returns:
            Plotly figure
        """
        # Default thresholds
        if thresholds is None:
            thresholds = {
                'critical': max_value * 0.5,
                'warning': max_value * 0.7,
                'good': max_value * 0.85,
                'excellent': max_value * 0.95
            }
        
        # Determine gauge color based on value
        if value >= thresholds.get('excellent', max_value * 0.95):
            gauge_color = self.COLORS['excellent']
            status = "Excellent"
        elif value >= thresholds.get('good', max_value * 0.85):
            gauge_color = self.COLORS['good']
            status = "Good"
        elif value >= thresholds.get('warning', max_value * 0.7):
            gauge_color = self.COLORS['warning']
            status = "Warning"
        else:
            gauge_color = self.COLORS['danger']
            status = "Critical"
        
        # Create gauge
        fig = go.Figure(go.Indicator(
            mode="gauge+number+delta" if show_target and target_value else "gauge+number",
            value=value,
            domain={'x': [0.05, 0.95], 'y': [0, 1]},
            title={'text': f"{title}<br><span style='font-size:0.8em;color:{self.COLORS['text_light']}'>{status}</span>"},
            number={'suffix': f" {unit}", 'font': {'size': 40}},
            delta={'reference': target_value if show_target else None, 'relative': False} if show_target else None,
            gauge={
                'axis': {
                    'range': [0, max_value],
                    'tickwidth': 1,
                    'tickcolor': self.COLORS['text_light']
                },
                'bar': {'color': gauge_color, 'thickness': 0.75},
                'bgcolor': self.COLORS['background'],
                'borderwidth': 2,
                'bordercolor': self.COLORS['grid'],
                'steps': [
                    {'range': [0, thresholds.get('critical', max_value * 0.5)], 
                     'color': 'rgba(229, 62, 62, 0.15)'},
                    {'range': [thresholds.get('critical', max_value * 0.5), thresholds.get('warning', max_value * 0.7)], 
                     'color': 'rgba(237, 137, 54, 0.15)'},
                    {'range': [thresholds.get('warning', max_value * 0.7), thresholds.get('good', max_value * 0.85)], 
                     'color': 'rgba(72, 187, 120, 0.15)'},
                    {'range': [thresholds.get('good', max_value * 0.85), max_value], 
                     'color': 'rgba(0, 168, 232, 0.15)'}
                ],
                'threshold': {
                    'line': {'color': self.COLORS['secondary'], 'width': 3},
                    'thickness': 0.75,
                    'value': target_value if show_target and target_value else value
                } if show_target else None
            }
        ))
        
        # Apply layout
        fig = self._apply_layout(
            fig,
            height=height,
            margin={'l': 20, 'r': 20, 't': 80, 'b': 20}
        )
        
        return fig


class WaterfallChart(ChartFactory):
    """Generate waterfall charts for variance analysis."""
    
    def create(
        self,
        categories: List[str],
        values: List[float],
        title: str = "Variance Analysis",
        start_value: Optional[float] = None,
        end_label: str = "Final",
        height: int = 400,
        show_total: bool = True
    ) -> go.Figure:
        """
        Create a waterfall chart.
        
        Args:
            categories: List of category names
            values: List of values (positive = increase, negative = decrease)
            title: Chart title
            start_value: Starting value (if None, calculated from first value)
            end_label: Label for final total
            height: Chart height in pixels
            show_total: Whether to show final total bar
            
        Returns:
            Plotly figure
        """
        # Calculate measure types
        measures = ["relative"] * len(categories)
        
        if show_total:
            categories = categories + [end_label]
            values = values + [sum(values)]
            measures = measures + ["total"]
        
        # Create colors (green for positive, red for negative, blue for total)
        colors = []
        for i, val in enumerate(values[:-1] if show_total else values):
            if val >= 0:
                colors.append(self.COLORS['good'])
            else:
                colors.append(self.COLORS['danger'])
        
        if show_total:
            colors.append(self.COLORS['primary'])
        
        # Create waterfall
        fig = go.Figure(go.Waterfall(
            name="",
            orientation="v",
            measure=measures,
            x=categories,
            y=values,
            text=[f"{v:+,.0f}" if v != 0 else "0" for v in values],
            textposition="outside",
            connector={"line": {"color": self.COLORS['text_light'], "width": 2, "dash": "dot"}},
            decreasing={"marker": {"color": self.COLORS['danger']}},
            increasing={"marker": {"color": self.COLORS['good']}},
            totals={"marker": {"color": self.COLORS['primary']}}
        ))
        
        # Apply layout
        fig = self._apply_layout(
            fig,
            title=title,
            yaxis_title="kWh",
            height=height,
            showlegend=False
        )
        
        return fig


class HeatmapChart(ChartFactory):
    """Generate heatmaps for pattern visualization."""
    
    def create(
        self,
        z_values: List[List[float]],
        x_labels: List[str],
        y_labels: List[str],
        title: str = "Consumption Pattern",
        colorscale: str = "Blues",
        show_values: bool = True,
        height: int = 400
    ) -> go.Figure:
        """
        Create a heatmap chart.
        
        Args:
            z_values: 2D array of values [rows][columns]
            x_labels: Column labels
            y_labels: Row labels
            title: Chart title
            colorscale: Plotly colorscale name
            show_values: Whether to show values in cells
            height: Chart height in pixels
            
        Returns:
            Plotly figure
        """
        fig = go.Figure(go.Heatmap(
            z=z_values,
            x=x_labels,
            y=y_labels,
            colorscale=colorscale,
            text=[[f"{val:.1f}" for val in row] for row in z_values] if show_values else None,
            texttemplate="%{text}" if show_values else None,
            textfont={"size": 10},
            colorbar=dict(
                title=dict(text="kWh"),
                tickmode="linear"
            )
        ))
        
        fig = self._apply_layout(
            fig,
            title=title,
            xaxis_title="Hour",
            yaxis_title="Day",
            height=height
        )
        
        return fig


class BarChart(ChartFactory):
    """Generate horizontal and vertical bar charts."""
    
    def create_horizontal(
        self,
        categories: List[str],
        values: List[float],
        title: str = "Machine Ranking",
        color_by_value: bool = True,
        height: int = 400
    ) -> go.Figure:
        """
        Create horizontal bar chart.
        
        Args:
            categories: Category names
            values: Values for each category
            title: Chart title
            color_by_value: Color bars by value magnitude
            height: Chart height in pixels
            
        Returns:
            Plotly figure
        """
        # Determine colors
        if color_by_value:
            max_val = max(values) if values else 1
            colors = [self.get_status_color(v / max_val * 100, {'excellent': 80, 'good': 60, 'warning': 40}) 
                     for v in values]
        else:
            colors = [self.COLORS['primary']] * len(values)
        
        fig = go.Figure(go.Bar(
            y=categories,
            x=values,
            orientation='h',
            marker=dict(color=colors),
            text=[f"{v:,.0f}" for v in values],
            textposition='outside',
            textfont=dict(size=10)
        ))
        
        # Adjust layout for better bar visibility
        max_val = max(values) if values else 1
        x_range = [0, max_val * 1.15]  # Add 15% padding for text labels
        
        fig = self._apply_layout(
            fig,
            title=title,
            xaxis_title="kWh",
            height=height,
            showlegend=False,
            xaxis={'range': x_range, 'gridcolor': '#e2e8f0', 'linecolor': '#cbd5e0', 'showgrid': True, 'zeroline': False}
        )
        
        return fig


class LineChart(ChartFactory):
    """Generate line charts for trend analysis."""
    
    def create(
        self,
        x_values: List,
        y_series: Dict[str, List[float]],
        title: str = "Consumption Trend",
        fill_area: bool = False,
        height: int = 400
    ) -> go.Figure:
        """
        Create multi-series line chart.
        
        Args:
            x_values: X-axis values (dates, hours, etc.)
            y_series: Dict of {series_name: values}
            title: Chart title
            fill_area: Whether to fill area under line
            height: Chart height in pixels
            
        Returns:
            Plotly figure
        """
        fig = go.Figure()
        
        colors = self._get_color_sequence(len(y_series))
        
        for idx, (name, values) in enumerate(y_series.items()):
            fig.add_trace(go.Scatter(
                x=x_values,
                y=values,
                mode='lines+markers',
                name=name,
                line=dict(color=colors[idx], width=2),
                marker=dict(size=6),
                fill='tozeroy' if fill_area else None
            ))
        
        fig = self._apply_layout(
            fig,
            title=title,
            xaxis_title="Time",
            yaxis_title="kWh",
            height=height
        )
        
        return fig


class SparklineChart(ChartFactory):
    """Generate minimal sparkline charts."""
    
    def create(
        self,
        values: List[float],
        width: int = 120,
        height: int = 40,
        color: Optional[str] = None
    ) -> go.Figure:
        """
        Create a sparkline chart (minimal trend indicator).
        
        Args:
            values: Data points
            width: Chart width in pixels
            height: Chart height in pixels
            color: Line color (default: primary)
            
        Returns:
            Plotly figure
        """
        fig = go.Figure(go.Scatter(
            y=values,
            mode='lines',
            line=dict(color=color or self.COLORS['primary'], width=1.5),
            fill='tozeroy',
            fillcolor=f"rgba(0, 168, 232, 0.2)"
        ))
        
        fig.update_layout(
            width=width,
            height=height,
            margin={'l': 0, 'r': 0, 't': 0, 'b': 0},
            paper_bgcolor='white',
            plot_bgcolor='white',
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            showlegend=False
        )
        
        return fig


class SankeyChart(ChartFactory):
    """Generate Sankey diagrams for flow visualization."""
    
    def create(
        self,
        sources: List[int],
        targets: List[int],
        values: List[float],
        labels: List[str],
        title: str = "Energy Flow",
        height: int = 500
    ) -> go.Figure:
        """
        Create a Sankey diagram.
        
        Args:
            sources: List of source node indices
            targets: List of target node indices
            values: Flow values
            labels: Node labels
            title: Chart title
            height: Chart height in pixels
            
        Returns:
            Plotly figure
        """
        # Generate colors for nodes
        node_colors = self._get_color_sequence(len(labels))
        
        # Create link colors (semi-transparent versions of source colors)
        link_colors = [f"rgba{tuple(list(bytes.fromhex(node_colors[s].lstrip('#'))) + [0.4])}" 
                      for s in sources]
        
        fig = go.Figure(go.Sankey(
            node=dict(
                pad=15,
                thickness=20,
                line=dict(color="white", width=2),
                label=labels,
                color=node_colors
            ),
            link=dict(
                source=sources,
                target=targets,
                value=values,
                color=link_colors
            )
        ))
        
        fig = self._apply_layout(
            fig,
            title=title,
            height=height,
            margin={'l': 20, 'r': 20, 't': 60, 'b': 20}
        )
        
        return fig


class ComboChart(ChartFactory):
    """Bar + line combo chart with dual y-axes"""
    
    def create(self,
               categories: list,
               bar_values: list,
               line_values: list,
               title: str = "Combo Chart",
               bar_name: str = "Primary",
               line_name: str = "Secondary",
               bar_color: str = None,
               line_color: str = None,
               yaxis1_title: str = "Primary Axis",
               yaxis2_title: str = "Secondary Axis",
               height: int = 400) -> go.Figure:
        """
        Create bar + line combo chart with dual y-axes
        
        Args:
            categories: X-axis labels
            bar_values: Bar chart data
            line_values: Line chart data
            title: Chart title
            bar_name: Legend name for bars
            line_name: Legend name for line
            bar_color: Bar color (default: navy)
            line_color: Line color (default: teal)
            yaxis1_title: Left y-axis title
            yaxis2_title: Right y-axis title
            height: Chart height in pixels
            
        Returns:
            Plotly figure with dual y-axes
        """
        bar_color = bar_color or self.COLORS['secondary']  # Navy
        line_color = line_color or self.COLORS['primary']  # Teal
        
        fig = go.Figure()
        
        # Add bar trace (primary y-axis)
        fig.add_trace(go.Bar(
            x=categories,
            y=bar_values,
            name=bar_name,
            marker_color=bar_color,
            yaxis='y1'
        ))
        
        # Add line trace (secondary y-axis)
        fig.add_trace(go.Scatter(
            x=categories,
            y=line_values,
            name=line_name,
            mode='lines+markers',
            line=dict(color=line_color, width=3),
            marker=dict(size=8, color=line_color),
            yaxis='y2'
        ))
        
        # Apply base layout
        fig = self._apply_layout(
            fig,
            title=title,
            xaxis_title="",
            yaxis_title=yaxis1_title,
            height=height
        )
        
        # Configure dual y-axes
        fig.update_layout(
            yaxis=dict(
                title=yaxis1_title,
                side='left',
                showgrid=True
            ),
            yaxis2=dict(
                title=yaxis2_title,
                side='right',
                overlaying='y',
                showgrid=False
            ),
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.02,
                xanchor='center',
                x=0.5
            )
        )
        
        return fig
