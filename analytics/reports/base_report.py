"""
EnMS Base Report Class
=======================
Base class for PDF report generation using ReportLab.
Handles page setup, headers, footers, and common layout elements.
"""

import os
from datetime import datetime
from typing import List, Any
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, PageBreak,
    Image as RLImage, KeepTogether
)
from reportlab.lib.styles import ParagraphStyle

from reports.styles import (
    get_custom_styles, get_table_style, get_summary_table_style,
    COLOR_NAVY, COLOR_GRAY_DARK, COLOR_WHITE, COLOR_TEAL,
    FONT_BOLD, FONT_REGULAR, FONT_SIZE_SMALL, FONT_SIZE_BODY
)


class BaseReport:
    """
    Base class for all PDF reports.
    
    Provides:
    - Page setup (A4, margins)
    - Header with logo
    - Footer with page numbers
    - Common layout methods
    """
    
    def __init__(
        self,
        title: str,
        subtitle: str = "",
        filename: str = "report.pdf"
    ):
        """
        Initialize base report.
        
        Args:
            title: Report title
            subtitle: Report subtitle (optional)
            filename: Output filename
        """
        self.title = title
        self.subtitle = subtitle
        self.filename = filename
        
        # Page setup
        self.pagesize = A4
        self.width, self.height = self.pagesize
        
        # Margins
        self.margin_left = 20 * mm
        self.margin_right = 20 * mm
        self.margin_top = 20 * mm  # Slightly reduced from 25
        self.margin_bottom = 18 * mm  # Slightly reduced from 20
        
        # Content width
        self.content_width = self.width - self.margin_left - self.margin_right
        
        # Styles
        self.styles = get_custom_styles()
        
        # Story (content elements)
        self.story: List[Any] = []
        
        # Logo path
        self.logo_path = os.path.join(
            os.path.dirname(__file__),
            '../static/logo.png'
        )
    
    def add_header(self, report_period: str = "", factory_name: str = ""):
        """
        Add report header with logo and title.
        
        Args:
            report_period: e.g., "November 2025"
            factory_name: e.g., "Demo Manufacturing Plant"
        """
        # Logo
        if os.path.exists(self.logo_path):
            logo = RLImage(self.logo_path, width=30*mm, height=30*mm*0.4)  # Smaller logo
            self.story.append(logo)
            self.story.append(Spacer(1, 4))
        
        # Title
        title_para = Paragraph(self.title, self.styles['ReportTitle'])
        self.story.append(title_para)
        
        # Subtitle
        if self.subtitle:
            subtitle_style = ParagraphStyle(
                name='Subtitle',
                parent=self.styles['ReportBody'],
                fontSize=FONT_SIZE_BODY,
                textColor=COLOR_GRAY_DARK,
                alignment=1  # Center
            )
            subtitle_para = Paragraph(self.subtitle, subtitle_style)
            self.story.append(subtitle_para)
        
        # Report period
        if report_period:
            period_style = ParagraphStyle(
                name='Period',
                parent=self.styles['ReportBody'],
                fontSize=FONT_SIZE_BODY,
                textColor=COLOR_NAVY,
                fontName=FONT_BOLD,
                alignment=1
            )
            period_para = Paragraph(f"Report Period: {report_period}", period_style)
            self.story.append(period_para)
        
        # Factory name
        if factory_name:
            factory_style = ParagraphStyle(
                name='Factory',
                parent=self.styles['ReportBody'],
                fontSize=FONT_SIZE_BODY,
                textColor=COLOR_GRAY_DARK,
                alignment=1
            )
            factory_para = Paragraph(f"Factory: {factory_name}", factory_style)
            self.story.append(factory_para)
        
        self.story.append(Spacer(1, 8))  # Reduced from 15
        
        # Horizontal line
        line_table = Table([['']], colWidths=[self.content_width])
        line_table.setStyle([
            ('LINEABOVE', (0, 0), (-1, 0), 2, COLOR_NAVY)
        ])
        self.story.append(line_table)
        self.story.append(Spacer(1, 6))  # Reduced from 12
    
    def add_section(self, title: str):
        """Add section heading."""
        section_para = Paragraph(title, self.styles['SectionHeading'])
        self.story.append(section_para)
    
    def add_paragraph(self, text: str):
        """Add body paragraph."""
        para = Paragraph(text, self.styles['ReportBody'])
        self.story.append(para)
    
    def add_spacer(self, height: float = 12):
        """Add vertical space."""
        self.story.append(Spacer(1, height))
    
    def add_bullet_list(self, items: List[str]):
        """Add bullet point list."""
        for item in items:
            bullet_text = f"• {item}"
            para = Paragraph(bullet_text, self.styles['BulletItem'])
            self.story.append(para)
    
    def add_table(
        self,
        data: List[List[Any]],
        col_widths: List[float] = None,
        is_summary: bool = False
    ):
        """
        Add table to report.
        
        Args:
            data: 2D list [[header1, header2], [val1, val2], ...]
            col_widths: Column widths in mm (or None for auto)
            is_summary: Use summary/KPI table style
        """
        if col_widths:
            col_widths = [w * mm for w in col_widths]
        
        table = Table(data, colWidths=col_widths)
        
        if is_summary:
            table.setStyle(get_summary_table_style())
        else:
            table.setStyle(get_table_style())
        
        self.story.append(table)
        self.story.append(Spacer(1, 8))  # Balanced spacing
    
    def add_image(self, image_buffer: BytesIO, width: float = None, height: float = None):
        """
        Add image from BytesIO buffer.
        
        Args:
            image_buffer: Image data (e.g., matplotlib chart)
            width: Image width in mm (or None for auto)
            height: Image height in mm (or None for auto)
        """
        if width is None:
            width = self.content_width - 20*mm
        else:
            width = width * mm
        
        if height:
            height = height * mm
        
        img = RLImage(image_buffer, width=width, height=height)
        self.story.append(img)
        self.story.append(Spacer(1, 5))  # Reduced from 10
    
    def add_footer_text(self):
        """Add footer with generation timestamp and compliance note."""
        self.story.append(Spacer(1, 8))  # Reduced from 15
        
        # Horizontal line
        line_table = Table([['']], colWidths=[self.content_width])
        line_table.setStyle([
            ('LINEABOVE', (0, 0), (-1, 0), 1, COLOR_GRAY_DARK)
        ])
        self.story.append(line_table)
        self.story.append(Spacer(1, 4))  # Reduced from 8
        
        # Generation timestamp
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        timestamp_para = Paragraph(f"Generated: {timestamp}", self.styles['SmallText'])
        self.story.append(timestamp_para)
        
        # Compliance note
        compliance_para = Paragraph(
            "EnMS System v1.0 | ISO 50001:2018 Compliant",
            self.styles['SmallText']
        )
        self.story.append(compliance_para)
    
    def build(self) -> BytesIO:
        """
        Build PDF and return as BytesIO buffer.
        
        Returns:
            BytesIO: PDF file buffer
        """
        buffer = BytesIO()
        
        # Create PDF document
        doc = SimpleDocTemplate(
            buffer,
            pagesize=self.pagesize,
            leftMargin=self.margin_left,
            rightMargin=self.margin_right,
            topMargin=self.margin_top,
            bottomMargin=self.margin_bottom,
            title=self.title
        )
        
        # Build PDF
        doc.build(self.story, onFirstPage=self._page_number, onLaterPages=self._page_number)
        
        buffer.seek(0)
        return buffer
    
    def _page_number(self, canvas, doc):
        """
        Add page numbers to footer (called by ReportLab).
        
        Args:
            canvas: ReportLab canvas
            doc: Document object
        """
        canvas.saveState()
        canvas.setFont(FONT_REGULAR, FONT_SIZE_SMALL)
        canvas.setFillColor(COLOR_GRAY_DARK)
        
        page_num = canvas.getPageNumber()
        text = f"Page {page_num}"
        canvas.drawRightString(
            self.width - self.margin_right,
            15 * mm,
            text
        )
        
        canvas.restoreState()
