"""
Monthly EnPI Report Generator
==============================
Generates monthly energy performance reports compliant with ISO 50001.
"""

from typing import Dict, List, Any
from datetime import datetime
from io import BytesIO

from reports.base_report import BaseReport
from reports.styles import COLOR_SUCCESS, COLOR_WARNING, COLOR_DANGER, format_number


class MonthlyEnPIReport(BaseReport):
    """
    Monthly Energy Performance Indicator Report.
    
    Sections:
    1. Executive Summary
    2. Energy Performance Indicators (EnPIs)
    3. Consumption by Machine (SEU Analysis)
    4. Daily Consumption Trend
    5. Anomaly Summary
    6. Recommendations
    """
    
    def __init__(self, data: Dict[str, Any]):
        """
        Initialize monthly report with data.
        
        Args:
            data: Report data dictionary with sections
        """
        # Extract metadata
        period = data.get('period', 'Unknown Period')
        factory_name = data.get('factory_name', '')
        year = data.get('year', datetime.now().year)
        month = data.get('month', datetime.now().month)
        
        # Generate filename
        month_name = datetime(year, month, 1).strftime('%B')
        filename = f"EnPI_Report_{year}-{month:02d}_{factory_name.replace(' ', '_')}.pdf"
        
        super().__init__(
            title="MONTHLY ENERGY PERFORMANCE REPORT",
            subtitle="APlus Engineering - EnMS ISO 50001",
            filename=filename
        )
        
        self.data = data
        self.report_period = f"{month_name} {year}"
        self.factory_name = factory_name
    
    def generate(self) -> BytesIO:
        """
        Generate complete monthly report.
        
        Returns:
            BytesIO: PDF buffer
        """
        # Header
        self.add_header(self.report_period, self.factory_name)
        
        # Section 1: Executive Summary
        self._add_executive_summary()
        
        # Section 2: EnPIs
        self._add_enpi_section()
        
        # Section 3: Consumption by Machine
        self._add_machine_consumption()
        
        # Section 4: Daily Trend (chart will be added by service)
        if 'daily_trend_chart' in self.data:
            self.add_section("4. DAILY CONSUMPTION TREND")
            self.add_image(self.data['daily_trend_chart'], width=100, height=60)  # Increased for better visibility
            self._add_daily_stats()
        
        # Section 5: Anomaly Summary
        self._add_anomaly_summary()
        
        # Section 6: Recommendations
        self._add_recommendations()
        
        # Footer
        self.add_footer_text()
        
        # Build PDF
        return self.build()
    
    def _add_executive_summary(self):
        """Add executive summary section."""
        self.add_section("1. EXECUTIVE SUMMARY")
        
        summary = self.data.get('summary', {})
        
        bullets = [
            f"Total Energy Consumption: {format_number(summary.get('total_kwh', 0), 0)} kWh",
        ]
        
        # Month-over-month comparison
        if 'prev_month_change' in summary:
            change = summary['prev_month_change']
            sign = '+' if change >= 0 else ''
            bullets.append(f"vs Previous Month: {sign}{change:.1f}%")
        
        # Baseline comparison
        if 'baseline_deviation' in summary:
            dev = summary['baseline_deviation']
            sign = '+' if dev >= 0 else ''
            bullets.append(f"vs Baseline: {sign}{dev:.1f}%")
        
        # Anomalies
        if 'anomaly_counts' in summary:
            counts = summary['anomaly_counts']
            total = sum(counts.values())
            details = ', '.join([f"{count} {sev}" for sev, count in counts.items() if count > 0])
            bullets.append(f"Active Anomalies: {total} ({details})")
        
        # Cost estimate
        if 'total_kwh' in summary:
            cost = summary['total_kwh'] * 0.18  # EUR per kWh
            bullets.append(f"Cost Estimate: €{format_number(cost, 0)} (@0.18 EUR/kWh)")
        
        self.add_bullet_list(bullets)
        self.add_spacer(6)  # Reduced spacing
    
    def _add_enpi_section(self):
        """Add EnPI table section."""
        self.add_section("2. ENERGY PERFORMANCE INDICATORS (EnPIs)")
        
        enpis = self.data.get('enpis', [])
        
        if not enpis:
            self.add_paragraph("No EnPI data available for this period.")
            self.add_spacer(6)
            return
        
        # Build table data
        table_data = [['EnPI', 'Current', 'Target', 'Status']]
        
        for enpi in enpis:
            name = enpi.get('name', 'Unknown')
            current = format_number(enpi.get('current', 0), 2)
            target = format_number(enpi.get('target', 0), 2)
            
            # Determine status
            if 'status' in enpi:
                status = enpi['status']
            elif enpi.get('current', 0) <= enpi.get('target', 0):
                status = '✓ Good'
            else:
                status = '⚠ Above Target'
            
            table_data.append([name, current, target, status])
        
        self.add_table(table_data, col_widths=[70, 30, 30, 40], is_summary=True)
    
    def _add_machine_consumption(self):
        """Add machine consumption table and chart."""
        self.add_section("3. CONSUMPTION BY MACHINE (SEU Analysis)")
        
        machines = self.data.get('machines', [])
        
        if not machines:
            self.add_paragraph("No machine data available.")
            self.add_spacer(6)
            return
        
        # Add chart if provided
        if 'machine_chart' in self.data:
            self.add_image(self.data['machine_chart'], width=100, height=70)  # Increased for better visibility
            self.add_spacer(3)
        
        # Build table
        table_data = [['Machine', 'Energy (kWh)', '% of Total', 'Trend']]
        
        for machine in machines[:6]:  # Top 6 (reduced from 8 to save space)
            name = machine.get('name', 'Unknown')
            kwh = format_number(machine.get('kwh', 0), 0)
            percent = format_number(machine.get('percent', 0), 1)
            trend = machine.get('trend', '-')
            
            table_data.append([name, kwh, f"{percent}%", trend])
        
        self.add_table(table_data, col_widths=[60, 35, 30, 25])
    
    def _add_daily_stats(self):
        """Add daily consumption statistics."""
        daily = self.data.get('daily_stats', {})
        
        if not daily:
            return
        
        # Single line stats instead of bullet list to save space
        stats_text = (
            f"Avg: {format_number(daily.get('avg', 0), 0)} kWh | "
            f"Max: {format_number(daily.get('max', 0), 0)} kWh ({daily.get('max_date', 'N/A')}) | "
            f"Min: {format_number(daily.get('min', 0), 0)} kWh ({daily.get('min_date', 'N/A')})"
        )
        self.add_paragraph(stats_text)
        self.add_spacer(4)
    
    def _add_anomaly_summary(self):
        """Add anomaly summary section."""
        self.add_section("5. ANOMALY SUMMARY")
        
        anomalies = self.data.get('anomalies', [])
        counts = self.data.get('summary', {}).get('anomaly_counts', {})
        
        if not anomalies:
            self.add_paragraph("No anomalies detected in this period.")
            self.add_spacer(6)
            return
        
        # Build table - top 5 most recent (reduced from 10 to save space)
        table_data = [['Date', 'Machine', 'Severity', 'Status']]
        
        for anomaly in anomalies[:5]:
            date = anomaly.get('detected_at', 'N/A')
            if isinstance(date, datetime):
                date = date.strftime('%b %d %H:%M')
            machine = anomaly.get('machine', 'Unknown')
            severity = anomaly.get('severity', 'normal').capitalize()
            status = 'Resolved' if anomaly.get('is_resolved') else 'Open'
            
            table_data.append([date, machine, severity, status])
        
        self.add_table(table_data, col_widths=[35, 50, 30, 25])
        
        # Summary text
        total = sum(counts.values())
        resolved = sum([a.get('is_resolved', False) for a in anomalies])
        unresolved = total - resolved
        
        summary_text = f"Total: {total} anomalies | {resolved} resolved | {unresolved} unresolved"
        self.add_paragraph(summary_text)
        self.add_spacer(6)  # Reduced from 10
    
    def _add_recommendations(self):
        """Add auto-generated recommendations."""
        self.add_section("6. RECOMMENDATIONS (Auto-generated)")
        
        recommendations = self.data.get('recommendations', [])
        
        if not recommendations:
            # Generate basic recommendations
            recommendations = self._generate_recommendations()
        
        self.add_bullet_list(recommendations)
        self.add_spacer(6)  # Reduced from 10
    
    def _generate_recommendations(self) -> List[str]:
        """Auto-generate recommendations based on data."""
        recs = []
        
        summary = self.data.get('summary', {})
        machines = self.data.get('machines', [])
        counts = summary.get('anomaly_counts', {})
        
        # Anomaly recommendations
        critical = counts.get('critical', 0)
        warning = counts.get('warning', 0)
        
        if critical > 0:
            recs.append(f"⚠ {critical} critical anomalies require immediate attention")
        
        if warning > 0:
            recs.append(f"⚠ {warning} warning-level anomalies should be investigated")
        
        # High consumption recommendations
        if machines:
            top_machine = machines[0]
            percent = top_machine.get('percent', 0)
            if percent > 30:
                recs.append(
                    f"{top_machine.get('name')} consumes {percent:.1f}% of total energy - "
                    f"review for optimization opportunities"
                )
        
        # Baseline deviation
        if 'baseline_deviation' in summary:
            dev = summary['baseline_deviation']
            if dev > 5:
                recs.append(f"Energy consumption is {dev:.1f}% above baseline - investigate causes")
        
        # Generic recommendations
        if not recs:
            recs.append("Continue monitoring energy performance")
            recs.append("Review peak demand on high-consumption days")
        
        return recs
