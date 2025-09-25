"""
Authentication Schemas
Pydantic models for authentication requests and responses
"""

from typing import Optional
from pydantic import BaseModel, EmailStr, validator
from datetime import datetime


class UserSignup(BaseModel):
    """Schema for user registration"""
    
    name: str
    email: EmailStr
    phone: Optional[str] = None
    password: str
    role: str = "owner"  # Default role
    
    @validator("name")
    def validate_name(cls, v):
        """Validate user name"""
        if not v or len(v.strip()) < 2:
            raise ValueError("Name must be at least 2 characters long")
        if len(v) > 100:
            raise ValueError("Name must be less than 100 characters")
        return v.strip()
    
    @validator("password")
    def validate_password(cls, v):
        """Validate password strength"""
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
    
    @validator("phone")
    def validate_phone(cls, v):
        """Validate Kenyan phone number format"""
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
    
    @validator("role")
    def validate_role(cls, v):
        """Validate user role"""
        allowed_roles = ["owner", "accountant"]
        if v not in allowed_roles:
            raise ValueError(f"Role must be one of: {allowed_roles}")
        return v


class UserLogin(BaseModel):
    """Schema for user login"""
    
    email: EmailStr
    password: str
    
    @validator("password")
    def validate_password_not_empty(cls, v):
        """Ensure password is not empty"""
        if not v or not v.strip():
            raise ValueError("Password is required")
        return v


class Token(BaseModel):
    """Schema for JWT token response"""
    
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires
    
    class Config:
        schema_extra = {
            "example": {
                "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                "token_type": "bearer",
                "expires_in": 1800
            }
        }


class TokenData(BaseModel):
    """Schema for JWT token payload data"""
    
    user_id: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    exp: Optional[datetime] = None


class RefreshToken(BaseModel):
    """Schema for refresh token request"""
    
    refresh_token: str
    
    @validator("refresh_token")
    def validate_refresh_token(cls, v):
        """Ensure refresh token is not empty"""
        if not v or not v.strip():
            raise ValueError("Refresh token is required")
        return v


class PasswordReset(BaseModel):
    """Schema for password reset request (stub for now)"""
    
    email: EmailStr
    
    class Config:
        schema_extra = {
            "example": {
                "email": "user@example.com"
            }
        }


class PasswordResetConfirm(BaseModel):
    """Schema for password reset confirmation (stub for now)"""
    
    token: str
    new_password: str
    
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


class AuthResponse(BaseModel):
    """Generic response schema for authentication operations"""
    
    success: bool
    message: str
    data: Optional[dict] = None
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "message": "Operation completed successfully",
                "data": {}
            }
        }