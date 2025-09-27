"""
User Model
Defines the users table structure and relationships
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Enum, Boolean, ForeignKey
from sqlalchemy.orm import relationship
import enum

from ..db import Base
from .types import GUID


class UserRole(str, enum.Enum):
    """User roles enum for role-based access control"""
    OWNER = "owner"
    ACCOUNTANT = "accountant"


class User(Base):
    """
    User model for authentication and authorization
    
    Stores user credentials, profile information, and role-based permissions.
    Each user can have multiple accounts (businesses) but only one role per user.
    """
    
    __tablename__ = "users"
    
    # Primary key - using UUID for better security and scalability
    id = Column(
        GUID(), 
        primary_key=True, 
        default=uuid.uuid4,
        comment="Unique user identifier"
    )
    
    # Profile Information
    name = Column(
        String(100), 
        nullable=False,
        comment="User's full name"
    )
    
    email = Column(
        String(255), 
        unique=True, 
        nullable=False, 
        index=True,
        comment="User's email address (unique login identifier)"
    )
    
    phone = Column(
        String(20),
        nullable=True,
        comment="User's phone number (for M-Pesa notifications)"
    )
    
    # Authentication
    hashed_password = Column(
        String(255), 
        nullable=False,
        comment="Bcrypt hashed password"
    )
    
    # Authorization
    role = Column(
        Enum(UserRole),
        nullable=False,
        default=UserRole.OWNER,
        comment="User role for access control"
    )
    
    # Account Status
    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether user account is active"
    )
    
    is_verified = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="Whether user email is verified"
    )
    
    # Timestamps
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        comment="Account creation timestamp"
    )
    
    last_login = Column(
        DateTime,
        nullable=True,
        comment="Last successful login timestamp"
    )
    
    # Relationships
    accounts = relationship(
        "Account",
        back_populates="owner",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )
    
    # Audit logs for this user
    audit_logs = relationship(
        "AuditLog",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"
    
    def __str__(self) -> str:
        return f"{self.name} ({self.email})"


class AuditLog(Base):
    """
    Audit log for tracking user actions and login attempts
    Essential for security monitoring and compliance
    """
    
    __tablename__ = "audit_logs"
    
    id = Column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4
    )
    
    user_id = Column(
        GUID(),
        ForeignKey("users.id"),
        nullable=True,  # Can be null for failed login attempts
        comment="User who performed the action"
    )
    
    action = Column(
        String(100),
        nullable=False,
        comment="Action performed (login, logout, transaction_view, etc.)"
    )
    
    resource = Column(
        String(255),
        nullable=True,
        comment="Resource accessed or modified"
    )
    
    ip_address = Column(
        String(45),  # IPv6 compatible
        nullable=True,
        comment="IP address of the request"
    )
    
    user_agent = Column(
        String(512),
        nullable=True,
        comment="User agent string from request"
    )
    
    success = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether the action was successful"
    )
    
    details = Column(
        String(1000),
        nullable=True,
        comment="Additional details about the action"
    )
    
    timestamp = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
        comment="When the action occurred"
    )
    
    # Relationship to user (if authenticated)
    user = relationship("User", back_populates="audit_logs")
    
    def __repr__(self) -> str:
        return f"<AuditLog(action={self.action}, user_id={self.user_id}, success={self.success})>"