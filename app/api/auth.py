"""
Authentication API Routes
Handles user registration, login, token refresh, and password reset
"""

from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from datetime import datetime
import logging

from ..db import get_db
from ..models.user import User, AuditLog, UserRole
from ..schemas.auth import UserSignup, UserLogin, Token, RefreshToken, PasswordReset, AuthResponse
from ..schemas.user import UserResponse
from ..core.security import (
    get_password_hash, 
    authenticate_user, 
    create_user_tokens,
    refresh_access_token,
    get_current_user,
    credentials_exception
)

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/auth", tags=["Authentication"])

# Security scheme for Bearer tokens
security = HTTPBearer()


def log_audit_event(
    db: Session, 
    user_id: str = None, 
    action: str = "", 
    success: bool = True, 
    details: str = "",
    ip_address: str = None,
    user_agent: str = None
):
    """
    Log an audit event to the database
    
    Args:
        db: Database session
        user_id: User ID (if applicable)
        action: Action performed
        success: Whether the action was successful
        details: Additional details
        ip_address: Client IP address
        user_agent: Client user agent
    """
    try:
        audit_log = AuditLog(
            user_id=user_id,
            action=action,
            success=success,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent
        )
        db.add(audit_log)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to log audit event: {e}")
        db.rollback()


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    user_data: UserSignup,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
) -> UserResponse:
    """
    Register a new user account
    
    Creates a new user with hashed password and default role.
    Logs the registration attempt for audit purposes.
    """
    try:
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == user_data.email).first()
        if existing_user:
            # Log failed registration attempt
            background_tasks.add_task(
                log_audit_event,
                db=db,
                action="user_signup_failed",
                success=False,
                details=f"Email already exists: {user_data.email}"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email address is already registered"
            )
        
        # Hash the password
        hashed_password = get_password_hash(user_data.password)
        
        # Create new user
        new_user = User(
            name=user_data.name,
            email=user_data.email,
            phone=user_data.phone,
            hashed_password=hashed_password,
            role=UserRole(user_data.role),
            is_active=True,
            is_verified=False  # Email verification would happen here in production
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        # Log successful registration
        background_tasks.add_task(
            log_audit_event,
            db=db,
            user_id=str(new_user.id),
            action="user_signup_success",
            success=True,
            details=f"New user registered: {user_data.email}"
        )
        
        logger.info(f"New user registered: {user_data.email}")
        
        # Return user data (excluding password)
        user_response = UserResponse.from_orm(new_user)
        user_response.account_count = 0  # New user has no accounts yet
        
        return user_response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signup error: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed. Please try again."
        )


@router.post("/login", response_model=Token)
async def login(
    user_credentials: UserLogin,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
) -> Token:
    """
    Authenticate user and return JWT tokens
    
    Validates user credentials and returns access and refresh tokens.
    Updates last login timestamp and logs the attempt.
    """
    try:
        # Authenticate user
        user = authenticate_user(db, user_credentials.email, user_credentials.password)
        
        if not user:
            # Log failed login attempt
            background_tasks.add_task(
                log_audit_event,
                db=db,
                action="login_failed",
                success=False,
                details=f"Invalid credentials for: {user_credentials.email}"
            )
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Create tokens
        tokens = create_user_tokens(user)
        
        # Log successful login
        background_tasks.add_task(
            log_audit_event,
            db=db,
            user_id=str(user.id),
            action="login_success",
            success=True,
            details=f"User logged in: {user.email}"
        )
        
        logger.info(f"User logged in successfully: {user.email}")
        
        return Token(**tokens)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed. Please try again."
        )


@router.post("/refresh", response_model=Dict[str, Any])
async def refresh_token(
    refresh_data: RefreshToken,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Refresh access token using refresh token
    
    Validates refresh token and returns new access token.
    """
    try:
        new_tokens = refresh_access_token(refresh_data.refresh_token, db)
        
        if not new_tokens:
            background_tasks.add_task(
                log_audit_event,
                db=db,
                action="token_refresh_failed",
                success=False,
                details="Invalid refresh token"
            )
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        logger.info("Access token refreshed successfully")
        return new_tokens
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed"
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> UserResponse:
    """
    Get current user information
    
    Returns user profile data for the authenticated user.
    """
    try:
        # Extract token from credentials
        token = credentials.credentials
        
        # Get current user
        current_user = get_current_user(db, token)
        
        if not current_user:
            raise credentials_exception
        
        # Get account count for this user
        account_count = current_user.accounts.count()
        
        # Return user data
        user_response = UserResponse.from_orm(current_user)
        user_response.account_count = account_count
        
        return user_response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user info error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user information"
        )


@router.post("/reset-password", response_model=AuthResponse)
async def reset_password(
    reset_data: PasswordReset,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
) -> AuthResponse:
    """
    Request password reset (stub implementation)
    
    In production, this would:
    1. Generate a secure reset token
    2. Send email with reset link
    3. Store token with expiration
    """
    try:
        # Check if user exists
        user = db.query(User).filter(User.email == reset_data.email).first()
        
        if user:
            # Log password reset request (but don't reveal if user exists)
            background_tasks.add_task(
                log_audit_event,
                db=db,
                user_id=str(user.id),
                action="password_reset_requested",
                success=True,
                details=f"Password reset requested for: {reset_data.email}"
            )
            
            logger.info(f"Password reset requested for: {reset_data.email}")
        else:
            # Log attempt for non-existent user
            background_tasks.add_task(
                log_audit_event,
                db=db,
                action="password_reset_requested",
                success=False,
                details=f"Password reset requested for non-existent email: {reset_data.email}"
            )
        
        # Always return success to prevent email enumeration
        return AuthResponse(
            success=True,
            message="If an account with this email exists, a password reset link has been sent."
        )
        
    except Exception as e:
        logger.error(f"Password reset error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password reset request failed"
        )


@router.post("/logout", response_model=AuthResponse)
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
) -> AuthResponse:
    """
    Logout user (stub implementation)
    
    In production, this would add the token to a blacklist.
    For now, we just log the logout event.
    """
    try:
        token = credentials.credentials
        current_user = get_current_user(db, token)
        
        if current_user:
            # Log logout event
            background_tasks.add_task(
                log_audit_event,
                db=db,
                user_id=str(current_user.id),
                action="user_logout",
                success=True,
                details=f"User logged out: {current_user.email}"
            )
            
            logger.info(f"User logged out: {current_user.email}")
        
        return AuthResponse(
            success=True,
            message="Logged out successfully"
        )
        
    except Exception as e:
        logger.error(f"Logout error: {e}")
        # Don't raise exception for logout - always return success
        return AuthResponse(
            success=True,
            message="Logged out successfully"
        )