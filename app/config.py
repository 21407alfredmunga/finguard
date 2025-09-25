"""
Configuration management for FinGuard Lite
Handles environment variables and application settings
"""

from functools import lru_cache
from typing import List, Optional
from pydantic import BaseSettings, validator
import os
from pathlib import Path


class Settings(BaseSettings):
    """Application settings with environment variable support"""
    
    # Application Info
    app_name: str = "FinGuard Lite"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"
    
    # Database Configuration
    database_url: str
    test_database_url: Optional[str] = None
    
    # JWT Authentication
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    
    # Daraja API Configuration
    daraja_consumer_key: str
    daraja_consumer_secret: str
    daraja_passkey: str
    daraja_shortcode: str = "174379"  # Sandbox default
    daraja_base_url: str = "https://sandbox.safaricom.co.ke"
    daraja_webhook_secret: str
    
    # CORS Configuration
    cors_origins: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "https://localhost:3000",
    ]
    
    # Logging
    log_level: str = "INFO"
    
    @validator("cors_origins", pre=True)
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string or list"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    @validator("database_url", pre=True)
    def validate_database_url(cls, v):
        """Ensure database URL is properly formatted"""
        if not v:
            raise ValueError("DATABASE_URL is required")
        return v
    
    @validator("jwt_secret_key", pre=True)
    def validate_jwt_secret(cls, v):
        """Ensure JWT secret key is secure"""
        if not v or len(v) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters long")
        return v
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached application settings
    Using lru_cache to avoid reading .env file multiple times
    """
    return Settings()


# Global settings instance
settings = get_settings()