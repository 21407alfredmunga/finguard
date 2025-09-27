"""
PDF Generation Service for FinGuard Lite invoices.

Uses WeasyPrint to generate PDF files from HTML templates with fallback options.
Handles file storage and URL generation.
"""

import os
import uuid
from pathlib import Path
from typing import Optional, Dict, Any
import logging
from datetime import datetime

from jinja2 import Environment, FileSystemLoader, Template
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration

from app.config import get_settings
from app.models.invoice import Invoice


logger = logging.getLogger(__name__)


class PDFGenerationError(Exception):
    """Custom exception for PDF generation failures."""
    pass


class InvoicePDFService:
    """Service for generating invoice PDFs using WeasyPrint and Jinja2."""
    
    def __init__(self):
        """Initialize PDF service with template engine and storage configuration."""
        self.settings = get_settings()
        
        # Setup Jinja2 template environment
        template_dir = Path(__file__).parent.parent / "templates"
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=True
        )
        
        # Setup PDF storage directory
        self.pdf_storage_dir = Path("storage/invoices")
        self.pdf_storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Font configuration for WeasyPrint
        self.font_config = FontConfiguration()
        
        logger.info("Invoice PDF Service initialized")
    
    def _get_template(self) -> Template:
        """Get the invoice HTML template."""
        try:
            return self.jinja_env.get_template("invoice_template.html")
        except Exception as e:
            logger.error(f"Failed to load invoice template: {e}")
            raise PDFGenerationError(f"Template loading failed: {e}")
    
    def _render_html(self, invoice: Invoice) -> str:
        """Render HTML content from invoice data using Jinja2 template."""
        
        template = self._get_template()
        
        # Prepare template context
        context = {
            'invoice': invoice,
            'current_date': datetime.now(),
            'company': {
                'name': 'FinGuard Lite',
                'tagline': 'AI-Powered Financial Assistant for Kenyan SMEs',
                'email': 'support@finguard.co.ke',
                'phone': '+254 700 000 000',
                'website': 'www.finguard.co.ke'
            }
        }
        
        try:
            html_content = template.render(**context)
            logger.debug(f"Rendered HTML template for invoice {invoice.invoice_number}")
            return html_content
        
        except Exception as e:
            logger.error(f"Template rendering failed for invoice {invoice.invoice_number}: {e}")
            raise PDFGenerationError(f"Template rendering failed: {e}")
    
    def _generate_pdf_filename(self, invoice: Invoice) -> str:
        """Generate unique PDF filename for invoice."""
        
        # Create filename with invoice number and timestamp
        safe_invoice_number = "".join(c for c in invoice.invoice_number if c.isalnum() or c in '-_')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        return f"invoice_{safe_invoice_number}_{timestamp}.pdf"
    
    def _create_pdf_from_html(self, html_content: str, output_path: Path) -> None:
        """Generate PDF file from HTML content using WeasyPrint."""
        
        try:
            # Create HTML object
            html_doc = HTML(string=html_content)
            
            # Optional CSS for better PDF formatting
            css_content = """
                @page {
                    size: A4;
                    margin: 1cm;
                }
                
                body {
                    -webkit-print-color-adjust: exact !important;
                    color-adjust: exact !important;
                }
                
                .no-break {
                    page-break-inside: avoid;
                }
                
                .page-break {
                    page-break-before: always;
                }
            """
            
            css_doc = CSS(string=css_content, font_config=self.font_config)
            
            # Generate PDF
            html_doc.write_pdf(
                target=str(output_path),
                stylesheets=[css_doc],
                font_config=self.font_config
            )
            
            logger.info(f"PDF generated successfully: {output_path}")
        
        except Exception as e:
            logger.error(f"WeasyPrint PDF generation failed: {e}")
            raise PDFGenerationError(f"PDF generation failed: {e}")
    
    def _get_pdf_url(self, filename: str) -> str:
        """Generate public URL for accessing the PDF file."""
        
        # In production, this would be a signed S3 URL or CDN URL
        # For development, we'll use a local file path or server URL
        
        if self.settings.environment == "production":
            # Production: Use cloud storage URL
            base_url = getattr(self.settings, 'cdn_base_url', 'https://api.finguard.co.ke')
            return f"{base_url}/storage/invoices/{filename}"
        else:
            # Development: Use local server URL
            return f"http://localhost:8000/storage/invoices/{filename}"
    
    def generate_invoice_pdf(self, invoice: Invoice) -> str:
        """
        Generate PDF for an invoice and return the file URL.
        
        Args:
            invoice: Invoice model instance with all required data
            
        Returns:
            PDF file URL for accessing the generated document
            
        Raises:
            PDFGenerationError: If PDF generation fails
        """
        
        try:
            logger.info(f"Generating PDF for invoice {invoice.invoice_number}")
            
            # Render HTML content
            html_content = self._render_html(invoice)
            
            # Generate unique filename
            pdf_filename = self._generate_pdf_filename(invoice)
            pdf_path = self.pdf_storage_dir / pdf_filename
            
            # Create PDF file
            self._create_pdf_from_html(html_content, pdf_path)
            
            # Verify file was created
            if not pdf_path.exists() or pdf_path.stat().st_size == 0:
                raise PDFGenerationError("Generated PDF file is empty or missing")
            
            # Generate public URL
            pdf_url = self._get_pdf_url(pdf_filename)
            
            logger.info(f"PDF generated for invoice {invoice.invoice_number}: {pdf_url}")
            return pdf_url
        
        except Exception as e:
            if isinstance(e, PDFGenerationError):
                raise
            
            logger.error(f"Unexpected error generating PDF for invoice {invoice.invoice_number}: {e}")
            raise PDFGenerationError(f"PDF generation failed: {str(e)}")
    
    def regenerate_pdf(self, invoice: Invoice) -> str:
        """Regenerate PDF for an existing invoice."""
        
        logger.info(f"Regenerating PDF for invoice {invoice.invoice_number}")
        return self.generate_invoice_pdf(invoice)
    
    def delete_pdf(self, pdf_url: str) -> bool:
        """Delete PDF file from storage."""
        
        try:
            # Extract filename from URL
            filename = pdf_url.split('/')[-1]
            pdf_path = self.pdf_storage_dir / filename
            
            if pdf_path.exists():
                pdf_path.unlink()
                logger.info(f"Deleted PDF file: {filename}")
                return True
            
            logger.warning(f"PDF file not found for deletion: {filename}")
            return False
        
        except Exception as e:
            logger.error(f"Failed to delete PDF file: {e}")
            return False
    
    def validate_pdf_storage(self) -> Dict[str, Any]:
        """Validate PDF storage configuration and accessibility."""
        
        validation_result = {
            "storage_dir_exists": self.pdf_storage_dir.exists(),
            "storage_dir_writable": os.access(self.pdf_storage_dir, os.W_OK),
            "template_accessible": False,
            "weasyprint_working": False
        }
        
        # Test template loading
        try:
            template = self._get_template()
            validation_result["template_accessible"] = True
        except Exception as e:
            logger.error(f"Template validation failed: {e}")
        
        # Test WeasyPrint functionality
        try:
            test_html = "<html><body><h1>Test</h1></body></html>"
            HTML(string=test_html)
            validation_result["weasyprint_working"] = True
        except Exception as e:
            logger.error(f"WeasyPrint validation failed: {e}")
        
        return validation_result


# Global service instance
_pdf_service_instance: Optional[InvoicePDFService] = None


def get_pdf_service() -> InvoicePDFService:
    """Get singleton instance of Invoice PDF Service."""
    global _pdf_service_instance
    
    if _pdf_service_instance is None:
        _pdf_service_instance = InvoicePDFService()
    
    return _pdf_service_instance