"""
Transaction API Routes
Handles transaction listing, filtering, and reconciliation
"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc
from datetime import datetime, timedelta
import logging

from ..db import get_db
from ..models.transaction import Transaction, TransactionType, TransactionStatus
from ..models.account import Account
from ..models.user import User
from ..schemas.transaction import (
    TransactionResponse, 
    TransactionList, 
    TransactionFilter,
    TransactionReconcile
)
from ..core.security import get_current_user, credentials_exception

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/transactions", tags=["Transactions"])

# Security scheme for Bearer tokens
security = HTTPBearer()


def get_current_authenticated_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Dependency to get current authenticated user
    
    Returns:
        User: Current authenticated user
        
    Raises:
        HTTPException: If user is not authenticated
    """
    token = credentials.credentials
    current_user = get_current_user(db, token)
    
    if not current_user:
        raise credentials_exception
    
    return current_user


def get_user_accounts(db: Session, user: User) -> List[Account]:
    """
    Get all accounts accessible by the user
    
    Args:
        db: Database session
        user: Current user
        
    Returns:
        List[Account]: List of accounts user can access
    """
    if user.role.value == "owner":
        # Owners can see their own accounts
        return user.accounts.all()
    elif user.role.value == "accountant":
        # Accountants can see all accounts (for now)
        # In production, implement proper account-level permissions
        return db.query(Account).all()
    else:
        return []


@router.get("", response_model=TransactionList)
async def list_transactions(
    account_id: Optional[str] = Query(None, description="Filter by account ID"),
    start_date: Optional[datetime] = Query(None, description="Start date filter"),
    end_date: Optional[datetime] = Query(None, description="End date filter"),
    transaction_type: Optional[TransactionType] = Query(None, description="Filter by transaction type"),
    status: Optional[TransactionStatus] = Query(None, description="Filter by status"),
    min_amount: Optional[float] = Query(None, description="Minimum amount filter"),
    max_amount: Optional[float] = Query(None, description="Maximum amount filter"),
    phone: Optional[str] = Query(None, description="Filter by phone number"),
    reference: Optional[str] = Query(None, description="Filter by reference"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_authenticated_user),
    db: Session = Depends(get_db)
) -> TransactionList:
    """
    List transactions with filtering and pagination
    
    Returns transactions accessible to the current user with optional filtering.
    """
    try:
        # Get accounts accessible by this user
        user_accounts = get_user_accounts(db, current_user)
        
        if not user_accounts:
            return TransactionList(
                transactions=[],
                total=0,
                page=page,
                per_page=per_page,
                pages=0,
                summary={"total_inbound": 0, "total_outbound": 0, "net_amount": 0, "transaction_count": 0}
            )
        
        # Build base query
        account_ids = [acc.id for acc in user_accounts]
        query = db.query(Transaction).filter(Transaction.account_id.in_(account_ids))
        
        # Apply filters
        if account_id:
            # Verify user has access to this specific account
            if account_id not in [str(acc.id) for acc in user_accounts]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to this account"
                )
            query = query.filter(Transaction.account_id == account_id)
        
        if start_date:
            query = query.filter(Transaction.transaction_time >= start_date)
        
        if end_date:
            query = query.filter(Transaction.transaction_time <= end_date)
        
        if transaction_type:
            query = query.filter(Transaction.transaction_type == transaction_type)
        
        if status:
            query = query.filter(Transaction.status == status)
        
        if min_amount is not None:
            query = query.filter(Transaction.amount >= min_amount)
        
        if max_amount is not None:
            query = query.filter(Transaction.amount <= max_amount)
        
        if phone:
            # Partial match on phone number
            phone_clean = ''.join(filter(str.isdigit, phone))
            query = query.filter(Transaction.phone.contains(phone_clean))
        
        if reference:
            # Case-insensitive partial match on reference
            query = query.filter(Transaction.reference.ilike(f"%{reference}%"))
        
        # Get total count before pagination
        total_count = query.count()
        
        # Calculate summary statistics for filtered results
        summary_query = query.with_entities(
            func.sum(func.case(
                [
                    (Transaction.transaction_type.in_([TransactionType.C2B, TransactionType.LIPA_NA_MPESA]), 
                     Transaction.amount)
                ], 
                else_=0
            )).label('total_inbound'),
            func.sum(func.case(
                [
                    (Transaction.transaction_type.in_([TransactionType.B2C, TransactionType.B2B]), 
                     Transaction.amount)
                ], 
                else_=0
            )).label('total_outbound'),
            func.count(Transaction.id).label('transaction_count')
        )
        
        summary_result = summary_query.first()
        total_inbound = float(summary_result.total_inbound or 0)
        total_outbound = float(summary_result.total_outbound or 0)
        net_amount = total_inbound - total_outbound
        
        # Apply pagination and ordering
        offset = (page - 1) * per_page
        transactions = query.order_by(desc(Transaction.transaction_time)).offset(offset).limit(per_page).all()
        
        # Calculate pagination info
        total_pages = (total_count + per_page - 1) // per_page
        
        # Convert to response format
        transaction_responses = [TransactionResponse.from_orm(t) for t in transactions]
        
        return TransactionList(
            transactions=transaction_responses,
            total=total_count,
            page=page,
            per_page=per_page,
            pages=total_pages,
            summary={
                "total_inbound": total_inbound,
                "total_outbound": total_outbound,
                "net_amount": net_amount,
                "transaction_count": int(summary_result.transaction_count or 0)
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing transactions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve transactions"
        )


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: str,
    current_user: User = Depends(get_current_authenticated_user),
    db: Session = Depends(get_db)
) -> TransactionResponse:
    """
    Get a specific transaction by ID
    
    Returns transaction details if user has access to the associated account.
    """
    try:
        # Get user's accessible accounts
        user_accounts = get_user_accounts(db, current_user)
        account_ids = [acc.id for acc in user_accounts]
        
        # Find transaction
        transaction = db.query(Transaction).filter(
            and_(
                Transaction.id == transaction_id,
                Transaction.account_id.in_(account_ids)
            )
        ).first()
        
        if not transaction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transaction not found or access denied"
            )
        
        return TransactionResponse.from_orm(transaction)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching transaction {transaction_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve transaction"
        )


@router.post("/reconcile", response_model=Dict[str, Any])
async def reconcile_transactions(
    reconcile_data: TransactionReconcile,
    current_user: User = Depends(get_current_authenticated_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Reconcile transactions for an account (stub implementation)
    
    In production, this would:
    1. Compare local transactions with M-Pesa statement
    2. Identify missing or mismatched transactions
    3. Generate reconciliation report
    4. Flag discrepancies for manual review
    """
    try:
        # Verify user has access to this account
        user_accounts = get_user_accounts(db, current_user)
        account_ids = [acc.id for acc in user_accounts]
        
        if str(reconcile_data.account_id) not in [str(aid) for aid in account_ids]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this account"
            )
        
        # Get account
        account = db.query(Account).filter(Account.id == reconcile_data.account_id).first()
        
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found"
            )
        
        # Build date range
        end_date = reconcile_data.end_date or datetime.utcnow()
        start_date = reconcile_data.start_date or (end_date - timedelta(days=30))
        
        # Get transactions in range
        transactions = db.query(Transaction).filter(
            and_(
                Transaction.account_id == reconcile_data.account_id,
                Transaction.transaction_time >= start_date,
                Transaction.transaction_time <= end_date
            )
        ).all()
        
        # Calculate reconciliation statistics
        total_transactions = len(transactions)
        completed_transactions = len([t for t in transactions if t.status == TransactionStatus.COMPLETED])
        failed_transactions = len([t for t in transactions if t.status == TransactionStatus.FAILED])
        pending_transactions = len([t for t in transactions if t.status == TransactionStatus.PENDING])
        
        total_amount = sum(float(t.amount) for t in transactions if t.is_inbound)
        
        logger.info(f"Reconciliation completed for account {reconcile_data.account_id}")
        
        return {
            "success": True,
            "message": "Reconciliation completed successfully",
            "account_id": str(reconcile_data.account_id),
            "date_range": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            },
            "summary": {
                "total_transactions": total_transactions,
                "completed_transactions": completed_transactions,
                "failed_transactions": failed_transactions,
                "pending_transactions": pending_transactions,
                "total_amount": total_amount
            },
            "discrepancies": [],  # Would contain actual discrepancies in production
            "recommendations": [
                "Review failed transactions for reprocessing",
                "Check pending transactions for timeout issues"
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reconciliation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Reconciliation failed"
        )


@router.get("/stats/summary", response_model=Dict[str, Any])
async def get_transaction_summary(
    account_id: Optional[str] = Query(None, description="Filter by account ID"),
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    current_user: User = Depends(get_current_authenticated_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get transaction summary statistics
    
    Returns aggregated transaction data for the specified time period.
    """
    try:
        # Get user's accessible accounts
        user_accounts = get_user_accounts(db, current_user)
        account_ids = [acc.id for acc in user_accounts]
        
        if not account_ids:
            return {
                "summary": {
                    "total_inbound": 0,
                    "total_outbound": 0,
                    "net_amount": 0,
                    "transaction_count": 0,
                    "average_transaction_value": 0
                },
                "period": f"Last {days} days",
                "accounts_analyzed": 0
            }
        
        # Date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Build query
        query = db.query(Transaction).filter(
            and_(
                Transaction.account_id.in_(account_ids),
                Transaction.transaction_time >= start_date,
                Transaction.status == TransactionStatus.COMPLETED
            )
        )
        
        # Apply account filter if specified
        if account_id:
            if account_id not in [str(aid) for aid in account_ids]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to this account"
                )
            query = query.filter(Transaction.account_id == account_id)
            accounts_analyzed = 1
        else:
            accounts_analyzed = len(account_ids)
        
        # Get aggregated statistics
        summary = query.with_entities(
            func.sum(func.case(
                [(Transaction.is_inbound == True, Transaction.amount)], 
                else_=0
            )).label('total_inbound'),
            func.sum(func.case(
                [(Transaction.is_inbound == False, Transaction.amount)], 
                else_=0
            )).label('total_outbound'),
            func.count(Transaction.id).label('transaction_count'),
            func.avg(Transaction.amount).label('avg_amount')
        ).first()
        
        total_inbound = float(summary.total_inbound or 0)
        total_outbound = float(summary.total_outbound or 0)
        net_amount = total_inbound - total_outbound
        transaction_count = int(summary.transaction_count or 0)
        avg_amount = float(summary.avg_amount or 0)
        
        return {
            "summary": {
                "total_inbound": total_inbound,
                "total_outbound": total_outbound,
                "net_amount": net_amount,
                "transaction_count": transaction_count,
                "average_transaction_value": avg_amount
            },
            "period": f"Last {days} days",
            "date_range": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            },
            "accounts_analyzed": accounts_analyzed
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting transaction summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate transaction summary"
        )