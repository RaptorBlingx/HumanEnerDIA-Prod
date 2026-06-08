"""
HTML Generator - Jinja2-based template rendering
Renders HTML from templates with data context.
"""
from pathlib import Path
from typing import Dict, Any, Optional
from jinja2 import Environment, FileSystemLoader, select_autoescape
import logging

logger = logging.getLogger(__name__)


class HTMLGenerator:
    """
    Generate HTML from Jinja2 templates.
    
    Features:
    - Template inheritance and composition
    - Auto-escaping for security
    - Custom filters and functions
    - Template caching
    """
    
    def __init__(self, templates_dir: Optional[str] = None):
        """
        Initialize HTML generator.
        
        Args:
            templates_dir: Path to templates directory. 
                         Defaults to reports_v2/templates/
        """
        if templates_dir is None:
            # Default to reports_v2/templates/ relative to this file
            reports_v2_dir = Path(__file__).parent.parent
            templates_dir = str(reports_v2_dir / 'templates')
        
        self.templates_dir = Path(templates_dir)
        
        if not self.templates_dir.exists():
            raise FileNotFoundError(f"Templates directory not found: {templates_dir}")
        
        # Initialize Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        
        # Register custom filters
        self._register_filters()
        
        logger.info(f"HTML Generator initialized with templates from: {self.templates_dir}")
    
    def _register_filters(self):
        """Register custom Jinja2 filters for data formatting."""
        
        def format_number(value, decimals=2):
            """Format number with thousands separator."""
            if value is None:
                return "N/A"
            try:
                return f"{float(value):,.{decimals}f}"
            except (ValueError, TypeError):
                return str(value)
        
        def format_percent(value, decimals=1):
            """Format number as percentage."""
            if value is None:
                return "N/A"
            try:
                return f"{float(value):.{decimals}f}%"
            except (ValueError, TypeError):
                return str(value)
        
        def format_energy(value, unit='kWh'):
            """Format energy value with unit."""
            if value is None:
                return "N/A"
            try:
                return f"{float(value):,.2f} {unit}"
            except (ValueError, TypeError):
                return str(value)
        
        def status_class(value):
            """Return CSS class based on status value."""
            status_map = {
                'critical': 'text-red-600 bg-red-50',
                'warning': 'text-orange-600 bg-orange-50',
                'good': 'text-green-600 bg-green-50',
                'excellent': 'text-teal-600 bg-teal-50',
            }
            return status_map.get(str(value).lower(), 'text-gray-600 bg-gray-50')
        
        def safe_round(value, precision=2):
            """Safely round a value, handling None and undefined."""
            if value is None or value == '' or str(value).lower() == 'undefined':
                return 0
            try:
                return round(float(value), precision)
            except (ValueError, TypeError, AttributeError):
                return 0
        
        # Register filters
        self.env.filters['format_number'] = format_number
        self.env.filters['format_percent'] = format_percent
        self.env.filters['format_energy'] = format_energy
        self.env.filters['status_class'] = status_class
        self.env.filters['round'] = safe_round  # Override default round filter
    
    def render(self, template_name: str, context: Dict[str, Any]) -> str:
        """
        Render template with context data.
        
        Args:
            template_name: Name of template file (e.g., 'cover/title_page.html')
            context: Dictionary of data to pass to template
            
        Returns:
            Rendered HTML string
            
        Raises:
            TemplateNotFound: If template doesn't exist
        """
        try:
            template = self.env.get_template(template_name)
            html = template.render(**context)
            
            logger.debug(f"Rendered template: {template_name}")
            return html
            
        except Exception as e:
            logger.error(f"Failed to render template '{template_name}': {str(e)}")
            raise
    
    def render_string(self, template_string: str, context: Dict[str, Any]) -> str:
        """
        Render HTML from string template (not file).
        
        Args:
            template_string: Jinja2 template as string
            context: Dictionary of data to pass to template
            
        Returns:
            Rendered HTML string
        """
        try:
            template = self.env.from_string(template_string)
            return template.render(**context)
        except Exception as e:
            logger.error(f"Failed to render template string: {str(e)}")
            raise


# Convenience function for quick rendering
def render_template(template_name: str, context: Dict[str, Any], templates_dir: Optional[str] = None) -> str:
    """
    Quick template rendering helper function.
    
    Usage:
        from reports_v2.generators.html_generator import render_template
        html = render_template('cover/title_page.html', {'title': 'My Report'})
    """
    generator = HTMLGenerator(templates_dir)
    return generator.render(template_name, context)
