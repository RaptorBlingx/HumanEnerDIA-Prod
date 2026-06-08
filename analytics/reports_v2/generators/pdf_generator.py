"""
PDF Generator - Playwright-based HTML to PDF conversion
Provides high-quality, pixel-perfect PDF generation with full CSS support.
"""
from pathlib import Path
from typing import Optional, Dict, Any
from playwright.sync_api import sync_playwright
from playwright.async_api import async_playwright
import logging

logger = logging.getLogger(__name__)


class PDFGenerator:
    """
    Generate PDF files from HTML using Playwright's Chromium engine.
    
    Features:
    - Full CSS support (Flexbox, Grid, custom fonts, etc.)
    - Print-optimized rendering
    - Page numbering and headers/footers
    - High-resolution output (300 DPI equivalent)
    """
    
    def __init__(self):
        self.default_options = {
            'format': 'A4',
            'print_background': True,
            'margin': {
                'top': '15mm',
                'right': '15mm',
                'bottom': '15mm',
                'left': '15mm'
            },
            'prefer_css_page_size': True,
            'display_header_footer': False,  # We'll use HTML-based headers/footers for more control
        }
    
    def generate_from_html(
        self,
        html_content: str,
        output_path: str,
        options: Optional[Dict[str, Any]] = None
    ) -> Path:
        """
        Generate PDF from HTML string.
        
        Args:
            html_content: Complete HTML document string
            output_path: Path where PDF should be saved
            options: Optional PDF generation options (overrides defaults)
            
        Returns:
            Path object pointing to generated PDF
            
        Raises:
            Exception: If PDF generation fails
        """
        try:
            # Merge custom options with defaults
            pdf_options = {**self.default_options, **(options or {})}
            
            logger.info(f"Generating PDF at: {output_path}")
            
            with sync_playwright() as p:
                # Launch browser in headless mode with sandbox disabled for containers
                browser = p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
                )
                page = browser.new_page()
                
                # Set timeout to prevent hanging
                page.set_default_timeout(30000)
                
                # Set content - use 'load' instead of 'networkidle' to avoid CDN hangs
                page.set_content(html_content, wait_until='load', timeout=30000)
                
                # Wait for any dynamic content/charts to render
                page.wait_for_timeout(2000)
                
                # Generate PDF
                page.pdf(path=output_path, **pdf_options)
                
                browser.close()
            
            output = Path(output_path)
            logger.info(f"✅ PDF generated successfully: {output_path} ({output.stat().st_size / 1024:.1f} KB)")
            
            return output
            
        except Exception as e:
            logger.error(f"Failed to generate PDF: {str(e)}")
            raise
    
    def generate_from_file(
        self,
        html_file_path: str,
        output_path: str,
        options: Optional[Dict[str, Any]] = None
    ) -> Path:
        """
        Generate PDF from HTML file.
        
        Args:
            html_file_path: Path to HTML file
            output_path: Path where PDF should be saved
            options: Optional PDF generation options
            
        Returns:
            Path object pointing to generated PDF
        """
        html_path = Path(html_file_path)
        
        if not html_path.exists():
            raise FileNotFoundError(f"HTML file not found: {html_file_path}")
        
        html_content = html_path.read_text(encoding='utf-8')
        return self.generate_from_html(html_content, output_path, options)

    async def generate_from_html_async(
        self,
        html_content: str,
        output_path: str,
        options: Optional[Dict[str, Any]] = None
    ) -> Path:
        """
        Generate PDF from HTML string (ASYNC version for uvicorn).
        
        This method uses async_playwright() which works correctly
        within uvicorn's event loop without blocking.
        """
        try:
            pdf_options = {**self.default_options, **(options or {})}
            
            logger.info(f"Generating PDF (async) at: {output_path}")
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
                )
                page = await browser.new_page()
                page.set_default_timeout(30000)
                
                await page.set_content(html_content, wait_until='load', timeout=30000)
                await page.wait_for_timeout(2000)
                await page.pdf(path=output_path, **pdf_options)
                await browser.close()
            
            output = Path(output_path)
            logger.info(f"✅ PDF generated (async): {output_path} ({output.stat().st_size / 1024:.1f} KB)")
            return output
            
        except Exception as e:
            logger.error(f"Failed to generate PDF (async): {str(e)}")
            raise


# Convenience function for quick PDF generation
def generate_pdf(html_content: str, output_path: str, **options) -> Path:
    """
    Quick PDF generation helper function.
    
    Usage:
        from reports_v2.generators.pdf_generator import generate_pdf
        generate_pdf('<html>...</html>', 'report.pdf', format='A4')
    """
    generator = PDFGenerator()
    return generator.generate_from_html(html_content, output_path, options)
