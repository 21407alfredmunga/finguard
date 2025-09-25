"""
Structured Logging Configuration for FinGuard Lite
Provides consistent logging across the application
"""

import logging
import sys
from typing import Dict, Any
import json
from datetime import datetime


class StructuredFormatter(logging.Formatter):
    """
    Custom formatter that outputs structured JSON logs
    
    This is useful for log aggregation systems like ELK stack or CloudWatch.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as structured JSON
        
        Args:
            record: Log record to format
            
        Returns:
            str: JSON formatted log message
        """
        log_entry = {
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception information if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info)
            }
        
        # Add extra fields if present
        if hasattr(record, 'extra_fields'):
            log_entry.update(record.extra_fields)
        
        return json.dumps(log_entry)


def setup_logging(log_level: str = "INFO", use_json: bool = False) -> None:
    """
    Set up application logging configuration
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        use_json: Whether to use JSON structured logging
    """
    # Convert log level string to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Create formatter
    if use_json:
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Suppress noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with structured logging support
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        logging.Logger: Configured logger instance
    """
    return logging.getLogger(name)


class LoggerAdapter(logging.LoggerAdapter):
    """
    Logger adapter that adds context information to log records
    
    Useful for adding request IDs, user IDs, or other contextual information.
    """
    
    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        """
        Process log message and add extra context
        
        Args:
            msg: Log message
            kwargs: Keyword arguments
            
        Returns:
            tuple: (message, kwargs) with added context
        """
        # Add extra fields to the log record
        extra_fields = kwargs.get('extra', {})
        extra_fields.update(self.extra)
        kwargs['extra'] = extra_fields
        
        return msg, kwargs


def create_context_logger(name: str, **context) -> LoggerAdapter:
    """
    Create a logger with additional context information
    
    Args:
        name: Logger name
        **context: Additional context fields to include in logs
        
    Returns:
        LoggerAdapter: Logger with context
    """
    logger = get_logger(name)
    return LoggerAdapter(logger, context)


# Security-related logging functions
def log_security_event(
    event_type: str,
    user_id: str = None,
    ip_address: str = None,
    user_agent: str = None,
    details: Dict[str, Any] = None,
    success: bool = True
) -> None:
    """
    Log security-related events for monitoring and compliance
    
    Args:
        event_type: Type of security event (login, logout, failed_auth, etc.)
        user_id: User ID if applicable
        ip_address: Client IP address
        user_agent: Client user agent
        details: Additional event details
        success: Whether the event was successful
    """
    security_logger = get_logger("security")
    
    event_data = {
        "event_type": event_type,
        "user_id": user_id,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "success": success,
        "details": details or {}
    }
    
    log_level = logging.INFO if success else logging.WARNING
    security_logger.log(
        log_level,
        f"Security event: {event_type}",
        extra={"extra_fields": event_data}
    )


def log_api_call(
    method: str,
    path: str,
    status_code: int,
    response_time: float,
    user_id: str = None,
    error_message: str = None
) -> None:
    """
    Log API call information for monitoring and analytics
    
    Args:
        method: HTTP method
        path: Request path
        status_code: HTTP status code
        response_time: Response time in seconds
        user_id: User ID if authenticated
        error_message: Error message if applicable
    """
    api_logger = get_logger("api")
    
    call_data = {
        "method": method,
        "path": path,
        "status_code": status_code,
        "response_time": response_time,
        "user_id": user_id,
        "error_message": error_message
    }
    
    if status_code >= 400:
        log_level = logging.ERROR if status_code >= 500 else logging.WARNING
        message = f"API Error: {method} {path} - {status_code}"
    else:
        log_level = logging.INFO
        message = f"API Call: {method} {path} - {status_code}"
    
    api_logger.log(
        log_level,
        message,
        extra={"extra_fields": call_data}
    )


def log_transaction_event(
    event_type: str,
    transaction_id: str = None,
    mpesa_transaction_id: str = None,
    account_id: str = None,
    amount: float = None,
    details: Dict[str, Any] = None
) -> None:
    """
    Log transaction-related events for audit and monitoring
    
    Args:
        event_type: Type of transaction event
        transaction_id: Internal transaction ID
        mpesa_transaction_id: M-Pesa transaction ID
        account_id: Account ID
        amount: Transaction amount
        details: Additional event details
    """
    transaction_logger = get_logger("transactions")
    
    event_data = {
        "event_type": event_type,
        "transaction_id": transaction_id,
        "mpesa_transaction_id": mpesa_transaction_id,
        "account_id": account_id,
        "amount": amount,
        "details": details or {}
    }
    
    transaction_logger.info(
        f"Transaction event: {event_type}",
        extra={"extra_fields": event_data}
    )


# Performance logging
def log_performance_metric(
    operation: str,
    duration: float,
    success: bool = True,
    details: Dict[str, Any] = None
) -> None:
    """
    Log performance metrics for monitoring and optimization
    
    Args:
        operation: Name of the operation
        duration: Duration in seconds
        success: Whether the operation was successful
        details: Additional metric details
    """
    perf_logger = get_logger("performance")
    
    metric_data = {
        "operation": operation,
        "duration": duration,
        "success": success,
        "details": details or {}
    }
    
    perf_logger.info(
        f"Performance: {operation} took {duration:.3f}s",
        extra={"extra_fields": metric_data}
    )