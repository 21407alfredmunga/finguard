"""
Account Schemas
Pydantic models for business account data validation and serialization
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, validator
import uuid

from ..models.account import Currency


class AccountBase(BaseModel):
    """Base account schema with common fields"""
    
    business_name: str
    business_type: Optional[str] = None
    currency: Currency = Currency.KES
    mpesa_shortcode: Optional[str] = None
    mpesa_account_reference: Optional[str] = None


class AccountCreate(AccountBase):
    """Schema for creating a new account"""
    
    @validator("business_name")
    def validate_business_name(cls, v):
        """Validate business name"""
        if not v or len(v.strip()) < 2:
            raise ValueError("Business name must be at least 2 characters long")
        if len(v) > 200:
            raise ValueError("Business name must be less than 200 characters")
        return v.strip()
    
    @validator("mpesa_shortcode")
    def validate_mpesa_shortcode(cls, v):
        """Validate M-Pesa shortcode format"""
        if v is None:
            return v
        
        # Remove any non-digits
        shortcode = ''.join(filter(str.isdigit, v))
        
        # M-Pesa shortcodes are typically 5-7 digits
        if len(shortcode) < 4 or len(shortcode) > 7:
            raise ValueError("M-Pesa shortcode must be 4-7 digits long")
        
        return shortcode
    
    @validator("mpesa_account_reference")
    def validate_account_reference(cls, v):
        """Validate account reference"""
        if v is not None and len(v) > 50:
            raise ValueError("Account reference must be less than 50 characters")
        return v


class AccountUpdate(BaseModel):
    """Schema for updating account information"""
    
    business_name: Optional[str] = None
    business_type: Optional[str] = None
    mpesa_shortcode: Optional[str] = None
    mpesa_account_reference: Optional[str] = None
    
    @validator("business_name")
    def validate_business_name(cls, v):
        """Validate business name if provided"""
        if v is not None and (not v or len(v.strip()) < 2):
            raise ValueError("Business name must be at least 2 characters long")
        if v is not None and len(v) > 200:
            raise ValueError("Business name must be less than 200 characters")
        return v.strip() if v else v
    
    @validator("mpesa_shortcode")
    def validate_mpesa_shortcode(cls, v):
        """Validate M-Pesa shortcode format if provided"""
        if v is None:
            return v
        
        # Remove any non-digits
        shortcode = ''.join(filter(str.isdigit, v))
        
        # M-Pesa shortcodes are typically 5-7 digits
        if len(shortcode) < 4 or len(shortcode) > 7:
            raise ValueError("M-Pesa shortcode must be 4-7 digits long")
        
        return shortcode


class AccountResponse(AccountBase):
    """Schema for account response"""
    
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    transaction_count: Optional[int] = 0
    
    class Config:
        orm_mode = True
        schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "user_id": "550e8400-e29b-41d4-a716-446655440001",
                "business_name": "Mama Mboga Shop",
                "business_type": "retail",
                "currency": "KES",
                "mpesa_shortcode": "174379",
                "mpesa_account_reference": "shop001",
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-01T00:00:00Z",
                "transaction_count": 15
            }
        }


class AccountWithStats(AccountResponse):
    """Account response with additional statistics"""
    
    total_inbound: Optional[float] = 0.0
    total_outbound: Optional[float] = 0.0
    last_transaction_date: Optional[datetime] = None
    
    class Config:
        orm_mode = True


class AccountList(BaseModel):
    """Schema for paginated account list"""
    
    accounts: List[AccountResponse]
    total: int
    page: int
    per_page: int
    pages: int
    
    class Config:
        schema_extra = {
            "example": {
                "accounts": [],
                "total": 10,
                "page": 1,
                "per_page": 20,
                "pages": 1
            }
        }