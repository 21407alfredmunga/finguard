"""
Security utilities for FinGuard Lite
Handles JWT tokens, password hashing, and authentication
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from passlib.hash import bcrypt
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
import secrets
import logging

from ..config import settings
from ..models.user import User

# Configure logging
logger = logging.getLogger(__name__)

# Password hashing context using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
ALGORITHM = settings.jwt_algorithm
SECRET_KEY = settings.jwt_secret_key
ACCESS_TOKEN_EXPIRE_MINUTES = settings.jwt_access_token_expire_minutes
REFRESH_TOKEN_EXPIRE_DAYS = settings.jwt_refresh_token_expire_days


class SecurityError(Exception):
    """Custom exception for security-related errors"""
    pass


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against its hash
    
    Args:
        plain_password: The plain text password
        hashed_password: The hashed password from database
        
    Returns:
        bool: True if password matches, False otherwise
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False


def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt
    
    Args:
        password: Plain text password to hash
        
    Returns:
        str: Hashed password
    """
    try:
        return pwd_context.hash(password)
    except Exception as e:
        logger.error(f"Password hashing error: {e}")
        raise SecurityError("Failed to hash password")


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token
    
    Args:
        data: Payload data to include in token
        expires_delta: Custom expiration time (optional)
        
    Returns:
        str: Encoded JWT token
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    })
    
    try:
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    except Exception as e:
        logger.error(f"JWT encoding error: {e}")
        raise SecurityError("Failed to create access token")


def create_refresh_token(data: Dict[str, Any]) -> str:
    """
    Create a JWT refresh token with longer expiration
    
    Args:
        data: Payload data to include in token
        
    Returns:
        str: Encoded JWT refresh token
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh",
        "jti": secrets.token_urlsafe(32)  # JWT ID for token blacklisting
    })
    
    try:
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    except Exception as e:
        logger.error(f"JWT encoding error: {e}")
        raise SecurityError("Failed to create refresh token")


def verify_token(token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
    """
    Verify and decode a JWT token
    
    Args:
        token: JWT token to verify
        token_type: Expected token type ("access" or "refresh")
        
    Returns:
        Dict containing token payload if valid, None if invalid
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # Check token type
        if payload.get("type") != token_type:
            logger.warning(f"Invalid token type. Expected: {token_type}, Got: {payload.get('type')}")
            return None
        
        # Check expiration
        exp = payload.get("exp")
        if exp is None or datetime.fromtimestamp(exp) < datetime.utcnow():
            logger.info("Token has expired")
            return None
        
        return payload
        
    except JWTError as e:
        logger.warning(f"JWT verification error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected token verification error: {e}")
        return None


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """
    Authenticate a user with email and password
    
    Args:
        db: Database session
        email: User's email address
        password: Plain text password
        
    Returns:
        User object if authentication successful, None otherwise
    """
    try:
        # Find user by email
        user = db.query(User).filter(User.email == email).first()
        
        if not user:
            logger.info(f"Authentication failed: User not found for email {email}")
            return None
        
        # Check if user is active
        if not user.is_active:
            logger.info(f"Authentication failed: User account inactive for {email}")
            return None
        
        # Verify password
        if not verify_password(password, user.hashed_password):
            logger.info(f"Authentication failed: Invalid password for {email}")
            return None
        
        # Update last login
        user.last_login = datetime.utcnow()
        db.commit()
        
        logger.info(f"Authentication successful for user {email}")
        return user
        
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        db.rollback()
        return None


def get_current_user(db: Session, token: str) -> Optional[User]:
    """
    Get current user from JWT access token
    
    Args:
        db: Database session
        token: JWT access token
        
    Returns:
        User object if token is valid, None otherwise
    """
    payload = verify_token(token, "access")
    
    if payload is None:
        return None
    
    user_id = payload.get("sub")  # Subject claim contains user ID
    if user_id is None:
        return None
    
    try:
        user = db.query(User).filter(User.id == user_id).first()
        
        if user is None or not user.is_active:
            return None
        
        return user
        
    except Exception as e:
        logger.error(f"Error fetching user: {e}")
        return None


def create_user_tokens(user: User) -> Dict[str, Any]:
    """
    Create both access and refresh tokens for a user
    
    Args:
        user: User object
        
    Returns:
        Dict containing access_token, refresh_token, token_type, and expires_in
    """
    # Prepare token data
    token_data = {
        "sub": str(user.id),  # Subject (user ID)
        "email": user.email,
        "role": user.role.value,
        "name": user.name
    }
    
    # Create tokens
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token({"sub": str(user.id), "email": user.email})
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60  # Convert to seconds
    }


def refresh_access_token(refresh_token: str, db: Session) -> Optional[Dict[str, Any]]:
    """
    Create new access token from valid refresh token
    
    Args:
        refresh_token: JWT refresh token
        db: Database session
        
    Returns:
        Dict containing new access token if refresh token is valid
    """
    payload = verify_token(refresh_token, "refresh")
    
    if payload is None:
        return None
    
    user_id = payload.get("sub")
    if user_id is None:
        return None
    
    # Fetch user to ensure they still exist and are active
    user = db.query(User).filter(User.id == user_id).first()
    
    if user is None or not user.is_active:
        return None
    
    # Create new access token
    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "name": user.name
    }
    
    access_token = create_access_token(token_data)
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }


def generate_secure_token(length: int = 32) -> str:
    """
    Generate a cryptographically secure random token
    
    Args:
        length: Length of the token
        
    Returns:
        str: URL-safe token
    """
    return secrets.token_urlsafe(length)


# Common HTTP exceptions for authentication errors
credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

inactive_user_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Inactive user account",
)

insufficient_permissions_exception = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Insufficient permissions for this operation",
)