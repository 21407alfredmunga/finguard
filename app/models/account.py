"""
Account Model  
Defines business accounts/companies that users can manage
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from ..db import Base


class Currency(str, enum.Enum):
    """Supported currencies for accounts"""
    KES = "KES"  # Kenyan Shilling (primary)
    USD = "USD"  # US Dollar
    EUR = "EUR"  # Euro


class Account(Base):
    """
    Business account/company model
    
    Represents a business entity that a user owns/manages.
    Each account can have multiple M-Pesa transactions.
    Users with 'owner' role can create accounts, 'accountant' role can view/manage existing ones.
    """
    
    __tablename__ = "accounts"
    
    # Primary key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique account identifier"
    )
    
    # Foreign key to user (account owner)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owner of this business account"
    )
    
    # Business Information
    business_name = Column(
        String(200),
        nullable=False,
        comment="Legal business name"
    )
    
    business_type = Column(
        String(100),
        nullable=True,
        comment="Type of business (retail, restaurant, etc.)"
    )
    
    # Financial Configuration
    currency = Column(
        Enum(Currency),
        nullable=False,
        default=Currency.KES,
        comment="Primary currency for this account"
    )
    
    # M-Pesa Configuration
    mpesa_shortcode = Column(
        String(10),
        nullable=True,
        comment="M-Pesa business shortcode (paybill/till number)"
    )
    
    mpesa_account_reference = Column(
        String(50),
        nullable=True,
        comment="Default account reference for M-Pesa transactions"
    )
    
    # Timestamps
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        comment="Account creation timestamp"
    )
    
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        comment="Last update timestamp"
    )
    
    # Relationships
    owner = relationship(
        "User",
        back_populates="accounts"
    )
    
    transactions = relationship(
        "Transaction",
        back_populates="account",
        cascade="all, delete-orphan",
        lazy="dynamic",
        order_by="Transaction.timestamp.desc()"  # Order by most recent first
    )
    
    invoices = relationship(
        "Invoice",
        back_populates="account",
        cascade="all, delete-orphan",
        lazy="dynamic",
        order_by="Invoice.created_at.desc()"
    )
    
    def __repr__(self) -> str:
        return f"<Account(id={self.id}, business_name={self.business_name})>"
    
    def __str__(self) -> str:
        return f"{self.business_name} ({self.currency})"
    
    @property
    def recent_transactions(self):
        """Get the 10 most recent transactions for this account"""
        return self.transactions.limit(10).all()
    
    @property
    def transaction_count(self) -> int:
        """Get total number of transactions for this account"""
        return self.transactions.count()