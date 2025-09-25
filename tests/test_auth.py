"""
Authentication Tests
Tests for user registration, login, token management, and authorization
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from typing import Dict, Any

from app.models.user import User, UserRole
from app.core.security import verify_password, verify_token


class TestUserRegistration:
    """Test user registration functionality"""
    
    def test_successful_registration(self, client: TestClient, test_user_data: Dict[str, Any]):
        """Test successful user registration"""
        response = client.post("/api/auth/signup", json=test_user_data)
        
        assert response.status_code == 201
        data = response.json()
        
        assert data["email"] == test_user_data["email"]
        assert data["name"] == test_user_data["name"]
        assert data["role"] == test_user_data["role"]
        assert data["is_active"] == True
        assert "id" in data
        assert "created_at" in data
    
    def test_duplicate_email_registration(self, client: TestClient, test_user: User, test_user_data: Dict[str, Any]):
        """Test registration with duplicate email"""
        # Use the same email as existing test_user
        duplicate_data = test_user_data.copy()
        duplicate_data["email"] = test_user.email
        
        response = client.post("/api/auth/signup", json=duplicate_data)
        
        assert response.status_code == 400
        assert "already registered" in response.json()["detail"].lower()
    
    def test_invalid_email_format(self, client: TestClient, test_user_data: Dict[str, Any]):
        """Test registration with invalid email format"""
        invalid_data = test_user_data.copy()
        invalid_data["email"] = "invalid-email"
        
        response = client.post("/api/auth/signup", json=invalid_data)
        
        assert response.status_code == 422
    
    def test_weak_password(self, client: TestClient, test_user_data: Dict[str, Any]):
        """Test registration with weak password"""
        weak_data = test_user_data.copy()
        weak_data["password"] = "123"
        
        response = client.post("/api/auth/signup", json=weak_data)
        
        assert response.status_code == 422
    
    def test_invalid_phone_number(self, client: TestClient, test_user_data: Dict[str, Any]):
        """Test registration with invalid phone number"""
        invalid_data = test_user_data.copy()
        invalid_data["phone"] = "invalid-phone"
        
        response = client.post("/api/auth/signup", json=invalid_data)
        
        assert response.status_code == 422
    
    def test_invalid_role(self, client: TestClient, test_user_data: Dict[str, Any]):
        """Test registration with invalid role"""
        invalid_data = test_user_data.copy()
        invalid_data["role"] = "invalid_role"
        
        response = client.post("/api/auth/signup", json=invalid_data)
        
        assert response.status_code == 422


class TestUserLogin:
    """Test user login functionality"""
    
    def test_successful_login(self, client: TestClient, test_user: User, test_user_data: Dict[str, Any]):
        """Test successful login"""
        login_data = {
            "email": test_user_data["email"],
            "password": test_user_data["password"]
        }
        
        response = client.post("/api/auth/login", json=login_data)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data
        
        # Verify token is valid
        token_payload = verify_token(data["access_token"], "access")
        assert token_payload is not None
        assert token_payload["email"] == test_user.email
    
    def test_invalid_email_login(self, client: TestClient):
        """Test login with invalid email"""
        login_data = {
            "email": "nonexistent@example.com",
            "password": "SomePassword123"
        }
        
        response = client.post("/api/auth/login", json=login_data)
        
        assert response.status_code == 401
        assert "invalid" in response.json()["detail"].lower()
    
    def test_invalid_password_login(self, client: TestClient, test_user: User):
        """Test login with invalid password"""
        login_data = {
            "email": test_user.email,
            "password": "WrongPassword123"
        }
        
        response = client.post("/api/auth/login", json=login_data)
        
        assert response.status_code == 401
        assert "invalid" in response.json()["detail"].lower()
    
    def test_inactive_user_login(self, client: TestClient, db_session: Session, test_user_data: Dict[str, Any]):
        """Test login with inactive user"""
        # Create inactive user
        inactive_user = User(
            name="Inactive User",
            email="inactive@example.com",
            phone="254700000000",
            hashed_password=get_password_hash("Password123"),
            role=UserRole.OWNER,
            is_active=False
        )
        
        db_session.add(inactive_user)
        db_session.commit()
        
        login_data = {
            "email": "inactive@example.com",
            "password": "Password123"
        }
        
        response = client.post("/api/auth/login", json=login_data)
        
        assert response.status_code == 401


class TestTokenManagement:
    """Test JWT token management"""
    
    def test_token_refresh(self, client: TestClient, test_user: User, test_user_data: Dict[str, Any]):
        """Test access token refresh"""
        # First, login to get tokens
        login_data = {
            "email": test_user_data["email"],
            "password": test_user_data["password"]
        }
        
        login_response = client.post("/api/auth/login", json=login_data)
        tokens = login_response.json()
        
        # Use refresh token to get new access token
        refresh_data = {
            "refresh_token": tokens["refresh_token"]
        }
        
        refresh_response = client.post("/api/auth/refresh", json=refresh_data)
        
        assert refresh_response.status_code == 200
        new_tokens = refresh_response.json()
        
        assert "access_token" in new_tokens
        assert new_tokens["token_type"] == "bearer"
        
        # Verify new token is different and valid
        assert new_tokens["access_token"] != tokens["access_token"]
        
        token_payload = verify_token(new_tokens["access_token"], "access")
        assert token_payload is not None
        assert token_payload["email"] == test_user.email
    
    def test_invalid_refresh_token(self, client: TestClient):
        """Test refresh with invalid token"""
        refresh_data = {
            "refresh_token": "invalid.token.here"
        }
        
        response = client.post("/api/auth/refresh", json=refresh_data)
        
        assert response.status_code == 401
    
    def test_get_current_user_info(self, client: TestClient, auth_headers: Dict[str, str], test_user: User):
        """Test getting current user information"""
        response = client.get("/api/auth/me", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["email"] == test_user.email
        assert data["name"] == test_user.name
        assert data["role"] == test_user.role.value
        assert "account_count" in data
    
    def test_get_user_info_invalid_token(self, client: TestClient):
        """Test getting user info with invalid token"""
        headers = {"Authorization": "Bearer invalid.token.here"}
        
        response = client.get("/api/auth/me", headers=headers)
        
        assert response.status_code == 401
    
    def test_get_user_info_missing_token(self, client: TestClient):
        """Test getting user info without token"""
        response = client.get("/api/auth/me")
        
        assert response.status_code == 401 or response.status_code == 422


class TestPasswordReset:
    """Test password reset functionality (stub)"""
    
    def test_password_reset_request(self, client: TestClient, test_user: User):
        """Test password reset request"""
        reset_data = {
            "email": test_user.email
        }
        
        response = client.post("/api/auth/reset-password", json=reset_data)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] == True
        assert "reset link" in data["message"].lower() or "sent" in data["message"].lower()
    
    def test_password_reset_nonexistent_email(self, client: TestClient):
        """Test password reset for nonexistent email"""
        reset_data = {
            "email": "nonexistent@example.com"
        }
        
        response = client.post("/api/auth/reset-password", json=reset_data)
        
        # Should still return success to prevent email enumeration
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True


class TestLogout:
    """Test user logout functionality"""
    
    def test_successful_logout(self, client: TestClient, auth_headers: Dict[str, str]):
        """Test successful logout"""
        response = client.post("/api/auth/logout", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] == True
        assert "logged out" in data["message"].lower()
    
    def test_logout_invalid_token(self, client: TestClient):
        """Test logout with invalid token"""
        headers = {"Authorization": "Bearer invalid.token.here"}
        
        response = client.post("/api/auth/logout", headers=headers)
        
        # Should still return success even with invalid token
        assert response.status_code == 200


class TestAuthenticationSecurity:
    """Test authentication security features"""
    
    def test_password_hashing(self, test_user: User, test_user_data: Dict[str, Any]):
        """Test that passwords are properly hashed"""
        # Password should not be stored in plain text
        assert test_user.hashed_password != test_user_data["password"]
        
        # Should be able to verify the password
        assert verify_password(test_user_data["password"], test_user.hashed_password)
    
    def test_token_expiration_claim(self, test_user: User):
        """Test that tokens contain expiration claims"""
        from app.core.security import create_user_tokens
        
        tokens = create_user_tokens(test_user)
        token_payload = verify_token(tokens["access_token"], "access")
        
        assert "exp" in token_payload
        assert "iat" in token_payload
        assert token_payload["exp"] > token_payload["iat"]
    
    def test_role_based_access_control(self, db_session: Session, client: TestClient):
        """Test that user roles are properly set and returned"""
        from app.core.security import get_password_hash, create_user_tokens
        
        # Create users with different roles
        owner = User(
            name="Owner User",
            email="owner@example.com", 
            phone="254700000001",
            hashed_password=get_password_hash("OwnerPass123"),
            role=UserRole.OWNER,
            is_active=True
        )
        
        accountant = User(
            name="Accountant User",
            email="accountant@example.com",
            phone="254700000002", 
            hashed_password=get_password_hash("AccountantPass123"),
            role=UserRole.ACCOUNTANT,
            is_active=True
        )
        
        db_session.add_all([owner, accountant])
        db_session.commit()
        
        # Test owner token
        owner_tokens = create_user_tokens(owner)
        owner_payload = verify_token(owner_tokens["access_token"], "access")
        assert owner_payload["role"] == "owner"
        
        # Test accountant token
        accountant_tokens = create_user_tokens(accountant)
        accountant_payload = verify_token(accountant_tokens["access_token"], "access")
        assert accountant_payload["role"] == "accountant"


if __name__ == "__main__":
    pytest.main([__file__])