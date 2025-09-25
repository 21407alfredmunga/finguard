"""
FinGuard Lite - Main FastAPI Application
Entry point for the AI-powered financial assistant for Kenyan SMEs
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import sys
from datetime import datetime

from .config import settings
from .db import create_tables
from .api import auth, daraja, transactions

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('finguard.log') if not settings.debug else logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler
    
    Runs startup and shutdown code for the FastAPI application.
    """
    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Debug mode: {settings.debug}")
    
    # Initialize database tables if in development
    if settings.debug and settings.environment == "development":
        try:
            create_tables()
            logger.info("Database tables initialized")
        except Exception as e:
            logger.error(f"Failed to initialize database tables: {e}")
    
    logger.info("Application startup complete")
    
    yield
    
    # Shutdown
    logger.info("Application shutdown initiated")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="AI-powered financial assistant for Kenyan SMEs with M-Pesa integration",
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,  # Disable docs in production
    redoc_url="/redoc" if settings.debug else None,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler for unhandled exceptions
    
    Logs the error and returns a generic error response to avoid leaking information.
    """
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    if settings.debug:
        # In debug mode, return detailed error information
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal Server Error",
                "message": str(exc),
                "type": type(exc).__name__
            }
        )
    else:
        # In production, return generic error message
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal Server Error",
                "message": "An unexpected error occurred. Please try again later."
            }
        )


# Health check endpoint
@app.get("/health")
async def health_check():
    """
    Health check endpoint for monitoring and load balancers
    
    Returns application status and basic system information.
    """
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "timestamp": datetime.utcnow().isoformat(),
        "database": "connected"  # TODO: Add actual database health check
    }


# Root endpoint
@app.get("/")
async def root():
    """
    Root endpoint with API information
    """
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "description": "AI-powered financial assistant for Kenyan SMEs",
        "status": "running",
        "docs": "/docs" if settings.debug else "Documentation disabled in production",
        "endpoints": {
            "authentication": "/api/auth",
            "transactions": "/api/transactions", 
            "daraja_webhook": "/api/daraja/webhook",
            "health": "/health"
        }
    }


# API Routes
app.include_router(auth.router, prefix="/api")
app.include_router(daraja.router, prefix="/api")  
app.include_router(transactions.router, prefix="/api")


# Middleware for request logging
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Middleware to log HTTP requests
    
    Logs basic request information for monitoring and debugging.
    """
    start_time = datetime.utcnow()
    
    # Process the request
    response = await call_next(request)
    
    # Calculate processing time
    process_time = (datetime.utcnow() - start_time).total_seconds()
    
    # Log request information
    logger.info(
        f"{request.method} {request.url.path} - "
        f"Status: {response.status_code} - "
        f"Time: {process_time:.3f}s"
    )
    
    # Add processing time to response headers
    response.headers["X-Process-Time"] = str(process_time)
    
    return response


# Additional middleware for security headers
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """
    Middleware to add security headers to responses
    """
    response = await call_next(request)
    
    # Add security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    
    if not settings.debug:
        # Only add HSTS in production
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
    return response


if __name__ == "__main__":
    # This block allows running the application directly with python -m app.main
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )