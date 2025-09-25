"""
Transaction Schemas
Pydantic models for transaction data validation and serialization
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, validator
import uuid

from ..models.transaction import TransactionType, TransactionStatus


class TransactionBase(BaseModel):
    """Base transaction schema"""
    
    mpesa_transaction_id: str
    transaction_type: TransactionType
    amount: Decimal
    phone: str
    party_name: Optional[str] = None
    reference: Optional[str] = None
    transaction_time: datetime


class TransactionResponse(TransactionBase):
    """Schema for transaction response"""
    
    id: uuid.UUID
    account_id: uuid.UUID
    status: TransactionStatus
    business_short_code: Optional[str] = None
    invoice_number: Optional[str] = None
    org_account_balance: Optional[Decimal] = None
    third_party_trans_id: Optional[str] = None
    created_at: datetime
    processed_at: Optional[datetime] = None
    
    class Config:
        orm_mode = True
        json_encoders = {
            Decimal: lambda v: float(v) if v else None
        }
        schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "account_id": "550e8400-e29b-41d4-a716-446655440001",
                "mpesa_transaction_id": "NLJ7RT61SV",
                "transaction_type": "C2B",
                "amount": 1000.00,
                "phone": "254708374149",
                "party_name": "John Doe",
                "reference": "INV001",
                "transaction_time": "2023-01-01T12:00:00Z",
                "status": "completed",
                "business_short_code": "174379",
                "created_at": "2023-01-01T12:01:00Z",
                "processed_at": "2023-01-01T12:01:30Z"
            }
        }


class TransactionFilter(BaseModel):
    """Schema for filtering transactions"""
    
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    transaction_type: Optional[TransactionType] = None
    status: Optional[TransactionStatus] = None
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None
    phone: Optional[str] = None
    reference: Optional[str] = None
    page: int = 1
    per_page: int = 20
    
    @validator("per_page")
    def validate_per_page(cls, v):
        """Limit per_page to reasonable values"""
        if v < 1:
            return 1
        if v > 100:
            return 100
        return v
    
    @validator("page")
    def validate_page(cls, v):
        """Ensure page is positive"""
        if v < 1:
            return 1
        return v
    
    @validator("end_date")
    def validate_date_range(cls, v, values):
        """Ensure end_date is after start_date"""
        if v and values.get('start_date') and v < values['start_date']:
            raise ValueError("End date must be after start date")
        return v
    
    @validator("max_amount")
    def validate_amount_range(cls, v, values):
        """Ensure max_amount is greater than min_amount"""
        if v and values.get('min_amount') and v < values['min_amount']:
            raise ValueError("Max amount must be greater than min amount")
        return v


class TransactionList(BaseModel):
    """Schema for paginated transaction list"""
    
    transactions: List[TransactionResponse]
    total: int
    page: int
    per_page: int
    pages: int
    summary: Optional[Dict[str, Any]] = None  # Transaction summary stats
    
    class Config:
        schema_extra = {
            "example": {
                "transactions": [],
                "total": 50,
                "page": 1,
                "per_page": 20,
                "pages": 3,
                "summary": {
                    "total_inbound": 45000.00,
                    "total_outbound": 5000.00,
                    "net_amount": 40000.00,
                    "transaction_count": 50
                }
            }
        }


class DarajaCallbackPayload(BaseModel):
    """
    Schema for Daraja M-Pesa callback payload
    Based on Safaricom's C2B callback format
    """
    
    # Core transaction fields
    TransactionType: str
    TransID: str  # M-Pesa transaction ID
    TransTime: str  # Format: YYYYMMDDHHMMSS
    TransAmount: str  # Amount as string
    BusinessShortCode: str
    BillRefNumber: Optional[str] = None  # Account reference
    InvoiceNumber: Optional[str] = None
    OrgAccountBalance: Optional[str] = None
    ThirdPartyTransID: Optional[str] = None
    MSISDN: str  # Customer phone number
    FirstName: Optional[str] = None
    MiddleName: Optional[str] = None
    LastName: Optional[str] = None
    
    # Additional fields that might be present
    KYCInfo: Optional[List[Dict[str, str]]] = None
    
    @validator("TransAmount")
    def validate_trans_amount(cls, v):
        """Validate transaction amount is numeric"""
        try:
            float(v)
            return v
        except (ValueError, TypeError):
            raise ValueError("TransAmount must be a valid number")
    
    @validator("TransTime")
    def validate_trans_time(cls, v):
        """Validate transaction time format"""
        if len(v) != 14:
            raise ValueError("TransTime must be in format YYYYMMDDHHMMSS")
        
        try:
            datetime.strptime(v, "%Y%m%d%H%M%S")
            return v
        except ValueError:
            raise ValueError("Invalid TransTime format")
    
    @validator("MSISDN")
    def validate_msisdn(cls, v):
        """Validate phone number format"""
        # Remove any non-digits
        phone = ''.join(filter(str.isdigit, v))
        
        # Check for valid format (should start with 254)
        if not phone.startswith('254'):
            raise ValueError("MSISDN must start with 254")
        
        if len(phone) != 12:
            raise ValueError("Invalid MSISDN format")
        
        return phone
    
    class Config:
        schema_extra = {
            "example": {
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
        }


class WebhookResponse(BaseModel):
    """Schema for webhook response"""
    
    success: bool
    message: str
    transaction_id: Optional[str] = None
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "message": "Transaction processed successfully",
                "transaction_id": "550e8400-e29b-41d4-a716-446655440000"
            }
        }


class TransactionReconcile(BaseModel):
    """Schema for transaction reconciliation (stub)"""
    
    account_id: uuid.UUID
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    force_reprocess: bool = False
    
    class Config:
        schema_extra = {
            "example": {
                "account_id": "550e8400-e29b-41d4-a716-446655440000",
                "start_date": "2023-01-01T00:00:00Z",
                "end_date": "2023-01-31T23:59:59Z",
                "force_reprocess": False
            }
        }