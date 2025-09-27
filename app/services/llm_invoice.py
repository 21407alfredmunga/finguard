"""
LLM Invoice Service for FinGuard Lite.

Uses Google Gemini SDK to generate structured invoice data from free-text prompts.
Includes validation, error handling, and invoice number generation.
"""

import json
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging

import google.generativeai as genai
from pydantic import ValidationError

from app.config import get_settings
from app.schemas.invoice import InvoiceSchema, InvoiceItem, LLMInvoiceGenerationError


logger = logging.getLogger(__name__)


class LLMInvoiceService:
    """Service for generating invoices from free-text using Gemini LLM."""
    
    def __init__(self):
        """Initialize Gemini client with API key from settings."""
        settings = get_settings()
        
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        
        genai.configure(api_key=settings.GEMINI_API_KEY)
        
        # Use Gemini 1.5 Flash for cost-effectiveness
        self.model = genai.GenerativeModel("gemini-1.5-flash")
        
        logger.info("LLM Invoice Service initialized with Gemini 1.5 Flash")
    
    def generate_invoice_number(self, prefix: str = "INV") -> str:
        """Generate unique invoice number with timestamp."""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"{prefix}-{timestamp}"
    
    def _create_generation_prompt(self, user_prompt: str) -> str:
        """Create structured prompt for Gemini to generate invoice JSON."""
        
        system_prompt = """
        You are an expert invoice generator for Kenyan businesses. Generate a valid JSON invoice from the user's description.
        
        STRICT REQUIREMENTS:
        1. Output ONLY valid JSON - no markdown, no explanations, no code blocks
        2. All amounts must be in Kenyan Shillings (KES)
        3. Phone numbers must be in format 254XXXXXXXXX (Kenya country code)
        4. Invoice numbers should follow format INV-YYYYMMDDHHMMSS
        5. Due dates should be reasonable (7-30 days from today)
        6. Calculate subtotals and totals accurately
        
        JSON Schema (follow exactly):
        {
            "invoice_number": "INV-20251227142530",
            "client_name": "Full Name",
            "client_phone": "254712345678",
            "items": [
                {
                    "description": "Item description",
                    "quantity": 1,
                    "unit_price": 1000.00,
                    "subtotal": 1000.00
                }
            ],
            "subtotal": 1000.00,
            "tax": 160.00,
            "total": 1160.00,
            "due_date": "2025-01-26T23:59:59",
            "notes": "Additional notes if any"
        }
        
        CALCULATION RULES:
        - subtotal = sum of all item subtotals
        - item subtotal = quantity × unit_price
        - tax = 16% of subtotal (Kenya VAT) unless specified otherwise
        - total = subtotal + tax
        
        Current date for reference: """ + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        full_prompt = f"{system_prompt}\n\nUser Request: {user_prompt}\n\nGenerate invoice JSON:"
        
        return full_prompt
    
    def _clean_json_response(self, response_text: str) -> str:
        """Clean LLM response to extract valid JSON."""
        
        # Remove markdown code blocks
        response_text = re.sub(r'```json\s*', '', response_text, flags=re.IGNORECASE)
        response_text = re.sub(r'```\s*', '', response_text)
        
        # Remove leading/trailing whitespace
        response_text = response_text.strip()
        
        # Try to extract JSON object from response
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            return json_match.group()
        
        return response_text
    
    def _validate_phone_number(self, phone: str) -> str:
        """Validate and format Kenyan phone number."""
        
        # Remove all non-digits
        phone_digits = re.sub(r'\D', '', phone)
        
        # Convert common Kenyan formats to 254 format
        if phone_digits.startswith('0'):
            phone_digits = '254' + phone_digits[1:]
        elif phone_digits.startswith('7') and len(phone_digits) == 9:
            phone_digits = '254' + phone_digits
        elif phone_digits.startswith('1') and len(phone_digits) == 9:
            phone_digits = '254' + phone_digits
        
        # Validate final format
        if not re.match(r'^254[0-9]{9}$', phone_digits):
            raise ValueError(f"Invalid Kenyan phone number format: {phone}")
        
        return phone_digits
    
    def _post_process_invoice_data(self, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        """Post-process and validate invoice data from LLM."""
        
        # Ensure invoice number exists
        if not invoice_data.get('invoice_number'):
            invoice_data['invoice_number'] = self.generate_invoice_number()
        
        # Validate and format phone number
        if 'client_phone' in invoice_data:
            invoice_data['client_phone'] = self._validate_phone_number(
                invoice_data['client_phone']
            )
        
        # Ensure due_date is datetime string
        if 'due_date' in invoice_data:
            due_date = invoice_data['due_date']
            if isinstance(due_date, str):
                # Try to parse various date formats
                try:
                    if 'T' not in due_date:
                        # Add time component if missing
                        due_date += 'T23:59:59'
                    datetime.fromisoformat(due_date.replace('Z', '+00:00'))
                except ValueError:
                    # Default to 14 days from now
                    invoice_data['due_date'] = (
                        datetime.now() + timedelta(days=14)
                    ).isoformat()
        else:
            # Default due date if not provided
            invoice_data['due_date'] = (
                datetime.now() + timedelta(days=14)
            ).isoformat()
        
        # Validate calculations
        items = invoice_data.get('items', [])
        calculated_subtotal = sum(
            item.get('quantity', 0) * item.get('unit_price', 0) 
            for item in items
        )
        
        # Update subtotal if incorrect
        invoice_data['subtotal'] = calculated_subtotal
        
        # Calculate tax (16% VAT by default)
        if 'tax' not in invoice_data:
            invoice_data['tax'] = round(calculated_subtotal * 0.16, 2)
        
        # Update total
        invoice_data['total'] = invoice_data['subtotal'] + invoice_data['tax']
        
        # Update item subtotals
        for item in items:
            if 'quantity' in item and 'unit_price' in item:
                item['subtotal'] = item['quantity'] * item['unit_price']
        
        return invoice_data
    
    async def generate_invoice_from_prompt(self, prompt: str) -> InvoiceSchema:
        """
        Generate structured invoice data from free-text prompt using Gemini.
        
        Args:
            prompt: Free-text description of invoice requirements
            
        Returns:
            Validated InvoiceSchema object
            
        Raises:
            LLMInvoiceGenerationError: If generation or validation fails
        """
        
        try:
            logger.info(f"Generating invoice from prompt: {prompt[:100]}...")
            
            # Create structured prompt
            generation_prompt = self._create_generation_prompt(prompt)
            
            # Call Gemini API
            response = self.model.generate_content(generation_prompt)
            
            if not response.text:
                raise LLMInvoiceGenerationError(
                    "Empty response from Gemini API",
                    prompt,
                    ""
                )
            
            logger.info("Received response from Gemini API")
            
            # Clean and parse JSON response
            clean_response = self._clean_json_response(response.text)
            
            try:
                invoice_data = json.loads(clean_response)
            except json.JSONDecodeError as e:
                raise LLMInvoiceGenerationError(
                    f"Invalid JSON response from Gemini: {e}",
                    prompt,
                    response.text
                )
            
            # Post-process the data
            invoice_data = self._post_process_invoice_data(invoice_data)
            
            # Validate with Pydantic schema
            try:
                validated_invoice = InvoiceSchema(**invoice_data)
                logger.info(f"Successfully generated invoice: {validated_invoice.invoice_number}")
                return validated_invoice
            
            except ValidationError as e:
                logger.error(f"Invoice validation failed: {e}")
                raise LLMInvoiceGenerationError(
                    f"Generated invoice data validation failed: {e}",
                    prompt,
                    json.dumps(invoice_data, indent=2)
                )
        
        except Exception as e:
            if isinstance(e, LLMInvoiceGenerationError):
                raise
            
            logger.error(f"Unexpected error in invoice generation: {e}")
            raise LLMInvoiceGenerationError(
                f"Invoice generation failed: {str(e)}",
                prompt,
                getattr(e, 'response_text', None)
            )
    
    def extract_invoice_info_from_text(self, text: str) -> Dict[str, Any]:
        """
        Extract basic invoice information from text using regex patterns.
        Fallback method if LLM fails.
        """
        
        info = {}
        
        # Extract amounts (KES/KSh patterns)
        amount_patterns = [
            r'(?:KES|KSh|ksh)\s*([0-9,]+(?:\.[0-9]{2})?)',
            r'([0-9,]+(?:\.[0-9]{2})?)\s*(?:KES|KSh|ksh)',
            r'([0-9,]+(?:\.[0-9]{2})?)\s*shillings?'
        ]
        
        for pattern in amount_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount_str = match.group(1).replace(',', '')
                try:
                    info['total'] = float(amount_str)
                    break
                except ValueError:
                    continue
        
        # Extract phone numbers
        phone_pattern = r'(?:254|0)[0-9]{9}'
        phone_match = re.search(phone_pattern, text)
        if phone_match:
            info['client_phone'] = self._validate_phone_number(phone_match.group())
        
        # Extract names (basic pattern)
        name_patterns = [
            r'(?:to|for)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)',
            r'([A-Z][a-z]+\s+[A-Z][a-z]+)(?:\s+254)',
        ]
        
        for pattern in name_patterns:
            match = re.search(pattern, text)
            if match:
                info['client_name'] = match.group(1).strip()
                break
        
        return info


# Global service instance
_invoice_service_instance: Optional[LLMInvoiceService] = None


def get_invoice_service() -> LLMInvoiceService:
    """Get singleton instance of LLM Invoice Service."""
    global _invoice_service_instance
    
    if _invoice_service_instance is None:
        _invoice_service_instance = LLMInvoiceService()
    
    return _invoice_service_instance