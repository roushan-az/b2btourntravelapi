"""
PDF Generation Service — Produces professional quotation PDFs using WeasyPrint.
Falls back to a plain HTML file if WeasyPrint is unavailable.
"""

import logging
import os
import tempfile
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


# ── HTML Template ──────────────────────────────────────────────────────────────

def _build_html(quotation_data: dict) -> str:
    """Render quotation data into a styled HTML string."""
    q = quotation_data
    items = q.get("items", [])
    activities = q.get("activities", [])
    valid_until = (date.today() + timedelta(days=settings.QUOTATION_VALID_DAYS)).strftime("%d %B %Y")
    today = date.today().strftime("%d %B %Y")

    # Build items rows
    items_html = ""
    for item in items:
        items_html += f"""
        <tr>
            <td>{item.get('description', '')}</td>
            <td class="muted">{item.get('detail', '')}</td>
            <td class="muted">{item.get('quantity', 1)}</td>
            <td class="amount">₹{float(item.get('unit_price', 0)):,.0f}</td>
            <td class="amount"><strong>₹{float(item.get('total_price', 0)):,.2f}</strong></td>
        </tr>"""

    for act in activities:
        items_html += f"""
        <tr>
            <td>{act.get('name', '')}</td>
            <td class="muted">Activity</td>
            <td class="muted">{act.get('quantity', 1)}</td>
            <td class="amount">₹{float(act.get('unit_price', 0)):,.0f}</td>
            <td class="amount"><strong>₹{float(act.get('total_price', 0)):,.2f}</strong></td>
        </tr>"""

    # Inclusions list
    inclusions = [
        "Accommodation in selected hotels / houseboats as per itinerary",
        "Meals as per selected meal plan",
        "All transfers by private vehicle",
        "Airport / railway station pickup and drop",
        "All sightseeing as per day-wise itinerary",
        "Toll taxes, parking charges, driver allowance",
        "Welcome drink on arrival",
    ]
    excls = [
        "Airfare / train fare",
        "Gondola tickets, pony rides & adventure activities",
        "Personal expenses, tips, and porterage",
        "Travel insurance",
        f"GST @ {q.get('gst_rate', 5)}% (shown separately)",
        "Anything not mentioned in inclusions",
    ]

    inc_html = "".join(f"<li>✓ {i}</li>" for i in inclusions)
    exc_html = "".join(f"<li>✗ {e}</li>" for e in excls)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Quotation {q.get('quote_number', '')} — WanderKashmir</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;1,400&family=Jost:wght@300;400;500;600&display=swap');
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Jost', sans-serif; background: #fff; color: #1a1a1a; font-size: 11pt; line-height: 1.6; }}
  .page {{ max-width: 800px; margin: 0 auto; padding: 0; }}

  /* Header */
  .header {{ background: linear-gradient(135deg, #1a2e1a 0%, #1c3a4a 100%); color: white; padding: 32px 40px; display: flex; justify-content: space-between; align-items: flex-start; }}
  .brand {{ display: flex; align-items: center; gap: 12px; }}
  .brand-icon {{ font-size: 2.5rem; }}
  .brand-name {{ font-family: 'Cormorant Garamond', serif; font-size: 1.6rem; font-weight: 500; }}
  .brand-sub {{ font-size: 0.65rem; letter-spacing: 0.15em; text-transform: uppercase; opacity: 0.55; margin-top: 2px; }}
  .quote-badge {{ background: rgba(255,255,255,0.1); padding: 16px 20px; border-radius: 8px; text-align: right; }}
  .quote-badge .label {{ font-size: 0.65rem; letter-spacing: 0.12em; text-transform: uppercase; opacity: 0.55; }}
  .quote-badge .value {{ font-size: 1.1rem; font-weight: 700; letter-spacing: 0.04em; margin-top: 2px; font-family: monospace; }}
  .quote-badge .valid {{ font-size: 0.7rem; opacity: 0.5; margin-top: 6px; }}

  /* Title band */
  .title-band {{ background: #f5e6d3; padding: 16px 40px; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 12px; border-bottom: 2px solid rgba(212,130,42,0.2); }}
  .title-band .field {{ }}
  .title-band .field-label {{ font-size: 0.62rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; color: #d4822a; }}
  .title-band .field-value {{ font-size: 0.9rem; font-weight: 600; color: #1a2e1a; margin-top: 2px; }}

  /* Section */
  .section {{ padding: 24px 40px; border-bottom: 1px solid #e8e4dc; }}
  .section-title {{ font-family: 'Cormorant Garamond', serif; font-size: 1.3rem; font-weight: 500; margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }}
  .section-title::before {{ content: ''; display: inline-block; width: 3px; height: 20px; background: #d4822a; border-radius: 2px; }}

  /* Table */
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ padding: 8px 12px; background: #1a2e1a; color: rgba(255,255,255,0.8); font-size: 0.7rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; text-align: left; }}
  td {{ padding: 10px 12px; border-bottom: 1px solid #e8e4dc; font-size: 0.85rem; vertical-align: top; }}
  tr:nth-child(even) td {{ background: #faf8f4; }}
  .amount {{ text-align: right; }}
  .muted {{ color: #6b6b6b; }}
  .total-row td {{ background: #1a2e1a !important; color: white; font-weight: 700; padding: 12px; }}
  .subtotal-row td {{ background: #f5e6d3 !important; font-weight: 600; }}

  /* Inc/Exc */
  .inc-exc {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
  .inc-exc ul {{ list-style: none; padding: 0; }}
  .inc-exc li {{ padding: 4px 0; font-size: 0.82rem; color: #2d2d2d; border-bottom: 1px dashed #e8e4dc; }}
  .inc-title {{ font-weight: 700; font-size: 0.8rem; margin-bottom: 8px; display: flex; align-items: center; gap: 6px; }}
  .inc-title.green {{ color: #2e7d32; }}
  .inc-title.red {{ color: #c62828; }}

  /* Footer */
  .footer {{ padding: 20px 40px; display: flex; justify-content: space-between; align-items: center; background: #f8f6f2; }}
  .footer-brand {{ font-family: 'Cormorant Garamond', serif; font-size: 1.1rem; color: #1a2e1a; }}
  .footer-tagline {{ color: #d4822a; font-style: italic; }}
  .terms {{ font-size: 0.72rem; color: #8a8a8a; line-height: 1.6; padding: 16px 40px; background: #f8f6f2; border-top: 1px solid #e8e4dc; }}
  .highlight {{ color: #d4822a; font-weight: 600; }}
</style>
</head>
<body>
<div class="page">

  <!-- HEADER -->
  <div class="header">
    <div class="brand">
      <div class="brand-icon">⛰</div>
      <div>
        <div class="brand-name">WanderKashmir</div>
        <div class="brand-sub">B2B Travel Portal · Kashmir</div>
      </div>
    </div>
    <div class="quote-badge">
      <div class="label">Quotation No.</div>
      <div class="value">{q.get('quote_number', '')}</div>
      <div class="valid">Valid until: {valid_until}</div>
      <div class="valid">Prepared: {today}</div>
    </div>
  </div>

  <!-- TITLE BAND -->
  <div class="title-band">
    <div class="field">
      <div class="field-label">Prepared for</div>
      <div class="field-value">{q.get('client_name', '')}</div>
    </div>
    <div class="field">
      <div class="field-label">Package</div>
      <div class="field-value">{q.get('package_label', '')} — Kashmir</div>
    </div>
    <div class="field">
      <div class="field-label">Travellers</div>
      <div class="field-value">{q.get('num_adults', 2)} Adult(s), {q.get('num_children', 0)} Child(ren)</div>
    </div>
    <div class="field">
      <div class="field-label">Travel Date</div>
      <div class="field-value">{q.get('travel_date', 'To Be Confirmed')}</div>
    </div>
    <div class="field">
      <div class="field-label">Prepared by</div>
      <div class="field-value">{q.get('agency_name', 'WanderKashmir Agent')}</div>
    </div>
  </div>

  <!-- COST BREAKDOWN -->
  <div class="section">
    <div class="section-title">Package Cost Breakdown</div>
    <table>
      <thead>
        <tr>
          <th style="width:35%">Description</th>
          <th>Details</th>
          <th style="width:8%">Qty</th>
          <th style="width:15%; text-align:right">Unit Rate</th>
          <th style="width:18%; text-align:right">Total</th>
        </tr>
      </thead>
      <tbody>
        {items_html}
        <tr class="subtotal-row">
          <td colspan="4"><strong>Sub-Total</strong></td>
          <td class="amount"><strong>₹{float(q.get('base_cost', 0)):,.2f}</strong></td>
        </tr>
        <tr>
          <td colspan="4" class="muted">GST @ {q.get('gst_rate', 5)}%</td>
          <td class="amount muted">₹{float(q.get('gst_amount', 0)):,.2f}</td>
        </tr>
        <tr class="total-row">
          <td colspan="4">TOTAL PACKAGE COST <span style="font-size:0.75rem; opacity:0.7">(Per Person, Single Occupancy)</span></td>
          <td class="amount" style="font-size:1.1rem; font-family:'Cormorant Garamond',serif; color:#e8a045;">
            ₹{float(q.get('total_cost', 0)):,.0f}
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- INCLUSIONS / EXCLUSIONS -->
  <div class="section">
    <div class="section-title">Inclusions &amp; Exclusions</div>
    <div class="inc-exc">
      <div>
        <div class="inc-title green">✓ Included in Package</div>
        <ul>{inc_html}</ul>
      </div>
      <div>
        <div class="inc-title red">✗ Not Included</div>
        <ul>{exc_html}</ul>
      </div>
    </div>
  </div>

  <!-- NOTES -->
  {"<div class='section'><div class='section-title'>Special Notes</div><p style='font-size:0.85rem; color:#5a5a5a;'>" + q.get('notes', '') + "</p></div>" if q.get('notes') else ""}

  <!-- FOOTER -->
  <div class="footer">
    <div>
      <div class="footer-brand">{q.get('agency_name', 'WanderKashmir')}</div>
      <div style="font-size:0.75rem; color:#8a8a8a; margin-top:2px;">{q.get('agent_name', '')} · Powered by WanderKashmir</div>
    </div>
    <div style="text-align:center; font-size:1.8rem;">⛰</div>
    <div style="text-align:right;">
      <div class="footer-tagline">Kashmir — Paradise on Earth</div>
      <div style="font-size:0.72rem; color:#8a8a8a; margin-top:2px;">wanderkashmir.com</div>
    </div>
  </div>

  <div class="terms">
    <strong>Terms &amp; Conditions:</strong> This quotation is valid for {settings.QUOTATION_VALID_DAYS} days from the date of issue.
    Prices are subject to change during peak season and public holidays.
    A 25% non-refundable advance is required to confirm booking.
    Balance payment is due 14 days prior to travel date.
    Cancellation charges apply as per company policy.
    WanderKashmir acts as a B2B facilitator and is not liable for force majeure events.
  </div>

</div>
</body>
</html>"""


class PDFService:
    """Generate PDF bytes from a quotation dict."""

    def generate(self, quotation_data: dict) -> bytes:
        """
        Generate a PDF and return the bytes.
        Uses WeasyPrint if available, else returns HTML bytes as fallback.
        """
        html_content = _build_html(quotation_data)

        if settings.PDF_ENGINE == "weasyprint":
            return self._generate_weasyprint(html_content)
        else:
            return self._generate_reportlab(quotation_data)

    def _generate_weasyprint(self, html_content: str) -> bytes:
        try:
            from weasyprint import HTML
            pdf_bytes = HTML(string=html_content).write_pdf()
            return pdf_bytes
        except ImportError:
            logger.warning("WeasyPrint not installed — returning HTML bytes as fallback")
            return html_content.encode("utf-8")
        except Exception as exc:
            logger.error(f"WeasyPrint PDF generation failed: {exc}")
            raise

    def _generate_reportlab(self, q: dict) -> bytes:
        """Minimal ReportLab fallback."""
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import cm
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
            import io as _io

            buf = _io.BytesIO()
            doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
            styles = getSampleStyleSheet()
            story = []

            story.append(Paragraph(f"<b>WanderKashmir</b> — Quotation {q.get('quote_number', '')}", styles["Title"]))
            story.append(Spacer(1, 0.5*cm))
            story.append(Paragraph(f"Client: {q.get('client_name', '')}", styles["Normal"]))
            story.append(Paragraph(f"Package: {q.get('package_label', '')}", styles["Normal"]))
            story.append(Paragraph(f"Total: ₹{float(q.get('total_cost', 0)):,.0f}", styles["Heading2"]))

            doc.build(story)
            return buf.getvalue()
        except ImportError:
            logger.warning("ReportLab not installed — returning HTML bytes")
            return _build_html(q).encode("utf-8")

    def build_blob_name(self, quote_number: str) -> str:
        """Azure Blob name for a quotation PDF."""
        safe = quote_number.replace("/", "-").replace(" ", "_")
        return f"quotations/{safe}.pdf"


# Singleton
pdf_service = PDFService()