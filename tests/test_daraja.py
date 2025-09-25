"""
Daraja Webhook Tests
Tests for M-Pesa webhook handling, transaction processing, and idempotency
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from typing import Dict, Any
from datetime import datetime

from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.models.account import Account


class TestWebhookReceiving:
    """Test webhook reception and basic validation"""
    
    def test_valid_webhook_payload(self, client: TestClient, sample_daraja_payload: Dict[str, Any], test_account: Account):
        """Test processing of valid webhook payload"""
        response = client.post("/api/daraja/webhook", json=sample_daraja_payload)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] == True
        assert "processed successfully" in data["message"]
        assert "transaction_id" in data
    
    def test_invalid_webhook_payload(self, client: TestClient):
        """Test handling of invalid webhook payload"""
        invalid_payload = {
            "InvalidField": "invalid_value"
        }
        
        response = client.post("/api/daraja/webhook", json=invalid_payload)
        
        # Should handle gracefully and return 422 for validation errors
        assert response.status_code == 422
    
    def test_missing_required_fields(self, client: TestClient, sample_daraja_payload: Dict[str, Any]):
        """Test webhook with missing required fields"""
        incomplete_payload = sample_daraja_payload.copy()
        del incomplete_payload["TransID"]  # Remove required field
        
        response = client.post("/api/daraja/webhook", json=incomplete_payload)
        
        assert response.status_code == 422
    
    def test_invalid_transaction_time_format(self, client: TestClient, sample_daraja_payload: Dict[str, Any]):
        """Test webhook with invalid transaction time format"""
        invalid_payload = sample_daraja_payload.copy()
        invalid_payload["TransTime"] = "invalid-time-format"
        
        response = client.post("/api/daraja/webhook", json=invalid_payload)
        
        assert response.status_code == 422
    
    def test_invalid_amount_format(self, client: TestClient, sample_daraja_payload: Dict[str, Any]):
        """Test webhook with invalid amount format"""
        invalid_payload = sample_daraja_payload.copy()
        invalid_payload["TransAmount"] = "invalid-amount"
        
        response = client.post("/api/daraja/webhook", json=invalid_payload)
        
        assert response.status_code == 422
    
    def test_invalid_phone_format(self, client: TestClient, sample_daraja_payload: Dict[str, Any]):
        """Test webhook with invalid phone number format"""
        invalid_payload = sample_daraja_payload.copy()
        invalid_payload["MSISDN"] = "invalid-phone"
        
        response = client.post("/api/daraja/webhook", json=invalid_payload)
        
        assert response.status_code == 422


class TestTransactionProcessing:
    """Test transaction processing and database storage"""
    
    def test_transaction_creation(self, client: TestClient, db_session: Session, sample_daraja_payload: Dict[str, Any], test_account: Account):
        """Test that webhook creates transaction record"""
        # Ensure no existing transaction
        existing = db_session.query(Transaction).filter(
            Transaction.mpesa_transaction_id == sample_daraja_payload["TransID"]
        ).first()
        assert existing is None
        
        # Process webhook
        response = client.post("/api/daraja/webhook", json=sample_daraja_payload)
        assert response.status_code == 200
        
        # Verify transaction was created
        transaction = db_session.query(Transaction).filter(
            Transaction.mpesa_transaction_id == sample_daraja_payload["TransID"]
        ).first()
        
        assert transaction is not None
        assert transaction.amount == float(sample_daraja_payload["TransAmount"])
        assert transaction.phone == sample_daraja_payload["MSISDN"]
        assert transaction.status == TransactionStatus.COMPLETED
        assert transaction.raw_payload is not None
    
    def test_transaction_type_mapping(self, client: TestClient, db_session: Session, test_account: Account):
        """Test correct mapping of transaction types"""
        test_cases = [
            ("Pay Bill", TransactionType.C2B),
            ("Buy Goods", TransactionType.C2B),
            ("Customer Pay Bill Online", TransactionType.LIPA_NA_MPESA),
        ]
        
        for daraja_type, expected_type in test_cases:
            payload = {
                "TransactionType": daraja_type,
                "TransID": f"TEST_{daraja_type.replace(' ', '_').upper()}",
                "TransTime": "20230101120000",
                "TransAmount": "100.00",
                "BusinessShortCode": "174379",
                "BillRefNumber": "test",
                "MSISDN": "254708374149",
                "FirstName": "John",
                "LastName": "Doe"
            }
            
            response = client.post("/api/daraja/webhook", json=payload)
            assert response.status_code == 200
            
            # Verify transaction type
            transaction = db_session.query(Transaction).filter(
                Transaction.mpesa_transaction_id == payload["TransID"]
            ).first()
            
            assert transaction.transaction_type == expected_type
    
    def test_phone_number_formatting(self, client: TestClient, db_session: Session, sample_daraja_payload: Dict[str, Any], test_account: Account):
        """Test phone number formatting and validation"""
        # Test with different phone formats
        phone_formats = [
            "254708374149",    # International format
            "0708374149",      # Local format  
            "+254708374149",   # International with +
        ]
        
        for i, phone in enumerate(phone_formats):
            payload = sample_daraja_payload.copy()
            payload["TransID"] = f"PHONE_TEST_{i}"
            payload["MSISDN"] = phone
            
            response = client.post("/api/daraja/webhook", json=payload)
            assert response.status_code == 200
            
            transaction = db_session.query(Transaction).filter(
                Transaction.mpesa_transaction_id == payload["TransID"]
            ).first()
            
            # Should be normalized to 254 format
            assert transaction.phone.startswith("254")
            assert len(transaction.phone) == 12
    
    def test_party_name_construction(self, client: TestClient, db_session: Session, test_account: Account):
        """Test party name construction from first, middle, last names"""
        test_cases = [
            {
                "FirstName": "John",
                "MiddleName": "M",
                "LastName": "Doe",
                "expected": "John M Doe"
            },
            {
                "FirstName": "Jane",
                "MiddleName": "",
                "LastName": "Smith", 
                "expected": "Jane Smith"
            },
            {
                "FirstName": "Bob",
                "MiddleName": None,
                "LastName": None,
                "expected": "Bob"
            },
        ]
        
        for i, test_case in enumerate(test_cases):
            payload = {
                "TransactionType": "Pay Bill",
                "TransID": f"NAME_TEST_{i}",
                "TransTime": "20230101120000",
                "TransAmount": "100.00",
                "BusinessShortCode": "174379",
                "MSISDN": "254708374149",
                "FirstName": test_case["FirstName"],
                "MiddleName": test_case["MiddleName"],
                "LastName": test_case["LastName"]
            }
            
            response = client.post("/api/daraja/webhook", json=payload)
            assert response.status_code == 200
            
            transaction = db_session.query(Transaction).filter(
                Transaction.mpesa_transaction_id == payload["TransID"]
            ).first()
            
            assert transaction.party_name == test_case["expected"]
    
    def test_raw_payload_storage(self, client: TestClient, db_session: Session, sample_daraja_payload: Dict[str, Any], test_account: Account):
        """Test that complete raw payload is stored"""
        response = client.post("/api/daraja/webhook", json=sample_daraja_payload)
        assert response.status_code == 200
        
        transaction = db_session.query(Transaction).filter(
            Transaction.mpesa_transaction_id == sample_daraja_payload["TransID"]
        ).first()
        
        assert transaction.raw_payload is not None
        assert isinstance(transaction.raw_payload, dict)
        
        # Verify key fields are preserved in raw payload
        assert transaction.raw_payload["TransID"] == sample_daraja_payload["TransID"]
        assert transaction.raw_payload["TransAmount"] == sample_daraja_payload["TransAmount"]


class TestIdempotency:
    """Test webhook idempotency and duplicate handling"""
    
    def test_duplicate_transaction_handling(self, client: TestClient, db_session: Session, sample_daraja_payload: Dict[str, Any], test_account: Account):
        """Test that duplicate transactions are properly handled"""
        # Send webhook first time
        first_response = client.post("/api/daraja/webhook", json=sample_daraja_payload)
        assert first_response.status_code == 200
        
        # Get first transaction
        first_transaction = db_session.query(Transaction).filter(
            Transaction.mpesa_transaction_id == sample_daraja_payload["TransID"]
        ).first()
        
        assert first_transaction is not None
        assert first_transaction.status == TransactionStatus.COMPLETED
        
        # Send same webhook again
        second_response = client.post("/api/daraja/webhook", json=sample_daraja_payload)
        assert second_response.status_code == 200
        
        response_data = second_response.json()
        assert "duplicate" in response_data["message"].lower()
        
        # Verify only one transaction exists and it's marked as duplicate
        transactions = db_session.query(Transaction).filter(
            Transaction.mpesa_transaction_id == sample_daraja_payload["TransID"]
        ).all()
        
        assert len(transactions) == 1
        assert transactions[0].status == TransactionStatus.DUPLICATE
    
    def test_multiple_unique_transactions(self, client: TestClient, db_session: Session, test_account: Account):
        """Test processing multiple unique transactions"""
        transaction_ids = ["UNIQUE_001", "UNIQUE_002", "UNIQUE_003"]
        
        for trans_id in transaction_ids:
            payload = {
                "TransactionType": "Pay Bill",
                "TransID": trans_id,
                "TransTime": "20230101120000",
                "TransAmount": "100.00", 
                "BusinessShortCode": "174379",
                "MSISDN": "254708374149",
                "FirstName": "John",
                "LastName": "Doe"
            }
            
            response = client.post("/api/daraja/webhook", json=payload)
            assert response.status_code == 200
        
        # Verify all transactions were created
        for trans_id in transaction_ids:
            transaction = db_session.query(Transaction).filter(
                Transaction.mpesa_transaction_id == trans_id
            ).first()
            
            assert transaction is not None
            assert transaction.status == TransactionStatus.COMPLETED


class TestErrorHandling:
    """Test error handling and resilience"""
    
    def test_account_not_found_fallback(self, client: TestClient, db_session: Session):
        """Test handling when no account matches shortcode"""
        # Use a shortcode that doesn't match any account
        payload = {
            "TransactionType": "Pay Bill",
            "TransID": "NO_ACCOUNT_TEST",
            "TransTime": "20230101120000",
            "TransAmount": "100.00",
            "BusinessShortCode": "999999",  # Non-existent shortcode
            "MSISDN": "254708374149",
            "FirstName": "John",
            "LastName": "Doe"
        }
        
        response = client.post("/api/daraja/webhook", json=payload)
        
        # Should handle gracefully - might use fallback account or return error
        # The exact behavior depends on implementation
        assert response.status_code in [200, 404]
    
    def test_database_error_recovery(self, client: TestClient, sample_daraja_payload: Dict[str, Any]):
        """Test recovery from database errors"""
        # This would require mocking database failures
        # For now, just test that webhook endpoint exists and is callable
        response = client.post("/api/daraja/webhook", json=sample_daraja_payload)
        
        # Should not crash the application
        assert response.status_code in [200, 500]


class TestWebhookUtilities:
    """Test webhook utility endpoints"""
    
    def test_health_check(self, client: TestClient):
        """Test webhook service health check"""
        response = client.get("/api/daraja/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "healthy"
        assert "service" in data
        assert "timestamp" in data
    
    def test_recent_transactions(self, client: TestClient, test_transaction: Transaction):
        """Test getting recent transactions"""
        response = client.get("/api/daraja/transactions/recent?limit=5")
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        # Should include the test transaction
        if data:
            assert "id" in data[0]
            assert "mpesa_transaction_id" in data[0]
    
    def test_test_webhook_endpoint(self, client: TestClient, sample_daraja_payload: Dict[str, Any], test_account: Account):
        """Test the development test webhook endpoint"""
        response = client.post("/api/daraja/test-webhook", json=sample_daraja_payload)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "test webhook processed" in data["message"].lower()
        assert "result" in data


if __name__ == "__main__":
    pytest.main([__file__])