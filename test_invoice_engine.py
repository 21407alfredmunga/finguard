#!/usr/bin/env python3
"""
Invoice Engine Testing Script for FinGuard Lite.

Tests free-text invoice generation, structured invoice creation,
PDF generation, and reconciliation with M-Pesa transactions.
"""

import json
import requests
import time
from datetime import datetime, timedelta
from typing import Dict, Any

# Configuration
BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api"

# Test data
TEST_USER_DATA = {
    "phone": "254712345678",
    "full_name": "Invoice Test User",
    "password": "testpassword123",
    "role": "owner"
}

FREE_TEXT_PROMPTS = [
    "Create invoice for KSh 12,000 to Mary Wanjiku (254798765432) for 10 bags of maize at KSh 1,200 each, due in 14 days",
    "Invoice Jane Doe 254723456789 for consulting services KSh 25,000 due next month",
    "Bill John Smith +254734567890 KSh 5,500 for website design, payment in 7 days",
    "Create invoice to Grace Mutua 0745678901 for KSh 8,200 worth of office supplies, 30 day payment terms"
]

STRUCTURED_INVOICE_DATA = {
    "invoice_number": "INV-STRUCT001",
    "client_name": "Structured Test Client",
    "client_phone": "254756789012",
    "items": [
        {
            "description": "Web Development Services",
            "quantity": 40,
            "unit_price": 1250.00,
            "subtotal": 50000.00
        },
        {
            "description": "Domain & Hosting Setup",
            "quantity": 1,
            "unit_price": 5000.00,
            "subtotal": 5000.00
        }
    ],
    "subtotal": 55000.00,
    "tax": 8800.00,
    "total": 63800.00,
    "due_date": (datetime.now() + timedelta(days=30)).isoformat(),
    "notes": "Payment terms: 30 days net. Late payment may incur fees."
}

# Test simulation functions
class InvoiceTestClient:
    """Test client for Invoice Engine testing."""
    
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()
        self.access_token = None
        self.user_id = None
    
    def authenticate(self) -> bool:
        """Authenticate test user and get access token."""
        
        print("🔐 Authenticating test user...")
        
        # Try to signup (might fail if user exists)
        try:
            signup_response = self.session.post(
                f"{API_BASE}/auth/signup",
                json=TEST_USER_DATA
            )
            if signup_response.status_code == 201:
                print("✅ Test user created successfully")
            elif signup_response.status_code == 400:
                print("ℹ️  Test user already exists, proceeding to login")
            else:
                print(f"❌ Signup failed: {signup_response.text}")
        except Exception as e:
            print(f"⚠️  Signup error (continuing): {e}")
        
        # Login to get token
        try:
            login_response = self.session.post(
                f"{API_BASE}/auth/login",
                json={
                    "phone": TEST_USER_DATA["phone"],
                    "password": TEST_USER_DATA["password"]
                }
            )
            
            if login_response.status_code == 200:
                token_data = login_response.json()
                self.access_token = token_data["access_token"]
                self.user_id = token_data["user_id"]
                
                # Set authorization header
                self.session.headers.update({
                    "Authorization": f"Bearer {self.access_token}"
                })
                
                print(f"✅ Authentication successful (User ID: {self.user_id})")
                return True
            else:
                print(f"❌ Login failed: {login_response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return False
    
    def test_free_text_invoice_creation(self) -> Dict[str, Any]:
        """Test free-text invoice creation using LLM."""
        
        print("\n📝 Testing Free-Text Invoice Creation...")
        results = {"success": 0, "failed": 0, "invoices": []}
        
        for i, prompt in enumerate(FREE_TEXT_PROMPTS, 1):
            print(f"\n   Test {i}//{len(FREE_TEXT_PROMPTS)}: {prompt[:50]}...")
            
            try:
                response = self.session.post(
                    f"{API_BASE}/invoices/free-text",
                    json={"prompt": prompt}
                )
                
                if response.status_code == 200:
                    invoice_data = response.json()
                    results["success"] += 1
                    results["invoices"].append(invoice_data)
                    
                    print(f"   ✅ Invoice created: {invoice_data['invoice_number']}")
                    print(f"      Client: {invoice_data['client_name']}")
                    print(f"      Total: KES {invoice_data['total']}")
                    print(f"      Status: {invoice_data['status']}")
                    
                    # Check if PDF is being generated
                    if invoice_data.get('pdf_url'):
                        print(f"      PDF: {invoice_data['pdf_url']}")
                
                else:
                    results["failed"] += 1
                    print(f"   ❌ Failed: {response.status_code} - {response.text}")
            
            except Exception as e:
                results["failed"] += 1
                print(f"   ❌ Error: {e}")
            
            time.sleep(1)  # Rate limiting
        
        print(f"\n📊 Free-Text Results: {results['success']} success, {results['failed']} failed")
        return results
    
    def test_structured_invoice_creation(self) -> Dict[str, Any]:
        """Test structured invoice creation."""
        
        print("\n📋 Testing Structured Invoice Creation...")
        
        try:
            response = self.session.post(
                f"{API_BASE}/invoices/form",
                json=STRUCTURED_INVOICE_DATA
            )
            
            if response.status_code == 200:
                invoice_data = response.json()
                
                print("✅ Structured invoice created successfully")
                print(f"   Invoice: {invoice_data['invoice_number']}")
                print(f"   Client: {invoice_data['client_name']}")
                print(f"   Items: {len(invoice_data['items'])}")
                print(f"   Total: KES {invoice_data['total']}")
                print(f"   Status: {invoice_data['status']}")
                
                return {"success": True, "invoice": invoice_data}
            
            else:
                print(f"❌ Structured invoice creation failed: {response.status_code}")
                print(f"   Error: {response.text}")
                return {"success": False, "error": response.text}
        
        except Exception as e:
            print(f"❌ Structured invoice error: {e}")
            return {"success": False, "error": str(e)}
    
    def test_invoice_listing(self) -> Dict[str, Any]:
        """Test invoice listing with filters."""
        
        print("\n📄 Testing Invoice Listing...")
        
        try:
            # Test basic listing
            response = self.session.get(f"{API_BASE}/invoices/")
            
            if response.status_code == 200:
                data = response.json()
                
                print(f"✅ Listed {len(data['invoices'])} invoices")
                print(f"   Total invoices: {data['total']}")
                print(f"   Page: {data['page']}, Per page: {data['per_page']}")
                
                # Test status filtering
                for status in ["draft", "issued", "paid"]:
                    filter_response = self.session.get(f"{API_BASE}/invoices/?status={status}")
                    if filter_response.status_code == 200:
                        filter_data = filter_response.json()
                        print(f"   {status.title()} invoices: {len(filter_data['invoices'])}")
                
                return {"success": True, "invoices": data['invoices']}
            
            else:
                print(f"❌ Invoice listing failed: {response.status_code}")
                return {"success": False, "error": response.text}
        
        except Exception as e:
            print(f"❌ Invoice listing error: {e}")
            return {"success": False, "error": str(e)}
    
    def test_invoice_operations(self, invoice_id: str) -> Dict[str, Any]:
        """Test individual invoice operations."""
        
        print(f"\n🔧 Testing Invoice Operations (ID: {invoice_id[:8]}...)...")
        
        results = {"get": False, "issue": False, "send": False}
        
        try:
            # Test get invoice
            get_response = self.session.get(f"{API_BASE}/invoices/{invoice_id}")
            if get_response.status_code == 200:
                results["get"] = True
                invoice = get_response.json()
                print(f"   ✅ Get invoice: {invoice['invoice_number']}")
                
                # Test issue invoice (if draft)
                if invoice["status"] == "draft":
                    issue_response = self.session.post(f"{API_BASE}/invoices/{invoice_id}/issue")
                    if issue_response.status_code == 200:
                        results["issue"] = True
                        print("   ✅ Invoice issued successfully")
                    else:
                        print(f"   ❌ Issue failed: {issue_response.text}")
                
                # Test send invoice
                send_response = self.session.post(f"{API_BASE}/invoices/{invoice_id}/send")
                if send_response.status_code == 200:
                    results["send"] = True
                    print("   ✅ Invoice send triggered")
                else:
                    print(f"   ❌ Send failed: {send_response.text}")
            
            else:
                print(f"   ❌ Get invoice failed: {get_response.status_code}")
        
        except Exception as e:
            print(f"   ❌ Operations error: {e}")
        
        return results
    
    def test_reconciliation(self) -> Dict[str, Any]:
        """Test invoice reconciliation with mock transaction."""
        
        print("\n💰 Testing Invoice Reconciliation...")
        
        try:
            # First, create a test invoice for reconciliation
            test_invoice_data = {
                "invoice_number": f"INV-RECON{int(time.time())}",
                "client_name": "Reconciliation Test",
                "client_phone": "254787654321",
                "items": [
                    {
                        "description": "Reconciliation test item",
                        "quantity": 1,
                        "unit_price": 2500.00,
                        "subtotal": 2500.00
                    }
                ],
                "subtotal": 2500.00,
                "tax": 400.00,
                "total": 2900.00,
                "due_date": (datetime.now() + timedelta(days=7)).isoformat()
            }
            
            invoice_response = self.session.post(
                f"{API_BASE}/invoices/form",
                json=test_invoice_data
            )
            
            if invoice_response.status_code != 200:
                print(f"❌ Failed to create test invoice: {invoice_response.text}")
                return {"success": False, "error": "Could not create test invoice"}
            
            invoice = invoice_response.json()
            invoice_id = invoice["id"]
            
            print(f"   📄 Created test invoice: {invoice['invoice_number']}")
            
            # Test auto-reconciliation (this would normally find matching transactions)
            reconcile_data = {"invoice_id": invoice_id}
            
            reconcile_response = self.session.post(
                f"{API_BASE}/invoices/reconcile",
                json=reconcile_data
            )
            
            if reconcile_response.status_code == 200:
                reconcile_result = reconcile_response.json()
                
                if reconcile_result["success"]:
                    print(f"   ✅ Auto-reconciliation successful")
                    print(f"      Matched amount: KES {reconcile_result.get('matched_amount', 'N/A')}")
                else:
                    print(f"   ℹ️  No matching transactions found (expected)")
                    print(f"      Message: {reconcile_result['message']}")
                
                return {"success": True, "result": reconcile_result}
            
            else:
                print(f"   ❌ Reconciliation failed: {reconcile_response.text}")
                return {"success": False, "error": reconcile_response.text}
        
        except Exception as e:
            print(f"   ❌ Reconciliation error: {e}")
            return {"success": False, "error": str(e)}
    
    def run_comprehensive_test(self) -> Dict[str, Any]:
        """Run comprehensive invoice engine test suite."""
        
        print("🚀 Starting FinGuard Invoice Engine Test Suite")
        print("=" * 60)
        
        # Check server health
        try:
            health_response = self.session.get(f"{self.base_url}/health")
            if health_response.status_code != 200:
                print("❌ Server health check failed")
                return {"success": False, "error": "Server not accessible"}
            print("✅ Server health check passed")
        except Exception as e:
            print(f"❌ Cannot connect to server: {e}")
            return {"success": False, "error": str(e)}
        
        # Authenticate
        if not self.authenticate():
            return {"success": False, "error": "Authentication failed"}
        
        results = {
            "free_text": None,
            "structured": None,
            "listing": None,
            "operations": None,
            "reconciliation": None
        }
        
        # Test free-text invoice creation
        results["free_text"] = self.test_free_text_invoice_creation()
        
        # Test structured invoice creation
        results["structured"] = self.test_structured_invoice_creation()
        
        # Test invoice listing
        results["listing"] = self.test_invoice_listing()
        
        # Test individual invoice operations
        if results["structured"]["success"] and "invoice" in results["structured"]:
            invoice_id = results["structured"]["invoice"]["id"]
            results["operations"] = self.test_invoice_operations(invoice_id)
        
        # Test reconciliation
        results["reconciliation"] = self.test_reconciliation()
        
        # Summary
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        
        if results["free_text"]:
            print(f"Free-text invoices: {results['free_text']['success']}/{len(FREE_TEXT_PROMPTS)} successful")
        
        print(f"Structured invoice: {'✅' if results['structured']['success'] else '❌'}")
        print(f"Invoice listing: {'✅' if results['listing']['success'] else '❌'}")
        print(f"Invoice operations: {'✅' if results['operations'] and all(results['operations'].values()) else '❌'}")
        print(f"Reconciliation: {'✅' if results['reconciliation']['success'] else '❌'}")
        
        print("\n🎉 Invoice Engine testing complete!")
        
        return results


def main():
    """Run the invoice engine test suite."""
    
    client = InvoiceTestClient()
    results = client.run_comprehensive_test()
    
    # Return appropriate exit code
    if any(not result.get("success", True) for result in results.values() if result):
        exit(1)
    else:
        exit(0)


if __name__ == "__main__":
    main()