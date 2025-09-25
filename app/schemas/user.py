"""
User Schemas
Pydantic models for user data validation and serialization
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, EmailStr, validator
import uuid

from ..models.user import UserRole


class UserBase(BaseModel):
    """Base user schema with common fields"""
    
    name: str
    email: EmailStr
    phone: Optional[str] = None
    role: UserRole = UserRole.OWNER


class UserCreate(UserBase):
    """Schema for creating a new user"""
    
    password: str
    
    @validator("password")
    def validate_password(cls, v):
        """Validate password strength"""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if len(v) > 128:
            raise ValueError("Password must be less than 128 characters")
        return v


class UserUpdate(BaseModel):
    """Schema for updating user information"""
    
    name: Optional[str] = None
    phone: Optional[str] = None
    
    @validator("name")
    def validate_name(cls, v):
        """Validate user name if provided"""
        if v is not None and (not v or len(v.strip()) < 2):
            raise ValueError("Name must be at least 2 characters long")
        if v is not None and len(v) > 100:
            raise ValueError("Name must be less than 100 characters")
        return v.strip() if v else v
    
    @validator("phone")
    def validate_phone(cls, v):
        """Validate Kenyan phone number format if provided"""
        if v is None:
            return v
        
        # Remove any whitespace or special characters
        phone = ''.join(filter(str.isdigit, v))
        
        # Check for valid Kenyan phone number formats
        if phone.startswith('254'):
            # International format: 254xxxxxxxxx
            if len(phone) != 12:
                raise ValueError("Invalid Kenyan phone number format")
        elif phone.startswith('0'):
            # Local format: 0xxxxxxxxx -> convert to international
            if len(phone) != 10:
                raise ValueError("Invalid Kenyan phone number format")
            phone = '254' + phone[1:]
        else:
            raise ValueError("Phone number must start with 254 or 0")
        
        return phone


class UserResponse(UserBase):
    """Schema for user response (excludes sensitive data)"""
    
    id: uuid.UUID
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login: Optional[datetime] = None
    account_count: Optional[int] = 0  # Number of accounts user owns
    
    class Config:
        orm_mode = True
        schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "John Doe",
                "email": "john@example.com",
                "phone": "254712345678",
                "role": "owner",
                "is_active": True,
                "is_verified": True,
                "created_at": "2023-01-01T00:00:00Z",
                "last_login": "2023-01-01T12:00:00Z",
                "account_count": 2
            }
        }


class UserProfile(UserResponse):
    """Extended user profile with additional information"""
    
    recent_login_count: Optional[int] = 0
    total_transactions: Optional[int] = 0
    
    class Config:
        orm_mode = True


class UserList(BaseModel):
    """Schema for paginated user list"""
    
    users: List[UserResponse]
    total: int
    page: int
    per_page: int
    pages: int
    
    class Config:
        schema_extra = {
            "example": {
                "users": [],
                "total": 100,
                "page": 1,
                "per_page": 20,
                "pages": 5
            }
        }


class ChangePassword(BaseModel):
    """Schema for changing user password"""
    
    current_password: str
    new_password: str
    
    @validator("current_password")
    def validate_current_password(cls, v):
        """Ensure current password is not empty"""
        if not v or not v.strip():
            raise ValueError("Current password is required")
        return v
    
    @validator("new_password")
    def validate_new_password(cls, v):
        """Validate new password strength"""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if len(v) > 128:
            raise ValueError("Password must be less than 128 characters")
        
        # Check for basic password requirements
        has_upper = any(c.isupper() for c in v)
        has_lower = any(c.islower() for c in v)
        has_digit = any(c.isdigit() for c in v)
        
        if not (has_upper and has_lower and has_digit):
            raise ValueError(
                "Password must contain at least one uppercase letter, "
                "one lowercase letter, and one digit"
            )
        
        return v