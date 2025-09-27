"""
Invoice Pydantic schemas for FinGuard Lite Invoice Engine.

Handles validation and serialization for invoice data, free-text prompts,
and structured invoice creation.
"""

from datetime import datetime, date
from decimal import Decimal
from typing import List, Optional
from enum import Enum
import uuid

from pydantic import BaseModel, Field, validator, ConfigDict
from pydantic_core import ValidationError


class InvoiceStatusEnum(str, Enum):
    """Invoice status enumeration for API responses."""
    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"
    OVERDUE = "overdue"


class InvoiceItem(BaseModel):
    """Individual line item in an invoice."""
    
    model_config = ConfigDict(from_attributes=True)
    
    description: str = Field(..., min_length=1, max_length=500, description="Item description")
    quantity: int = Field(..., gt=0, description="Quantity of items")
    unit_price: float = Field(..., gt=0, description="Price per unit in KES")
    subtotal: float = Field(..., gt=0, description="Line item subtotal (qty * unit_price)")
    
    @validator('subtotal')
    def validate_subtotal(cls, v, values):
        """Ensure subtotal matches quantity * unit_price."""
        if 'quantity' in values and 'unit_price' in values:
            expected = values['quantity'] * values['unit_price']
            if abs(v - expected) > 0.01:  # Allow small floating point differences
                raise ValueError(f"Subtotal {v} doesn't match quantity * unit_price = {expected}")
        return v


class InvoiceSchema(BaseModel):
    """Complete invoice data schema for LLM generation and API validation."""
    
    model_config = ConfigDict(from_attributes=True)
    
    invoice_number: str = Field(..., min_length=1, max_length=50, description="Unique invoice number")
    client_name: str = Field(..., min_length=1, max_length=255, description="Client/customer name")
    client_phone: str = Field(..., regex=r"^254[0-9]{9}$", description="Client phone number (254XXXXXXXXX)")
    
    items: List[InvoiceItem] = Field(..., min_items=1, description="Invoice line items")
    
    subtotal: float = Field(..., gt=0, description="Total before tax")
    tax: float = Field(default=0.00, ge=0, description="Tax amount in KES")
    total: float = Field(..., gt=0, description="Final total amount")
    
    due_date: datetime = Field(..., description="Invoice due date and time")
    notes: Optional[str] = Field(None, max_length=1000, description="Additional invoice notes")
    
    @validator('due_date')
    def validate_due_date(cls, v):
        """Ensure due date is not in the past."""
        if v.date() < date.today():
            raise ValueError("Due date cannot be in the past")
        return v
    
    @validator('total')
    def validate_total(cls, v, values):
        """Ensure total matches subtotal + tax."""
        if 'subtotal' in values and 'tax' in values:
            expected = values['subtotal'] + values['tax']
            if abs(v - expected) > 0.01:
                raise ValueError(f"Total {v} doesn't match subtotal + tax = {expected}")
        return v
    
    @validator('subtotal')
    def validate_subtotal_against_items(cls, v, values):
        """Ensure subtotal matches sum of item subtotals."""
        if 'items' in values:
            expected = sum(item.subtotal for item in values['items'])
            if abs(v - expected) > 0.01:
                raise ValueError(f"Subtotal {v} doesn't match sum of items = {expected}")
        return v


class FreeTextInvoiceRequest(BaseModel):
    """Request schema for free-text invoice generation."""
    
    prompt: str = Field(
        ..., 
        min_length=10, 
        max_length=2000,
        description="Natural language description of the invoice to generate"
    )
    
    # Optional overrides
    account_id: Optional[uuid.UUID] = Field(None, description="Override account ID")
    
    class Config:
        json_schema_extra = {
            "example": {
                "prompt": "Create invoice for KSh 12,000 to Mary Wanjiku (254712345678) for 10 bags of maize at KSh 1,200 each, due in 14 days"
            }
        }


class StructuredInvoiceRequest(InvoiceSchema):
    """Request schema for structured invoice creation (extends InvoiceSchema)."""
    
    account_id: Optional[uuid.UUID] = Field(None, description="Override account ID")
    
    class Config:
        json_schema_extra = {
            "example": {
                "invoice_number": "INV-001",
                "client_name": "Mary Wanjiku",
                "client_phone": "254712345678",
                "items": [
                    {
                        "description": "Maize bags (90kg each)",
                        "quantity": 10,
                        "unit_price": 1200.00,
                        "subtotal": 12000.00
                    }
                ],
                "subtotal": 12000.00,
                "tax": 0.00,
                "total": 12000.00,
                "due_date": "2025-10-11T23:59:59",
                "notes": "Payment via M-Pesa preferred"
            }
        }


class InvoiceResponse(BaseModel):
    """Complete invoice response schema."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    account_id: uuid.UUID
    
    invoice_number: str
    client_name: str
    client_phone: str
    
    items: List[InvoiceItem]
    
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    
    status: InvoiceStatusEnum
    pdf_url: Optional[str] = None
    
    created_at: datetime
    updated_at: Optional[datetime] = None
    due_date: datetime
    paid_at: Optional[datetime] = None
    
    matched_transaction_id: Optional[uuid.UUID] = None
    reconciled_at: Optional[datetime] = None
    
    notes: Optional[str] = None
    
    # Computed properties
    is_overdue: bool = False
    days_until_due: int = 0


class InvoiceListResponse(BaseModel):
    """Paginated invoice list response."""
    
    invoices: List[InvoiceResponse]
    total: int
    page: int
    per_page: int
    has_next: bool
    has_prev: bool


class InvoiceReconcileRequest(BaseModel):
    """Request schema for invoice reconciliation."""
    
    invoice_id: uuid.UUID = Field(..., description="Invoice ID to reconcile")
    transaction_id: Optional[uuid.UUID] = Field(None, description="Specific transaction ID (optional for auto-match)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "invoice_id": "123e4567-e89b-12d3-a456-426614174000",
                "transaction_id": "789e0123-e45f-67g8-h901-234567890abc"
            }
        }


class InvoiceReconcileResponse(BaseModel):
    """Response schema for invoice reconciliation."""
    
    success: bool
    message: str
    invoice_id: uuid.UUID
    transaction_id: Optional[uuid.UUID] = None
    matched_amount: Optional[Decimal] = None
    reconciled_at: Optional[datetime] = None


class LLMInvoiceGenerationError(Exception):
    """Custom exception for LLM invoice generation failures."""
    
    def __init__(self, message: str, original_prompt: str, llm_response: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.original_prompt = original_prompt
        self.llm_response = llm_response