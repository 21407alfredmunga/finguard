"""
Invoice API endpoints for FinGuard Lite.

Handles free-text and structured invoice creation, PDF generation,
listing, and reconciliation with M-Pesa transactions.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, asc, func
from decimal import Decimal

from app.db import get_db
from app.models import Invoice, Transaction, Account, User
from app.models.invoice import InvoiceStatus
from app.schemas.invoice import (
    FreeTextInvoiceRequest,
    StructuredInvoiceRequest,
    InvoiceResponse,
    InvoiceListResponse,
    InvoiceReconcileRequest,
    InvoiceReconcileResponse,
    LLMInvoiceGenerationError
)
from app.core.security import get_current_user
from app.services.llm_invoice import get_invoice_service
from app.services.pdf_generator import get_pdf_service


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/invoices", tags=["invoices"])


def get_user_account(user: User, db: Session, account_id: Optional[uuid.UUID] = None) -> Account:
    """Get user's account, either specified or default."""
    
    if account_id:
        account = db.query(Account).filter(
            Account.id == account_id,
            Account.user_id == user.id
        ).first()
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
    else:
        # Get user's first account
        account = db.query(Account).filter(Account.user_id == user.id).first()
        if not account:
            raise HTTPException(
                status_code=400, 
                detail="No account found. Please create an account first."
            )
    
    return account


async def generate_pdf_background(invoice_id: uuid.UUID, db_session_factory):
    """Background task to generate PDF for invoice."""
    
    try:
        # Create new database session for background task
        db = db_session_factory()
        
        invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not invoice:
            logger.error(f"Invoice {invoice_id} not found for PDF generation")
            return
        
        # Generate PDF
        pdf_service = get_pdf_service()
        pdf_url = pdf_service.generate_invoice_pdf(invoice)
        
        # Update invoice with PDF URL
        invoice.pdf_url = pdf_url
        db.commit()
        
        logger.info(f"PDF generated for invoice {invoice.invoice_number}: {pdf_url}")
        
    except Exception as e:
        logger.error(f"Background PDF generation failed for invoice {invoice_id}: {e}")
        db.rollback()
    finally:
        db.close()


@router.post("/free-text", response_model=InvoiceResponse)
async def create_invoice_from_text(
    request: FreeTextInvoiceRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> InvoiceResponse:
    """
    Generate invoice from free-text description using LLM.
    
    Example prompt: "Create invoice for KSh 12,000 to Mary Wanjiku (254712345678) 
    for 10 bags of maize at KSh 1,200 each, due in 14 days"
    """
    
    try:
        logger.info(f"Creating invoice from text for user {current_user.id}")
        
        # Get user's account
        account = get_user_account(current_user, db, request.account_id)
        
        # Generate structured invoice data using LLM
        llm_service = get_invoice_service()
        invoice_schema = await llm_service.generate_invoice_from_prompt(request.prompt)
        
        # Create database record
        invoice = Invoice(
            id=uuid.uuid4(),
            account_id=account.id,
            invoice_number=invoice_schema.invoice_number,
            client_name=invoice_schema.client_name,
            client_phone=invoice_schema.client_phone,
            items=[item.dict() for item in invoice_schema.items],
            subtotal=Decimal(str(invoice_schema.subtotal)),
            tax=Decimal(str(invoice_schema.tax)),
            total=Decimal(str(invoice_schema.total)),
            status=InvoiceStatus.ISSUED,  # Auto-issue LLM generated invoices
            due_date=invoice_schema.due_date,
            notes=invoice_schema.notes
        )
        
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
        
        # Generate PDF in background
        background_tasks.add_task(generate_pdf_background, invoice.id, lambda: Session(db.bind))
        
        logger.info(f"Invoice {invoice.invoice_number} created from text")
        
        # Prepare response
        response_data = InvoiceResponse.from_orm(invoice)
        response_data.is_overdue = invoice.is_overdue
        response_data.days_until_due = invoice.days_until_due
        
        return response_data
        
    except LLMInvoiceGenerationError as e:
        logger.error(f"LLM invoice generation failed: {e.message}")
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Invoice generation failed",
                "message": e.message,
                "prompt": e.original_prompt[:100] + "..." if len(e.original_prompt) > 100 else e.original_prompt
            }
        )
    
    except Exception as e:
        logger.error(f"Unexpected error creating invoice from text: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create invoice")


@router.post("/form", response_model=InvoiceResponse)
async def create_structured_invoice(
    request: StructuredInvoiceRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> InvoiceResponse:
    """Create invoice from structured data (traditional form input)."""
    
    try:
        logger.info(f"Creating structured invoice for user {current_user.id}")
        
        # Get user's account
        account = get_user_account(current_user, db, request.account_id)
        
        # Check if invoice number already exists
        existing = db.query(Invoice).filter(
            Invoice.invoice_number == request.invoice_number,
            Invoice.account_id == account.id
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Invoice number {request.invoice_number} already exists"
            )
        
        # Create database record
        invoice = Invoice(
            id=uuid.uuid4(),
            account_id=account.id,
            invoice_number=request.invoice_number,
            client_name=request.client_name,
            client_phone=request.client_phone,
            items=[item.dict() for item in request.items],
            subtotal=Decimal(str(request.subtotal)),
            tax=Decimal(str(request.tax)),
            total=Decimal(str(request.total)),
            status=InvoiceStatus.DRAFT,  # Start as draft for manual invoices
            due_date=request.due_date,
            notes=request.notes
        )
        
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
        
        # Generate PDF in background
        background_tasks.add_task(generate_pdf_background, invoice.id, lambda: Session(db.bind))
        
        logger.info(f"Structured invoice {invoice.invoice_number} created")
        
        # Prepare response
        response_data = InvoiceResponse.from_orm(invoice)
        response_data.is_overdue = invoice.is_overdue
        response_data.days_until_due = invoice.days_until_due
        
        return response_data
        
    except Exception as e:
        logger.error(f"Error creating structured invoice: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create invoice")


@router.get("/", response_model=InvoiceListResponse)
def list_invoices(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by status"),
    client_name: Optional[str] = Query(None, description="Filter by client name"),
    overdue_only: bool = Query(False, description="Show only overdue invoices"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List user's invoices with filtering and pagination."""
    
    try:
        # Get user's accounts
        account_ids = db.query(Account.id).filter(Account.user_id == current_user.id).subquery()
        
        # Build base query
        query = db.query(Invoice).filter(Invoice.account_id.in_(account_ids))
        
        # Apply filters
        if status:
            try:
                status_enum = InvoiceStatus(status.lower())
                query = query.filter(Invoice.status == status_enum)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        
        if client_name:
            query = query.filter(Invoice.client_name.ilike(f"%{client_name}%"))
        
        if overdue_only:
            query = query.filter(
                and_(
                    Invoice.status != InvoiceStatus.PAID,
                    Invoice.due_date < datetime.now()
                )
            )
        
        # Get total count
        total = query.count()
        
        # Apply pagination and ordering
        offset = (page - 1) * per_page
        invoices = query.order_by(desc(Invoice.created_at)).offset(offset).limit(per_page).all()
        
        # Prepare response data
        invoice_responses = []
        for invoice in invoices:
            response_data = InvoiceResponse.from_orm(invoice)
            response_data.is_overdue = invoice.is_overdue
            response_data.days_until_due = invoice.days_until_due
            invoice_responses.append(response_data)
        
        return InvoiceListResponse(
            invoices=invoice_responses,
            total=total,
            page=page,
            per_page=per_page,
            has_next=offset + per_page < total,
            has_prev=page > 1
        )
        
    except Exception as e:
        logger.error(f"Error listing invoices: {e}")
        raise HTTPException(status_code=500, detail="Failed to list invoices")


@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get specific invoice by ID."""
    
    # Get user's account IDs
    account_ids = [acc.id for acc in current_user.accounts]
    
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.account_id.in_(account_ids)
    ).first()
    
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    # Prepare response
    response_data = InvoiceResponse.from_orm(invoice)
    response_data.is_overdue = invoice.is_overdue
    response_data.days_until_due = invoice.days_until_due
    
    return response_data


@router.post("/{invoice_id}/issue", response_model=InvoiceResponse)
def issue_invoice(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Issue a draft invoice (change status from draft to issued)."""
    
    # Get user's account IDs
    account_ids = [acc.id for acc in current_user.accounts]
    
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.account_id.in_(account_ids)
    ).first()
    
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    if invoice.status != InvoiceStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot issue invoice with status: {invoice.status.value}"
        )
    
    invoice.status = InvoiceStatus.ISSUED
    db.commit()
    
    logger.info(f"Invoice {invoice.invoice_number} issued")
    
    response_data = InvoiceResponse.from_orm(invoice)
    response_data.is_overdue = invoice.is_overdue
    response_data.days_until_due = invoice.days_until_due
    
    return response_data


@router.post("/reconcile", response_model=InvoiceReconcileResponse)
def reconcile_invoice(
    request: InvoiceReconcileRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Reconcile invoice with M-Pesa transaction.
    
    Can specify exact transaction_id or auto-match based on amount and date.
    """
    
    try:
        # Get user's account IDs
        account_ids = [acc.id for acc in current_user.accounts]
        
        # Get invoice
        invoice = db.query(Invoice).filter(
            Invoice.id == request.invoice_id,
            Invoice.account_id.in_(account_ids)
        ).first()
        
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")
        
        if invoice.status == InvoiceStatus.PAID:
            return InvoiceReconcileResponse(
                success=False,
                message="Invoice is already marked as paid",
                invoice_id=invoice.id,
                transaction_id=invoice.matched_transaction_id,
                reconciled_at=invoice.reconciled_at
            )
        
        transaction = None
        
        if request.transaction_id:
            # Manual reconciliation with specific transaction
            transaction = db.query(Transaction).filter(
                Transaction.id == request.transaction_id,
                Transaction.account_id == invoice.account_id
            ).first()
            
            if not transaction:
                raise HTTPException(status_code=404, detail="Transaction not found")
        
        else:
            # Auto-match transaction based on amount and date range
            logger.info(f"Auto-matching transaction for invoice {invoice.invoice_number}")
            
            # Define matching criteria
            amount_tolerance = Decimal("50.00")  # Allow ±50 KES tolerance
            min_amount = invoice.total - amount_tolerance
            max_amount = invoice.total + amount_tolerance
            
            # Date range: ±3 days from invoice creation or due date
            start_date = min(invoice.created_at, invoice.due_date) - timedelta(days=3)
            end_date = max(invoice.created_at, invoice.due_date) + timedelta(days=3)
            
            # Find matching unreconciled transactions
            matching_transactions = db.query(Transaction).filter(
                Transaction.account_id == invoice.account_id,
                Transaction.amount.between(min_amount, max_amount),
                Transaction.transaction_time.between(start_date, end_date),
                Transaction.matched_invoice_id.is_(None),  # Not already reconciled
                Transaction.status == "completed"
            ).order_by(
                # Prefer transactions closer to exact amount and date
                func.abs(Transaction.amount - invoice.total),
                Transaction.transaction_time.desc()
            ).all()
            
            if not matching_transactions:
                return InvoiceReconcileResponse(
                    success=False,
                    message=f"No matching transactions found for amount KES {invoice.total} within date range",
                    invoice_id=invoice.id
                )
            
            # Use the best match
            transaction = matching_transactions[0]
            
            logger.info(
                f"Auto-matched transaction {transaction.mpesa_transaction_id} "
                f"(KES {transaction.amount}) to invoice {invoice.invoice_number} "
                f"(KES {invoice.total})"
            )
        
        # Perform reconciliation
        invoice.mark_as_paid(transaction.id)
        transaction.matched_invoice_id = invoice.id
        
        db.commit()
        
        logger.info(f"Invoice {invoice.invoice_number} reconciled with transaction {transaction.mpesa_transaction_id}")
        
        return InvoiceReconcileResponse(
            success=True,
            message="Invoice successfully reconciled",
            invoice_id=invoice.id,
            transaction_id=transaction.id,
            matched_amount=transaction.amount,
            reconciled_at=invoice.reconciled_at
        )
        
    except Exception as e:
        logger.error(f"Error reconciling invoice: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to reconcile invoice")


@router.post("/{invoice_id}/send")
def send_invoice(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    Send invoice via SMS/email (stub implementation).
    
    In production, this would integrate with SMS/email services.
    """
    
    # Get user's account IDs
    account_ids = [acc.id for acc in current_user.accounts]
    
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.account_id.in_(account_ids)
    ).first()
    
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    if invoice.status == InvoiceStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail="Cannot send draft invoice. Please issue it first."
        )
    
    # TODO: Implement actual SMS/email sending
    logger.info(f"Sending invoice {invoice.invoice_number} to {invoice.client_phone}")
    
    return {
        "success": True,
        "message": f"Invoice {invoice.invoice_number} sent to {invoice.client_name}",
        "invoice_id": invoice.id,
        "client_phone": invoice.client_phone,
        "pdf_url": invoice.pdf_url
    }