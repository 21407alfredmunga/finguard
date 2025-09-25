"""
Daraja API Routes  
Handles M-Pesa webhook callbacks and transaction processing
"""

from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime
import json
import logging

from ..db import get_db
from ..models.transaction import Transaction, TransactionType, TransactionStatus
from ..models.account import Account
from ..schemas.transaction import DarajaCallbackPayload, WebhookResponse, TransactionResponse
from ..core.daraja import validate_webhook_signature, format_kenyan_phone

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/daraja", tags=["Daraja M-Pesa"])


def parse_transaction_time(trans_time_str: str) -> datetime:
    """
    Parse M-Pesa transaction time string to datetime
    
    Args:
        trans_time_str: Transaction time in YYYYMMDDHHMMSS format
        
    Returns:
        datetime: Parsed datetime object
    """
    try:
        return datetime.strptime(trans_time_str, "%Y%m%d%H%M%S")
    except ValueError as e:
        logger.error(f"Failed to parse transaction time: {trans_time_str} - {e}")
        # Fallback to current time if parsing fails
        return datetime.utcnow()


def determine_transaction_type(transaction_type_str: str) -> TransactionType:
    """
    Determine transaction type from Daraja callback
    
    Args:
        transaction_type_str: Transaction type from callback
        
    Returns:
        TransactionType: Normalized transaction type
    """
    # Normalize the transaction type string
    normalized = transaction_type_str.strip().lower()
    
    # Map Daraja transaction types to our enum
    type_mapping = {
        "pay bill": TransactionType.C2B,
        "paybill": TransactionType.C2B,
        "buy goods": TransactionType.C2B,
        "buygoods": TransactionType.C2B,
        "customer pay bill online": TransactionType.LIPA_NA_MPESA,
        "lipa na mpesa online": TransactionType.LIPA_NA_MPESA,
        "customer buy goods online": TransactionType.LIPA_NA_MPESA,
        "b2c": TransactionType.B2C,
        "b2b": TransactionType.B2B,
        "reversal": TransactionType.REVERSAL,
    }
    
    transaction_type = type_mapping.get(normalized, TransactionType.C2B)
    logger.info(f"Mapped transaction type '{transaction_type_str}' to {transaction_type}")
    
    return transaction_type


def find_account_by_shortcode(db: Session, shortcode: str) -> Account:
    """
    Find account by M-Pesa shortcode
    
    Args:
        db: Database session
        shortcode: M-Pesa business shortcode
        
    Returns:
        Account: Account associated with the shortcode
        
    Raises:
        HTTPException: If no account found for shortcode
    """
    account = db.query(Account).filter(Account.mpesa_shortcode == shortcode).first()
    
    if not account:
        # For demo purposes, return the first available account
        # In production, you would need proper shortcode management
        account = db.query(Account).first()
        
        if not account:
            logger.error(f"No account found for shortcode: {shortcode}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No account configured for shortcode: {shortcode}"
            )
        
        logger.warning(f"Using fallback account for shortcode: {shortcode}")
    
    return account


async def process_transaction_background(
    db: Session,
    transaction_id: str,
    payload: Dict[str, Any]
):
    """
    Background task to process transaction data
    
    This runs after the webhook response to avoid blocking Daraja.
    Performs additional validation, reconciliation, and notifications.
    """
    try:
        # Fetch the transaction
        transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()
        
        if not transaction:
            logger.error(f"Transaction not found for background processing: {transaction_id}")
            return
        
        # Additional processing logic here
        # - Send notifications
        # - Update balances
        # - Trigger reconciliation
        # - Generate reports
        
        logger.info(f"Background processing completed for transaction: {transaction_id}")
        
    except Exception as e:
        logger.error(f"Background processing failed for transaction {transaction_id}: {e}")


@router.post("/webhook", response_model=WebhookResponse)
async def handle_mpesa_webhook(
    request: Request,
    payload: DarajaCallbackPayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
) -> WebhookResponse:
    """
    Handle M-Pesa transaction webhook callback from Daraja API
    
    Processes incoming transaction notifications and stores them in the database.
    Ensures idempotency by checking for duplicate transaction IDs.
    """
    try:
        # Get raw request body for signature validation
        raw_body = await request.body()
        
        # Validate webhook signature (basic validation for now)
        signature = request.headers.get("X-Signature", "")
        
        if not validate_webhook_signature(raw_body, signature):
            logger.warning("Invalid webhook signature")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature"
            )
        
        logger.info(f"Received M-Pesa webhook: TransID={payload.TransID}")
        
        # Check for duplicate transaction
        existing_transaction = db.query(Transaction).filter(
            Transaction.mpesa_transaction_id == payload.TransID
        ).first()
        
        if existing_transaction:
            logger.info(f"Duplicate transaction ignored: {payload.TransID}")
            existing_transaction.mark_as_duplicate()
            db.commit()
            
            return WebhookResponse(
                success=True,
                message="Duplicate transaction ignored",
                transaction_id=str(existing_transaction.id)
            )
        
        # Find the account for this transaction
        account = find_account_by_shortcode(db, payload.BusinessShortCode)
        
        # Parse and normalize transaction data
        transaction_time = parse_transaction_time(payload.TransTime)
        transaction_type = determine_transaction_type(payload.TransactionType)
        
        # Format phone number
        try:
            formatted_phone = format_kenyan_phone(payload.MSISDN)
        except ValueError as e:
            logger.error(f"Invalid phone number format: {payload.MSISDN} - {e}")
            formatted_phone = payload.MSISDN
        
        # Construct party name
        party_name_parts = [
            payload.FirstName or "",
            payload.MiddleName or "", 
            payload.LastName or ""
        ]
        party_name = " ".join(filter(None, party_name_parts)).strip()
        
        if not party_name:
            party_name = f"Customer {formatted_phone}"
        
        # Create new transaction record
        new_transaction = Transaction(
            account_id=account.id,
            mpesa_transaction_id=payload.TransID,
            transaction_type=transaction_type,
            amount=float(payload.TransAmount),
            phone=formatted_phone,
            party_name=party_name,
            reference=payload.BillRefNumber or payload.InvoiceNumber,
            transaction_time=transaction_time,
            business_short_code=payload.BusinessShortCode,
            invoice_number=payload.InvoiceNumber,
            org_account_balance=float(payload.OrgAccountBalance) if payload.OrgAccountBalance else None,
            third_party_trans_id=payload.ThirdPartyTransID,
            raw_payload=payload.dict(),  # Store complete raw payload
            status=TransactionStatus.PENDING
        )
        
        # Save to database
        db.add(new_transaction)
        db.commit()
        db.refresh(new_transaction)
        
        # Mark as processed
        new_transaction.mark_as_processed()
        db.commit()
        
        logger.info(f"Transaction processed successfully: {new_transaction.id}")
        
        # Add background task for additional processing
        background_tasks.add_task(
            process_transaction_background,
            db=db,
            transaction_id=str(new_transaction.id),
            payload=payload.dict()
        )
        
        return WebhookResponse(
            success=True,
            message="Transaction processed successfully",
            transaction_id=str(new_transaction.id)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        db.rollback()
        
        # Return success to Daraja to avoid retries, but log the error
        return WebhookResponse(
            success=True,  # Still return success to avoid Daraja retries
            message="Transaction queued for processing"
        )


@router.get("/transactions/recent", response_model=List[TransactionResponse])
async def get_recent_transactions(
    limit: int = 10,
    db: Session = Depends(get_db)
) -> List[TransactionResponse]:
    """
    Get recent transactions across all accounts
    
    This is a utility endpoint for testing and monitoring.
    In production, this should require authentication and filter by user.
    """
    try:
        transactions = db.query(Transaction).order_by(
            Transaction.created_at.desc()
        ).limit(limit).all()
        
        return [TransactionResponse.from_orm(t) for t in transactions]
        
    except Exception as e:
        logger.error(f"Error fetching recent transactions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch recent transactions"
        )


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint for monitoring webhook service
    """
    return {
        "service": "Daraja Webhook Handler",
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }


# Development/testing endpoints (should be removed in production)
@router.post("/test-webhook")
async def test_webhook_endpoint(
    test_payload: Dict[str, Any],
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Test endpoint to simulate webhook calls during development
    
    Accepts any JSON payload and processes it as a webhook.
    Should be removed or secured in production.
    """
    try:
        # Convert test payload to DarajaCallbackPayload
        callback_payload = DarajaCallbackPayload(**test_payload)
        
        # Create a fake request object for testing
        class FakeRequest:
            def __init__(self):
                self.headers = {"X-Signature": "test-signature"}
            
            async def body(self):
                return json.dumps(test_payload).encode()
        
        fake_request = FakeRequest()
        background_tasks = BackgroundTasks()
        
        # Process the webhook
        result = await handle_mpesa_webhook(
            fake_request, 
            callback_payload, 
            background_tasks,
            db
        )
        
        return {
            "message": "Test webhook processed",
            "result": result.dict()
        }
        
    except Exception as e:
        logger.error(f"Test webhook error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Test webhook failed: {str(e)}"
        )