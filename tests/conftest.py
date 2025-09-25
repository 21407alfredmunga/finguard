"""
Test Configuration and Fixtures
Shared test setup and utilities
"""

import pytest
import asyncio
from typing import Generator, Dict, Any
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
import tempfile
import os

from app.main import app
from app.db import get_db, Base
from app.models.user import User, UserRole
from app.models.account import Account, Currency
from app.models.transaction import Transaction, TransactionType, TransactionStatus
from app.core.security import get_password_hash, create_user_tokens


# Test database setup
TEST_DATABASE_URL = "sqlite:///./test_finguard.db"

# Create test engine
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False
)

# Create test session factory
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def get_test_db() -> Generator[Session, None, None]:
    """Override database dependency for testing"""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


# Override the dependency
app.dependency_overrides[get_db] = get_test_db


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Create test database tables"""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    
    # Clean up test database file
    if os.path.exists("./test_finguard.db"):
        os.remove("./test_finguard.db")


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Create a fresh database session for each test"""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


@pytest.fixture
def client() -> TestClient:
    """Create FastAPI test client"""
    return TestClient(app)


@pytest.fixture
def test_user_data() -> Dict[str, Any]:
    """Sample user data for testing"""
    return {
        "name": "John Doe",
        "email": "john@example.com",
        "phone": "254712345678",
        "password": "SecurePass123",
        "role": "owner"
    }


@pytest.fixture
def test_user(db_session: Session, test_user_data: Dict[str, Any]) -> User:
    """Create a test user in the database"""
    user = User(
        name=test_user_data["name"],
        email=test_user_data["email"],
        phone=test_user_data["phone"],
        hashed_password=get_password_hash(test_user_data["password"]),
        role=UserRole.OWNER,
        is_active=True,
        is_verified=True
    )
    
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    return user


@pytest.fixture
def test_accountant_user(db_session: Session) -> User:
    """Create a test accountant user"""
    user = User(
        name="Jane Smith",
        email="jane@example.com",
        phone="254798765432",
        hashed_password=get_password_hash("AccountantPass123"),
        role=UserRole.ACCOUNTANT,
        is_active=True,
        is_verified=True
    )
    
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    return user


@pytest.fixture
def test_account(db_session: Session, test_user: User) -> Account:
    """Create a test account"""
    account = Account(
        user_id=test_user.id,
        business_name="Test Business Ltd",
        business_type="retail",
        currency=Currency.KES,
        mpesa_shortcode="174379",
        mpesa_account_reference="TEST001"
    )
    
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    
    return account


@pytest.fixture
def test_transaction(db_session: Session, test_account: Account) -> Transaction:
    """Create a test transaction"""
    transaction = Transaction(
        account_id=test_account.id,
        mpesa_transaction_id="TEST123456789",
        transaction_type=TransactionType.C2B,
        amount=1000.00,
        phone="254712345678",
        party_name="John Doe",
        reference="TEST_REF",
        transaction_time="2023-01-01 12:00:00",
        business_short_code="174379",
        raw_payload={
            "TransactionType": "Pay Bill",
            "TransID": "TEST123456789",
            "TransAmount": "1000.00"
        },
        status=TransactionStatus.COMPLETED
    )
    
    db_session.add(transaction)
    db_session.commit()
    db_session.refresh(transaction)
    
    return transaction


@pytest.fixture
def auth_headers(test_user: User) -> Dict[str, str]:
    """Create authorization headers for authenticated requests"""
    tokens = create_user_tokens(test_user)
    return {
        "Authorization": f"Bearer {tokens['access_token']}"
    }


@pytest.fixture
def sample_daraja_payload() -> Dict[str, Any]:
    """Sample Daraja webhook payload for testing"""
    return {
        "TransactionType": "Pay Bill",
        "TransID": "NLJ7RT61SV", 
        "TransTime": "20191122063845",
        "TransAmount": "10.00",
        "BusinessShortCode": "174379",
        "BillRefNumber": "account",
        "InvoiceNumber": "",
        "OrgAccountBalance": "49197.00",
        "ThirdPartyTransID": "",
        "MSISDN": "254708374149",
        "FirstName": "John",
        "MiddleName": "",
        "LastName": "Doe"
    }


# Async test utilities
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# Test data generators
def generate_user_data(
    email: str = None,
    role: str = "owner",
    **kwargs
) -> Dict[str, Any]:
    """Generate user data for testing"""
    import uuid
    
    if not email:
        email = f"test{uuid.uuid4().hex[:8]}@example.com"
    
    base_data = {
        "name": "Test User",
        "email": email,
        "phone": "254700000000",
        "password": "TestPass123",
        "role": role
    }
    
    base_data.update(kwargs)
    return base_data


def generate_account_data(**kwargs) -> Dict[str, Any]:
    """Generate account data for testing"""
    import uuid
    
    base_data = {
        "business_name": f"Test Business {uuid.uuid4().hex[:8]}",
        "business_type": "retail",
        "currency": "KES",
        "mpesa_shortcode": "174379",
        "mpesa_account_reference": f"TEST{uuid.uuid4().hex[:4].upper()}"
    }
    
    base_data.update(kwargs)
    return base_data


def generate_daraja_payload(
    trans_id: str = None,
    amount: str = "100.00",
    phone: str = "254708374149",
    **kwargs
) -> Dict[str, Any]:
    """Generate Daraja webhook payload for testing"""
    import uuid
    from datetime import datetime
    
    if not trans_id:
        trans_id = f"TEST{uuid.uuid4().hex[:8].upper()}"
    
    base_payload = {
        "TransactionType": "Pay Bill",
        "TransID": trans_id,
        "TransTime": datetime.now().strftime("%Y%m%d%H%M%S"),
        "TransAmount": amount,
        "BusinessShortCode": "174379", 
        "BillRefNumber": "account",
        "InvoiceNumber": "",
        "OrgAccountBalance": "10000.00",
        "ThirdPartyTransID": "",
        "MSISDN": phone,
        "FirstName": "John",
        "MiddleName": "",
        "LastName": "Doe"
    }
    
    base_payload.update(kwargs)
    return base_payload