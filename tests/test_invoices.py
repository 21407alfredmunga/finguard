"""
Tests for Invoice Engine - LLM Service, API endpoints, and PDF generation.

Includes unit tests for LLM wrapper, integration tests for invoice creation,
and reconciliation testing.
"""

import pytest
import json
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models import Invoice, Transaction, Account, User
from app.models.invoice import InvoiceStatus
from app.schemas.invoice import InvoiceSchema, InvoiceItem, LLMInvoiceGenerationError
from app.services.llm_invoice import LLMInvoiceService


class TestLLMInvoiceService:
    """Test LLM Invoice Service functionality."""
    
    @pytest.fixture
    def llm_service(self):
        """Mock LLM service without actual API calls."""
        with patch('app.services.llm_invoice.genai') as mock_genai:
            mock_model = Mock()
            mock_genai.GenerativeModel.return_value = mock_model
            
            service = LLMInvoiceService()
            service.model = mock_model
            return service
    
    def test_generate_invoice_number(self, llm_service):
        """Test invoice number generation."""
        invoice_number = llm_service.generate_invoice_number()
        
        assert invoice_number.startswith("INV-")
        assert len(invoice_number) == 18  # INV- + 14 digit timestamp
    
    def test_validate_phone_number(self, llm_service):
        """Test phone number validation and formatting."""
        
        # Test various input formats
        test_cases = [
            ("0712345678", "254712345678"),
            ("712345678", "254712345678"),
            ("254712345678", "254712345678"),
            ("+254712345678", "254712345678"),
            ("0123456789", "254123456789"),
        ]
        
        for input_phone, expected in test_cases:
            result = llm_service._validate_phone_number(input_phone)
            assert result == expected
        
        # Test invalid formats
        with pytest.raises(ValueError):
            llm_service._validate_phone_number("123456")  # Too short
        
        with pytest.raises(ValueError):
            llm_service._validate_phone_number("255712345678")  # Wrong country code
    
    def test_post_process_invoice_data(self, llm_service):
        """Test invoice data post-processing and validation."""
        
        raw_data = {
            "client_name": "John Doe",
            "client_phone": "0712345678",
            "items": [
                {"description": "Test item", "quantity": 2, "unit_price": 500.00}
            ],
        }
        
        processed = llm_service._post_process_invoice_data(raw_data)
        
        # Check phone number formatting
        assert processed["client_phone"] == "254712345678"
        
        # Check calculations
        assert processed["subtotal"] == 1000.00
        assert processed["tax"] == 160.00  # 16% VAT
        assert processed["total"] == 1160.00
        
        # Check item subtotal
        assert processed["items"][0]["subtotal"] == 1000.00
        
        # Check invoice number generation
        assert "invoice_number" in processed
        assert processed["invoice_number"].startswith("INV-")
        
        # Check due date generation
        assert "due_date" in processed
    
    @pytest.mark.asyncio
    async def test_generate_invoice_success(self, llm_service):
        """Test successful invoice generation from prompt."""
        
        # Mock successful Gemini response
        mock_response = Mock()
        mock_response.text = json.dumps({
            "invoice_number": "INV-20251227142530",
            "client_name": "Mary Wanjiku",
            "client_phone": "254712345678",
            "items": [
                {
                    "description": "Maize bags (90kg each)",
                    "quantity": 10,
                    "unit_price": 1200.00,
                    "subtotal": 12000.00
                }
            ],
            "subtotal": 12000.00,
            "tax": 1920.00,
            "total": 13920.00,
            "due_date": "2025-02-10T23:59:59",
            "notes": "Payment via M-Pesa preferred"
        })
        
        llm_service.model.generate_content.return_value = mock_response
        
        prompt = "Create invoice for KSh 12,000 to Mary Wanjiku (254712345678) for 10 bags of maize"
        result = await llm_service.generate_invoice_from_prompt(prompt)
        
        assert isinstance(result, InvoiceSchema)
        assert result.client_name == "Mary Wanjiku"
        assert result.client_phone == "254712345678"
        assert result.total == 13920.00
        assert len(result.items) == 1
        assert result.items[0].description == "Maize bags (90kg each)"
    
    @pytest.mark.asyncio
    async def test_generate_invoice_invalid_json(self, llm_service):
        """Test handling of invalid JSON response from LLM."""
        
        mock_response = Mock()
        mock_response.text = "This is not valid JSON"
        
        llm_service.model.generate_content.return_value = mock_response
        
        with pytest.raises(LLMInvoiceGenerationError) as exc_info:
            await llm_service.generate_invoice_from_prompt("test prompt")
        
        assert "Invalid JSON response" in str(exc_info.value)
    
    @pytest.mark.asyncio  
    async def test_generate_invoice_validation_error(self, llm_service):
        """Test handling of validation errors in generated data."""
        
        # Mock response with invalid data
        mock_response = Mock()
        mock_response.text = json.dumps({
            "client_name": "Test",
            # Missing required fields
            "items": [],
            "total": -100  # Invalid negative total
        })
        
        llm_service.model.generate_content.return_value = mock_response
        
        with pytest.raises(LLMInvoiceGenerationError) as exc_info:
            await llm_service.generate_invoice_from_prompt("test prompt")
        
        assert "validation failed" in str(exc_info.value)


class TestInvoiceAPI:
    """Test Invoice API endpoints."""
    
    @pytest.fixture
    def client(self):
        """Test client with mocked database."""
        return TestClient(app)
    
    @pytest.fixture
    def auth_headers(self, test_user_token):
        """Authentication headers for API requests."""
        return {"Authorization": f"Bearer {test_user_token}"}
    
    def test_create_invoice_free_text(self, client, auth_headers, db_session):
        """Test free-text invoice creation endpoint."""
        
        with patch('app.services.llm_invoice.get_invoice_service') as mock_service:
            # Mock LLM service response
            mock_invoice = InvoiceSchema(
                invoice_number="INV-TEST001",
                client_name="John Doe",
                client_phone="254712345678",
                items=[
                    InvoiceItem(
                        description="Test item",
                        quantity=1,
                        unit_price=1000.00,
                        subtotal=1000.00
                    )
                ],
                subtotal=1000.00,
                tax=160.00,
                total=1160.00,
                due_date=datetime.now() + timedelta(days=14)
            )
            
            mock_service.return_value.generate_invoice_from_prompt = AsyncMock(return_value=mock_invoice)
            
            response = client.post(
                "/api/invoices/free-text",
                json={"prompt": "Create invoice for KSh 1,000 to John Doe (254712345678)"},
                headers=auth_headers
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["invoice_number"] == "INV-TEST001"
            assert data["client_name"] == "John Doe"
            assert data["total"] == "1160.00"
            assert data["status"] == "issued"
    
    def test_create_structured_invoice(self, client, auth_headers):
        """Test structured invoice creation endpoint."""
        
        invoice_data = {
            "invoice_number": "INV-STRUCT001",
            "client_name": "Jane Smith",
            "client_phone": "254798765432",
            "items": [
                {
                    "description": "Consulting services",
                    "quantity": 5,
                    "unit_price": 2000.00,
                    "subtotal": 10000.00
                }
            ],
            "subtotal": 10000.00,
            "tax": 1600.00,
            "total": 11600.00,
            "due_date": (datetime.now() + timedelta(days=30)).isoformat(),
            "notes": "Monthly consulting fee"
        }
        
        response = client.post(
            "/api/invoices/form",
            json=invoice_data,
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["invoice_number"] == "INV-STRUCT001"
        assert data["client_name"] == "Jane Smith"
        assert data["status"] == "draft"
    
    def test_list_invoices(self, client, auth_headers, test_invoices):
        """Test invoice listing with pagination and filtering."""
        
        # Test basic listing
        response = client.get("/api/invoices/", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "invoices" in data
        assert "total" in data
        assert "page" in data
        
        # Test status filtering
        response = client.get("/api/invoices/?status=paid", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        for invoice in data["invoices"]:
            assert invoice["status"] == "paid"
    
    def test_get_invoice_by_id(self, client, auth_headers, test_invoice):
        """Test getting specific invoice by ID."""
        
        response = client.get(f"/api/invoices/{test_invoice.id}", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert data["id"] == str(test_invoice.id)
        assert data["invoice_number"] == test_invoice.invoice_number
    
    def test_issue_invoice(self, client, auth_headers, db_session):
        """Test issuing a draft invoice."""
        
        # Create draft invoice
        draft_invoice = Invoice(
            id=uuid.uuid4(),
            account_id=test_account.id,  # This needs to be properly mocked
            invoice_number="INV-DRAFT001",
            client_name="Test Client",
            client_phone="254712345678",
            items=[{"description": "Test", "quantity": 1, "unit_price": 100, "subtotal": 100}],
            subtotal=Decimal("100.00"),
            tax=Decimal("16.00"),
            total=Decimal("116.00"),
            status=InvoiceStatus.DRAFT,
            due_date=datetime.now() + timedelta(days=14)
        )
        
        db_session.add(draft_invoice)
        db_session.commit()
        
        response = client.post(f"/api/invoices/{draft_invoice.id}/issue", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "issued"


class TestInvoiceReconciliation:
    """Test invoice reconciliation with M-Pesa transactions."""
    
    def test_manual_reconciliation(self, db_session, test_user, test_account):
        """Test manual reconciliation with specific transaction ID."""
        
        # Create test invoice
        invoice = Invoice(
            id=uuid.uuid4(),
            account_id=test_account.id,
            invoice_number="INV-REC001",
            client_name="Test Client",
            client_phone="254712345678",
            items=[{"description": "Test", "quantity": 1, "unit_price": 1000, "subtotal": 1000}],
            subtotal=Decimal("1000.00"),
            tax=Decimal("160.00"),
            total=Decimal("1160.00"),
            status=InvoiceStatus.ISSUED,
            due_date=datetime.now() + timedelta(days=14)
        )
        
        # Create matching transaction
        transaction = Transaction(
            id=uuid.uuid4(),
            account_id=test_account.id,
            mpesa_transaction_id="TEST123456789",
            amount=Decimal("1160.00"),
            phone="254712345678",
            first_name="Test",
            last_name="Client",
            timestamp=datetime.now(),
            status="completed"
        )
        
        db_session.add_all([invoice, transaction])
        db_session.commit()
        
        # Perform reconciliation
        invoice.mark_as_paid(transaction.id)
        transaction.matched_invoice_id = invoice.id
        db_session.commit()
        
        # Verify reconciliation
        assert invoice.status == InvoiceStatus.PAID
        assert invoice.matched_transaction_id == transaction.id
        assert transaction.matched_invoice_id == invoice.id
        assert invoice.paid_at is not None
    
    def test_auto_reconciliation(self, db_session, test_account):
        """Test automatic reconciliation based on amount and date matching."""
        
        # Create invoice
        invoice_amount = Decimal("2500.00")
        invoice = Invoice(
            id=uuid.uuid4(),
            account_id=test_account.id,
            invoice_number="INV-AUTO001", 
            client_name="Auto Client",
            client_phone="254798765432",
            items=[{"description": "Auto test", "quantity": 1, "unit_price": 2500, "subtotal": 2500}],
            subtotal=Decimal("2500.00"),
            tax=Decimal("0.00"),
            total=invoice_amount,
            status=InvoiceStatus.ISSUED,
            due_date=datetime.now() + timedelta(days=7)
        )
        
        # Create matching transaction (within tolerance)
        matching_transaction = Transaction(
            id=uuid.uuid4(),
            account_id=test_account.id,
            mpesa_transaction_id="AUTO123456789",
            amount=invoice_amount,  # Exact match
            phone="254798765432",
            first_name="Auto",
            last_name="Client",
            timestamp=datetime.now(),
            status="completed"
        )
        
        # Create non-matching transactions
        non_matching_transactions = [
            Transaction(
                id=uuid.uuid4(),
                account_id=test_account.id,
                mpesa_transaction_id="WRONG1",
                amount=Decimal("1000.00"),  # Wrong amount
                phone="254798765432",
                timestamp=datetime.now(),
                status="completed"
            ),
            Transaction(
                id=uuid.uuid4(),
                account_id=test_account.id,
                mpesa_transaction_id="WRONG2",
                amount=invoice_amount,
                phone="254798765432", 
                timestamp=datetime.now() - timedelta(days=10),  # Too old
                status="completed"
            )
        ]
        
        db_session.add_all([invoice, matching_transaction] + non_matching_transactions)
        db_session.commit()
        
        # Find matching transaction (simulating auto-match logic)
        amount_tolerance = Decimal("50.00")
        min_amount = invoice.total - amount_tolerance
        max_amount = invoice.total + amount_tolerance
        
        start_date = invoice.created_at - timedelta(days=3)
        end_date = invoice.created_at + timedelta(days=3)
        
        matching_txns = db_session.query(Transaction).filter(
            Transaction.account_id == invoice.account_id,
            Transaction.amount.between(min_amount, max_amount),
            Transaction.transaction_time.between(start_date, end_date),
            Transaction.status == "completed"
        ).all()
        
        assert len(matching_txns) == 1
        assert matching_txns[0].mpesa_transaction_id == "AUTO123456789"


class TestPDFGeneration:
    """Test PDF generation service."""
    
    @pytest.fixture
    def pdf_service(self):
        """Mock PDF service."""
        with patch('app.services.pdf_generator.WeasyPrint') as mock_weasyprint:
            from app.services.pdf_generator import InvoicePDFService
            return InvoicePDFService()
    
    def test_generate_pdf_filename(self, pdf_service):
        """Test PDF filename generation."""
        
        mock_invoice = Mock()
        mock_invoice.invoice_number = "INV-TEST/001"
        
        filename = pdf_service._generate_pdf_filename(mock_invoice)
        
        assert filename.startswith("invoice_INV-TEST_001_")
        assert filename.endswith(".pdf")
    
    def test_render_html_template(self, pdf_service, test_invoice):
        """Test HTML template rendering."""
        
        html_content = pdf_service._render_html(test_invoice)
        
        # Check that invoice data is in HTML
        assert test_invoice.client_name in html_content
        assert test_invoice.invoice_number in html_content
        assert str(test_invoice.total) in html_content
        
        # Check for proper HTML structure
        assert "<html" in html_content
        assert "</html>" in html_content
        assert "invoice-container" in html_content
    
    @patch('app.services.pdf_generator.HTML')
    def test_generate_invoice_pdf(self, mock_html, pdf_service, test_invoice):
        """Test complete PDF generation flow."""
        
        # Mock WeasyPrint HTML object
        mock_html_obj = Mock()
        mock_html.return_value = mock_html_obj
        
        pdf_url = pdf_service.generate_invoice_pdf(test_invoice)
        
        # Verify HTML was created and PDF was generated
        mock_html.assert_called_once()
        mock_html_obj.write_pdf.assert_called_once()
        
        # Verify URL format
        assert "invoices/" in pdf_url
        assert ".pdf" in pdf_url


# Test fixtures
@pytest.fixture
def test_user(db_session):
    """Create test user."""
    user = User(
        id=uuid.uuid4(),
        phone="254712345678",
        full_name="Test User",
        role="owner"
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_account(db_session, test_user):
    """Create test account."""
    account = Account(
        id=uuid.uuid4(),
        user_id=test_user.id,
        business_name="Test Business",
        currency="KES"
    )
    db_session.add(account)
    db_session.commit()
    return account


@pytest.fixture
def test_invoice(db_session, test_account):
    """Create test invoice."""
    invoice = Invoice(
        id=uuid.uuid4(),
        account_id=test_account.id,
        invoice_number="INV-TEST001",
        client_name="Test Client",
        client_phone="254798765432",
        items=[
            {
                "description": "Test Product",
                "quantity": 2,
                "unit_price": 500.00,
                "subtotal": 1000.00
            }
        ],
        subtotal=Decimal("1000.00"),
        tax=Decimal("160.00"),
        total=Decimal("1160.00"),
        status=InvoiceStatus.ISSUED,
        due_date=datetime.now() + timedelta(days=30)
    )
    db_session.add(invoice)
    db_session.commit()
    return invoice


@pytest.fixture
def test_invoices(db_session, test_account):
    """Create multiple test invoices for listing tests."""
    invoices = []
    
    for i in range(5):
        invoice = Invoice(
            id=uuid.uuid4(),
            account_id=test_account.id,
            invoice_number=f"INV-LIST{i+1:03d}",
            client_name=f"Client {i+1}",
            client_phone=f"25471234567{i}",
            items=[{"description": f"Item {i+1}", "quantity": 1, "unit_price": 1000, "subtotal": 1000}],
            subtotal=Decimal("1000.00"),
            tax=Decimal("160.00"),
            total=Decimal("1160.00"),
            status=InvoiceStatus.PAID if i % 2 == 0 else InvoiceStatus.ISSUED,
            due_date=datetime.now() + timedelta(days=30-i*5)
        )
        invoices.append(invoice)
    
    db_session.add_all(invoices)
    db_session.commit()
    return invoices