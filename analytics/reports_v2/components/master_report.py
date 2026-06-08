"""
Master Report Generator - Orchestrates complete PDF report
Combines all sections with table of contents, page numbers, and navigation.
"""
from typing import Dict, Any, List, Optional
from pathlib import Path
import logging

from reports_v2.components.cover_page import CoverPage
from reports_v2.components.executive_dashboard import ExecutiveDashboard
from reports_v2.components.energy_overview import EnergyOverview
from reports_v2.components.machine_analysis import MachineAnalysis
from reports_v2.components.cost_analysis import CostAnalysis
from reports_v2.components.carbon_analysis import CarbonAnalysis
from reports_v2.generators.html_generator import HTMLGenerator
from reports_v2.generators.pdf_generator import PDFGenerator

logger = logging.getLogger(__name__)


class MasterReport:
    """
    Master report orchestrator for complete PDF generation.
    
    Features:
    - Combines all report sections
    - Table of contents with page numbers
    - Consistent headers/footers
    - Page numbering
    - Section navigation
    """
    
    def __init__(self):
        self.html_gen = HTMLGenerator()
        self.pdf_gen = PDFGenerator()
        
        # Component instances
        self.cover_page = CoverPage()
        self.dashboard = ExecutiveDashboard()
        self.energy_overview = EnergyOverview()
        self.machine_analysis = MachineAnalysis()
        self.cost_analysis = CostAnalysis()
        self.carbon_analysis = CarbonAnalysis()
    
    def generate_complete_report(self,
                                 # Report metadata
                                 facility_name: str,
                                 reporting_period: str,
                                 generated_date: str,
                                 
                                 # Section data
                                 cover_data: Dict[str, Any],
                                 dashboard_data: Dict[str, Any],
                                 energy_data: Dict[str, Any],
                                 machine_ranking_data: Optional[Dict[str, Any]] = None,
                                 machine_profiles: Optional[List[Dict[str, Any]]] = None,
                                 cost_data: Optional[Dict[str, Any]] = None,
                                 carbon_data: Optional[Dict[str, Any]] = None,
                                 
                                 # Output
                                 output_path: Path = None) -> Path:
        """
        Generate complete report PDF.
        
        Args:
            facility_name: Facility name
            reporting_period: Reporting period
            generated_date: Report generation date
            cover_data: Cover page data
            dashboard_data: Executive dashboard data
            energy_data: Energy overview data
            machine_ranking_data: Machine ranking data
            machine_profiles: List of machine profile data
            cost_data: Cost analysis data
            carbon_data: Carbon analysis data
            output_path: Output file path
            
        Returns:
            Path to generated PDF
        """
        if output_path is None:
            output_path = Path("/tmp/enms_complete_report.pdf")
        
        logger.info("Generating complete report...")
        
        # Build table of contents
        toc_items = [
            {'title': 'Executive Summary', 'page': 3},
            {'title': 'Energy Overview', 'page': 4},
        ]
        
        current_page = 4
        if machine_ranking_data:
            toc_items.append({'title': 'Machine Analysis', 'page': current_page})
            current_page += 1
            
            if machine_profiles:
                for profile in machine_profiles:
                    toc_items.append({
                        'title': f"  → {profile.get('machine_name', 'Machine')}",
                        'page': current_page
                    })
                    current_page += 1
        
        if cost_data:
            toc_items.append({'title': 'Cost Analysis', 'page': current_page})
            current_page += 1
        
        if carbon_data:
            toc_items.append({'title': 'Carbon Footprint', 'page': current_page})
            current_page += 1
        
        # Prepare all section HTML
        sections_html = []
        
        # Cover page (page 1)
        cover_html = self.html_gen.render('sections/cover_page.html', cover_data)
        sections_html.append(cover_html)
        
        # TOC will be inserted here as page 2 in _build_complete_html
        
        # Executive dashboard (page 3 - after TOC)
        dashboard_html = self.html_gen.render('sections/executive_dashboard.html', dashboard_data)
        sections_html.append(dashboard_html)
        
        # Energy overview
        energy_html = self.html_gen.render('sections/energy_overview.html', energy_data)
        sections_html.append(energy_html)
        
        # Machine analysis
        if machine_ranking_data:
            ranking_html = self.html_gen.render('sections/machine_ranking.html', machine_ranking_data)
            sections_html.append(ranking_html)
            
            if machine_profiles:
                for profile_data in machine_profiles:
                    profile_html = self.html_gen.render('sections/machine_profile.html', profile_data)
                    sections_html.append(profile_html)
        
        # Cost analysis
        if cost_data:
            cost_html = self.html_gen.render('sections/cost_analysis.html', cost_data)
            sections_html.append(cost_html)
        
        # Carbon analysis
        if carbon_data:
            carbon_html = self.html_gen.render('sections/carbon_analysis.html', carbon_data)
            sections_html.append(carbon_html)
        
        # Build complete HTML document
        full_html = self._build_complete_html(
            facility_name=facility_name,
            reporting_period=reporting_period,
            generated_date=generated_date,
            toc_items=toc_items,
            sections_html=sections_html
        )
        
        # Generate PDF
        logger.info(f"Rendering PDF to {output_path}...")
        result_path = self.pdf_gen.generate_from_html(full_html, output_path)
        
        logger.info(f"Complete report generated: {result_path}")
        return result_path

    async def generate_complete_report_async(self,
                                 facility_name: str,
                                 reporting_period: str,
                                 generated_date: str,
                                 cover_data: Dict[str, Any],
                                 dashboard_data: Dict[str, Any],
                                 energy_data: Dict[str, Any],
                                 machine_ranking_data: Optional[Dict[str, Any]] = None,
                                 machine_profiles: Optional[List[Dict[str, Any]]] = None,
                                 cost_data: Optional[Dict[str, Any]] = None,
                                 carbon_data: Optional[Dict[str, Any]] = None,
                                 output_path: Path = None) -> Path:
        """
        Generate complete report PDF using ASYNC Playwright.
        Use this method when calling from uvicorn/FastAPI endpoints.
        """
        logger.info("Generating complete report (async)...")
        
        # Build HTML using same logic as sync version
        if output_path is None:
            output_path = Path("/tmp/enms_report.pdf")
            
        toc_items = self._build_toc_items(machine_ranking_data, machine_profiles, cost_data, carbon_data)
        sections_html = self._build_sections_html(
            cover_data, dashboard_data, energy_data, 
            machine_ranking_data, machine_profiles, cost_data, carbon_data
        )
        
        full_html = self._build_complete_html(
            facility_name=facility_name,
            reporting_period=reporting_period,
            generated_date=generated_date,
            toc_items=toc_items,
            sections_html=sections_html
        )
        
        # Generate PDF using ASYNC method
        logger.info(f"Rendering PDF (async) to {output_path}...")
        result_path = await self.pdf_gen.generate_from_html_async(full_html, str(output_path))
        
        logger.info(f"Complete report generated (async): {result_path}")
        return result_path

    def _build_toc_items(self, machine_ranking_data, machine_profiles, cost_data, carbon_data):
        """Build table of contents items."""
        toc_items = [
            {'title': 'Cover Page', 'page': 1},
            {'title': 'Table of Contents', 'page': 2},
            {'title': 'Executive Dashboard', 'page': 3},
            {'title': 'Energy Overview', 'page': 4},
        ]
        current_page = 5
        if machine_ranking_data:
            toc_items.append({'title': 'Machine Ranking', 'page': current_page})
            current_page += 1
            if machine_profiles:
                for profile in machine_profiles:
                    name = profile.get('machine_name', profile.get('name', 'Machine'))
                    toc_items.append({'title': f'  → {name}', 'page': current_page})
                    current_page += 1
        if cost_data:
            toc_items.append({'title': 'Cost Analysis', 'page': current_page})
            current_page += 1
        if carbon_data:
            toc_items.append({'title': 'Carbon Footprint', 'page': current_page})
        return toc_items

    def _build_sections_html(self, cover_data, dashboard_data, energy_data, 
                            machine_ranking_data, machine_profiles, cost_data, carbon_data):
        """Build HTML for all sections."""
        sections_html = []
        
        cover_html = self.html_gen.render('sections/cover_page.html', cover_data)
        sections_html.append(cover_html)
        
        dashboard_html = self.html_gen.render('sections/executive_dashboard.html', dashboard_data)
        sections_html.append(dashboard_html)
        
        energy_html = self.html_gen.render('sections/energy_overview.html', energy_data)
        sections_html.append(energy_html)
        
        if machine_ranking_data:
            ranking_html = self.html_gen.render('sections/machine_ranking.html', machine_ranking_data)
            sections_html.append(ranking_html)
            if machine_profiles:
                for profile_data in machine_profiles:
                    profile_html = self.html_gen.render('sections/machine_profile.html', profile_data)
                    sections_html.append(profile_html)
        
        if cost_data:
            cost_html = self.html_gen.render('sections/cost_analysis.html', cost_data)
            sections_html.append(cost_html)
        
        if carbon_data:
            carbon_html = self.html_gen.render('sections/carbon_analysis.html', carbon_data)
            sections_html.append(carbon_html)
            
        return sections_html

    def _build_complete_html(self,
                            facility_name: str,
                            reporting_period: str,
                            generated_date: str,
                            toc_items: List[Dict[str, Any]],
                            sections_html: List[str]) -> str:
        """Build complete HTML document with all sections."""
        
        # Table of contents HTML
        toc_html = '<div class="section" style="padding: 2rem; page-break-after: always;">'
        toc_html += '<div style="margin-bottom: 2rem; border-bottom: 3px solid #00A8E8; padding-bottom: 1rem;">'
        toc_html += '<h1 style="font-size: 32px; font-weight: 700; color: #1a365d; margin: 0 0 0.5rem 0;">Table of Contents</h1>'
        toc_html += f'<p style="font-size: 14px; color: #718096; margin: 0;">{facility_name} - {reporting_period}</p>'
        toc_html += '</div>'
        
        toc_html += '<div style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 2rem;">'
        for item in toc_items:
            indent = '2rem' if item['title'].startswith('  →') else '0'
            toc_html += f'''
            <div style="display: flex; justify-content: space-between; padding: 0.75rem; margin-left: {indent}; border-bottom: 1px solid #f7fafc;">
                <div style="font-size: 14px; color: #2d3748; font-weight: {'400' if indent else '600'};">
                    {item['title'].replace('  → ', '')}
                </div>
                <div style="font-size: 14px; color: #718096;">
                    {item['page']}
                </div>
            </div>
            '''
        toc_html += '</div></div>'
        
        # Insert TOC as page 2 (after cover page)
        # Cover is sections_html[0], insert TOC before dashboard
        sections_html_with_toc = [sections_html[0], toc_html] + sections_html[1:]
        
        # Combine all sections
        all_sections = '\n'.join(sections_html_with_toc)
        
        # Complete HTML document
        complete_html = f'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Energy Management Report - {facility_name}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f7fafc;
            color: #2d3748;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
        }}
        
        .section {{
            background: white;
            position: relative;
        }}
        
        /* Page break control */
        .page-break {{
            page-break-after: always;
        }}
        
        /* Print optimization */
        @media print {{
            body {{
                background: white;
            }}
            
            .section {{
                page-break-after: always;
            }}
            
            /* Prevent breaks inside elements */
            table, figure, img {{
                page-break-inside: avoid;
            }}
        }}
        
        /* Footer on each page */
        @page {{
            margin: 15mm;
            
            @bottom-center {{
                content: counter(page);
                font-family: Inter, sans-serif;
                font-size: 10px;
                color: #718096;
            }}
            
            @bottom-left {{
                content: "{facility_name}";
                font-family: Inter, sans-serif;
                font-size: 10px;
                color: #718096;
            }}
            
            @bottom-right {{
                content: "{reporting_period}";
                font-family: Inter, sans-serif;
                font-size: 10px;
                color: #718096;
            }}
        }}
    </style>
</head>
<body>
    {all_sections}
    
    <!-- Report Metadata Footer -->
    <div style="padding: 2rem; text-align: center; color: #a0aec0; font-size: 11px; border-top: 1px solid #e2e8f0;">
        <p>Generated on {generated_date}</p>
        <p style="margin-top: 0.5rem;">EnMS - Energy Management System | ISO 50001 Compliant</p>
    </div>
</body>
</html>
        '''
        
        return complete_html
