"""
EnMS Report Styles - Industrial Theme
======================================
ReportLab styles for PDF generation with APlus Engineering branding.
"""

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import TableStyle

# ============================================================================
# COLOR PALETTE - Industrial Theme
# ============================================================================

# Primary Colors
COLOR_NAVY = colors.HexColor('#1a365d')           # Dark Navy (headers)
COLOR_TEAL = colors.HexColor('#00A8E8')           # Industrial Teal (accent)
COLOR_GRAY_DARK = colors.HexColor('#374151')      # Dark gray (text)
COLOR_GRAY_LIGHT = colors.HexColor('#f3f4f6')     # Light gray (backgrounds)
COLOR_WHITE = colors.white

# Status Colors
COLOR_SUCCESS = colors.HexColor('#059669')        # Green
COLOR_WARNING = colors.HexColor('#d97706')        # Amber
COLOR_DANGER = colors.HexColor('#dc2626')         # Red
COLOR_INFO = colors.HexColor('#2563eb')           # Blue

# ============================================================================
# FONTS
# ============================================================================

FONT_REGULAR = 'Helvetica'
FONT_BOLD = 'Helvetica-Bold'
FONT_ITALIC = 'Helvetica-Oblique'

# Font Sizes
FONT_SIZE_TITLE = 16
FONT_SIZE_HEADING = 12
FONT_SIZE_SUBHEADING = 10
FONT_SIZE_BODY = 9
FONT_SIZE_SMALL = 8

# ============================================================================
# PARAGRAPH STYLES
# ============================================================================

def get_custom_styles():
    """Get custom paragraph styles for reports."""
    styles = getSampleStyleSheet()
    
    # Title Style
    styles.add(ParagraphStyle(
        name='ReportTitle',
        parent=styles['Heading1'],
        fontSize=FONT_SIZE_TITLE,
        textColor=COLOR_NAVY,
        fontName=FONT_BOLD,
        alignment=TA_CENTER,
        spaceAfter=8,  # Balanced
        spaceBefore=0
    ))
    
    # Section Heading
    styles.add(ParagraphStyle(
        name='SectionHeading',
        parent=styles['Heading2'],
        fontSize=FONT_SIZE_HEADING,
        textColor=COLOR_NAVY,
        fontName=FONT_BOLD,
        alignment=TA_LEFT,
        spaceAfter=6,  # Balanced
        spaceBefore=10,  # Balanced
        borderWidth=0,
        borderPadding=0,
        borderColor=COLOR_NAVY,
        borderRadius=0
    ))
    
    # Body Text
    styles.add(ParagraphStyle(
        name='ReportBody',
        parent=styles['Normal'],
        fontSize=FONT_SIZE_BODY,
        textColor=COLOR_GRAY_DARK,
        fontName=FONT_REGULAR,
        alignment=TA_LEFT,
        spaceAfter=5,  # Balanced
        leading=11
    ))
    
    # Small Text (footer)
    styles.add(ParagraphStyle(
        name='SmallText',
        parent=styles['Normal'],
        fontSize=FONT_SIZE_SMALL,
        textColor=colors.gray,
        fontName=FONT_REGULAR,
        alignment=TA_CENTER,
        spaceAfter=0
    ))
    
    # Bullet List
    styles.add(ParagraphStyle(
        name='BulletItem',
        parent=styles['Normal'],
        fontSize=FONT_SIZE_BODY,
        textColor=COLOR_GRAY_DARK,
        fontName=FONT_REGULAR,
        alignment=TA_LEFT,
        leftIndent=20,
        bulletIndent=10,
        spaceAfter=3  # Balanced
    ))
    
    return styles

# ============================================================================
# TABLE STYLES
# ============================================================================

def get_table_style():
    """Standard table style for data tables."""
    return TableStyle([
        # Header row
        ('BACKGROUND', (0, 0), (-1, 0), COLOR_NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), COLOR_WHITE),
        ('FONTNAME', (0, 0), (-1, 0), FONT_BOLD),
        ('FONTSIZE', (0, 0), (-1, 0), FONT_SIZE_BODY),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 5),  # Reduced from 8
        ('TOPPADDING', (0, 0), (-1, 0), 5),  # Reduced from 8
        
        # Data rows
        ('BACKGROUND', (0, 1), (-1, -1), COLOR_WHITE),
        ('TEXTCOLOR', (0, 1), (-1, -1), COLOR_GRAY_DARK),
        ('FONTNAME', (0, 1), (-1, -1), FONT_REGULAR),
        ('FONTSIZE', (0, 1), (-1, -1), FONT_SIZE_BODY),
        ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),  # Reduced from 6
        ('TOPPADDING', (0, 1), (-1, -1), 4),  # Reduced from 6,
        
        # Grid
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
        ('LINEBELOW', (0, 0), (-1, 0), 2, COLOR_NAVY),
        
        # Alternating row colors
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [COLOR_WHITE, COLOR_GRAY_LIGHT])
    ])

def get_summary_table_style():
    """Table style for summary/KPI tables."""
    return TableStyle([
        # Header row
        ('BACKGROUND', (0, 0), (-1, 0), COLOR_TEAL),
        ('TEXTCOLOR', (0, 0), (-1, 0), COLOR_WHITE),
        ('FONTNAME', (0, 0), (-1, 0), FONT_BOLD),
        ('FONTSIZE', (0, 0), (-1, 0), FONT_SIZE_BODY),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 5),  # Reduced from 8
        ('TOPPADDING', (0, 0), (-1, 0), 5),  # Reduced from 8
        
        # Data rows
        ('BACKGROUND', (0, 1), (-1, -1), COLOR_WHITE),
        ('TEXTCOLOR', (0, 1), (-1, -1), COLOR_GRAY_DARK),
        ('FONTNAME', (0, 1), (-1, -1), FONT_REGULAR),
        ('FONTSIZE', (0, 1), (-1, -1), FONT_SIZE_BODY),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),  # Center numeric values
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),     # Left align labels
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),  # Reduced from 6
        ('TOPPADDING', (0, 1), (-1, -1), 4),  # Reduced from 6,
        
        # Grid
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
        ('LINEBELOW', (0, 0), (-1, 0), 2, COLOR_TEAL),
    ])

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_status_color(status: str) -> colors.Color:
    """Get color based on status value."""
    status_lower = status.lower()
    if 'good' in status_lower or 'pass' in status_lower or '✓' in status_lower:
        return COLOR_SUCCESS
    elif 'warning' in status_lower or 'caution' in status_lower:
        return COLOR_WARNING
    elif 'critical' in status_lower or 'fail' in status_lower or 'bad' in status_lower:
        return COLOR_DANGER
    else:
        return COLOR_GRAY_DARK

def format_number(value: float, decimals: int = 2) -> str:
    """Format number with thousand separators."""
    if value is None:
        return "N/A"
    return f"{value:,.{decimals}f}"
