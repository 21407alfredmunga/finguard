"""
Transaction Model
Defines M-Pesa transaction records from Daraja API callbacks
"""

import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric, Enum, Index, JSON
from sqlalchemy.orm import relationship
import enum

from ..db import Base
from .types import GUID


class TransactionType(str, enum.Enum):
    """M-Pesa transaction types supported by Daraja API"""
    C2B = "C2B"                    # Customer to Business (PayBill/BuyGoods)
    B2C = "B2C"                    # Business to Customer  
    LIPA_NA_MPESA = "LipaNaMpesa"  # Lipa Na M-Pesa Online (STK Push)
    B2B = "B2B"                    # Business to Business
    REVERSAL = "Reversal"          # Transaction reversal


class TransactionStatus(str, enum.Enum):
    """Transaction processing status"""
    PENDING = "pending"      # Just received, being processed
    COMPLETED = "completed"  # Successfully processed
    FAILED = "failed"        # Processing failed
    DUPLICATE = "duplicate"  # Duplicate transaction ignored


class Transaction(Base):
    """
    M-Pesa transaction record from Daraja API webhooks
    
    Stores normalized transaction data along with raw payload for reprocessing.
    Ensures idempotency through unique M-Pesa transaction ID constraint.
    """
    
    __tablename__ = "transactions"
    
    # Primary key
    id = Column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
        comment="Internal transaction identifier"
    )
    
    # Foreign key to account
    account_id = Column(
        GUID(),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Account this transaction belongs to"
    )
    
    # M-Pesa Transaction Data (from Daraja callback)
    mpesa_transaction_id = Column(
        String(50),
        nullable=False,
        unique=True,  # Ensures idempotency
        index=True,
        comment="Unique M-Pesa transaction ID (TransID from callback)"
    )
    
    transaction_type = Column(
        Enum(TransactionType),
        nullable=False,
        comment="Type of M-Pesa transaction"
    )
    
    # Financial Details
    amount = Column(
        Numeric(precision=15, scale=2),  # Support up to 999,999,999,999.99
        nullable=False,
        comment="Transaction amount"
    )
    
    # Participant Information
    phone = Column(
        String(20),
        nullable=False,
        comment="Phone number of the customer/sender"
    )
    
    party_name = Column(
        String(200),
        nullable=True,
        comment="Name of the transaction participant"
    )
    
    # Transaction Metadata
    reference = Column(
        String(100),
        nullable=True,
        comment="Account reference/bill reference number"
    )
    
    transaction_time = Column(
        DateTime,
        nullable=False,
        comment="When the M-Pesa transaction occurred"
    )
    
    # Processing Status
    status = Column(
        Enum(TransactionStatus),
        nullable=False,
        default=TransactionStatus.PENDING,
        comment="Processing status of this transaction"
    )
    
    # Raw Data Storage (for reprocessing and debugging)
    raw_payload = Column(
        JSON,
        nullable=False,
        comment="Complete raw JSON payload from Daraja callback"
    )
    
    # Additional M-Pesa Fields (commonly used)
    business_short_code = Column(
        String(10),
        nullable=True,
        comment="M-Pesa business shortcode"
    )
    
    invoice_number = Column(
        String(50),
        nullable=True,
        comment="Invoice number if applicable"
    )
    
    org_account_balance = Column(
        Numeric(precision=15, scale=2),
        nullable=True,
        comment="Organization account balance after transaction"
    )
    
    third_party_trans_id = Column(
        String(50),
        nullable=True,
        comment="Third party transaction ID"
    )
    
    # Timestamps
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        comment="When this record was created"
    )
    
    processed_at = Column(
        DateTime,
        nullable=True,
        comment="When this transaction was processed"
    )
    
    # Relationships
    account = relationship(
        "Account",
        back_populates="transactions"
    )
    
    matched_invoice = relationship(
        "Invoice",
        back_populates="matched_transaction"
    )
    
    # Database indexes for performance
    __table_args__ = (
        Index('idx_transactions_account_time', 'account_id', 'transaction_time'),
        Index('idx_transactions_phone_time', 'phone', 'transaction_time'),
        Index('idx_transactions_type_status', 'transaction_type', 'status'),
    )
    
    def __repr__(self) -> str:
        return (f"<Transaction(id={self.id}, mpesa_id={self.mpesa_transaction_id}, "
                f"amount={self.amount}, type={self.transaction_type})>")
    
    def __str__(self) -> str:
        return f"KES {self.amount} from {self.phone} ({self.mpesa_transaction_id})"
    
    @property
    def amount_formatted(self) -> str:
        """Format amount as currency string"""
        return f"KES {self.amount:,.2f}"
    
    @property
    def is_inbound(self) -> bool:
        """Check if this is an inbound transaction (money coming in)"""
        return self.transaction_type in [TransactionType.C2B, TransactionType.LIPA_NA_MPESA]
    
    @property
    def is_outbound(self) -> bool:
        """Check if this is an outbound transaction (money going out)"""
        return self.transaction_type in [TransactionType.B2C, TransactionType.B2B]
    
    def mark_as_processed(self):
        """Mark transaction as successfully processed"""
        self.status = TransactionStatus.COMPLETED
        self.processed_at = datetime.utcnow()
    
    def mark_as_failed(self):
        """Mark transaction as failed"""
        self.status = TransactionStatus.FAILED
        self.processed_at = datetime.utcnow()
    
    def mark_as_duplicate(self):
        """Mark transaction as duplicate"""
        self.status = TransactionStatus.DUPLICATE
        self.processed_at = datetime.utcnow()