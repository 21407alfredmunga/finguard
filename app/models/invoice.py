"""
Invoice model for FinGuard Lite Invoice Engine.

Handles invoice data storage with PostgreSQL JSONB for line items.
"""

from datetime import datetime
from enum import Enum as PyEnum
from typing import List, Optional
import uuid

from sqlalchemy import (
    Column, String, Numeric, DateTime, ForeignKey, Enum, Text, JSON
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base


class InvoiceStatus(PyEnum):
    """Invoice status enumeration."""
    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"
    OVERDUE = "overdue"


class Invoice(Base):
    """Invoice model with JSONB line items and M-Pesa reconciliation."""
    
    __tablename__ = "invoices"
    
    # Primary fields
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    
    # Invoice identification
    invoice_number = Column(String(50), unique=True, nullable=False, index=True)
    
    # Client information
    client_name = Column(String(255), nullable=False)
    client_phone = Column(String(20), nullable=False)
    
    # Line items stored as JSONB array
    # Format: [{"description": str, "quantity": int, "unit_price": float, "subtotal": float}]
    items = Column(JSONB, nullable=False)
    
    # Financial totals
    subtotal = Column(Numeric(15, 2), nullable=False)
    tax = Column(Numeric(15, 2), nullable=False, default=0.00)
    total = Column(Numeric(15, 2), nullable=False)
    
    # Invoice status and tracking
    status = Column(Enum(InvoiceStatus), nullable=False, default=InvoiceStatus.DRAFT)
    pdf_url = Column(Text, nullable=True)  # URL to generated PDF
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    due_date = Column(DateTime(timezone=True), nullable=False)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    
    # Reconciliation fields
    matched_transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=True)
    reconciled_at = Column(DateTime(timezone=True), nullable=True)
    
    # Additional metadata
    notes = Column(Text, nullable=True)
    
    # Relationships
    account = relationship("Account", back_populates="invoices")
    matched_transaction = relationship("Transaction", back_populates="matched_invoice")
    
    def __repr__(self):
        return f"<Invoice {self.invoice_number} - {self.client_name} - {self.total}>"
    
    @property
    def is_overdue(self) -> bool:
        """Check if invoice is overdue."""
        return (
            self.status != InvoiceStatus.PAID and 
            self.due_date < datetime.now(self.due_date.tzinfo)
        )
    
    @property
    def days_until_due(self) -> int:
        """Calculate days until due date."""
        if self.status == InvoiceStatus.PAID:
            return 0
        
        delta = self.due_date.date() - datetime.now(self.due_date.tzinfo).date()
        return delta.days
    
    def mark_as_paid(self, transaction_id: Optional[uuid.UUID] = None):
        """Mark invoice as paid and optionally link transaction."""
        self.status = InvoiceStatus.PAID
        self.paid_at = datetime.utcnow()
        
        if transaction_id:
            self.matched_transaction_id = transaction_id
            self.reconciled_at = datetime.utcnow()