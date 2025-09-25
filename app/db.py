"""
Database session management for FinGuard Lite
Handles SQLAlchemy database connections and session lifecycle
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from typing import Generator
import logging

from .config import settings

# Configure logging
logger = logging.getLogger(__name__)

# Create SQLAlchemy engine
# For PostgreSQL, we'll use the asyncpg driver for better async performance
engine = create_engine(
    settings.database_url,
    # Connection pool settings for production
    pool_pre_ping=True,  # Verify connections before use
    pool_recycle=300,    # Recycle connections every 5 minutes
    echo=settings.debug, # Log SQL queries in debug mode
)

# Create SessionLocal class for database sessions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for SQLAlchemy models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency function to get database session
    
    This function creates a new database session, yields it for use,
    and ensures it's properly closed after the request is finished.
    Used as a FastAPI dependency.
    
    Yields:
        Session: SQLAlchemy database session
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database session error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def create_tables():
    """
    Create all database tables
    This should be used for testing or initial setup
    For production, use Alembic migrations instead
    """
    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")


def drop_tables():
    """
    Drop all database tables
    WARNING: This will delete all data!
    Should only be used in testing environments
    """
    logger.warning("Dropping all database tables...")
    Base.metadata.drop_all(bind=engine)
    logger.info("Database tables dropped")


# Test database configuration
def get_test_engine():
    """
    Create a separate engine for testing
    Uses in-memory SQLite for fast testing if no test DB URL provided
    """
    if settings.test_database_url:
        return create_engine(
            settings.test_database_url,
            pool_pre_ping=True,
            echo=False
        )
    else:
        # Fallback to SQLite for testing
        return create_engine(
            "sqlite:///./test.db",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
            echo=False
        )


def get_test_session():
    """Get a test database session"""
    test_engine = get_test_engine()
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    
    # Create tables for testing
    Base.metadata.create_all(bind=test_engine)
    
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()
        # Clean up after tests
        Base.metadata.drop_all(bind=test_engine)