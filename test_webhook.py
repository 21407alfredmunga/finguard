"""
Example Daraja Webhook Test Script
Use this to test your webhook endpoint during development
"""

import requests
import json
from datetime import datetime

# Your webhook URL (adjust port if needed)
WEBHOOK_URL = "http://localhost:8000/api/daraja/webhook"

# Example M-Pesa C2B callback payload
example_payload = {
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

# Additional test payloads for different scenarios
test_payloads = [
    {
        "name": "Standard PayBill Transaction",
        "payload": {
            "TransactionType": "Pay Bill",
            "TransID": "TEST001",
            "TransTime": datetime.now().strftime("%Y%m%d%H%M%S"),
            "TransAmount": "1000.00",
            "BusinessShortCode": "174379",
            "BillRefNumber": "INV001",
            "InvoiceNumber": "INV-2023-001",
            "OrgAccountBalance": "50000.00",
            "ThirdPartyTransID": "",
            "MSISDN": "254712345678",
            "FirstName": "Jane",
            "MiddleName": "Mary",
            "LastName": "Doe"
        }
    },
    {
        "name": "Buy Goods Transaction",
        "payload": {
            "TransactionType": "Buy Goods",
            "TransID": "TEST002",
            "TransTime": datetime.now().strftime("%Y%m%d%H%M%S"),
            "TransAmount": "500.00",
            "BusinessShortCode": "174379",
            "BillRefNumber": "",
            "InvoiceNumber": "",
            "OrgAccountBalance": "51000.00",
            "ThirdPartyTransID": "",
            "MSISDN": "254798765432",
            "FirstName": "Bob",
            "MiddleName": "",
            "LastName": "Smith"
        }
    },
    {
        "name": "Lipa Na M-Pesa Online",
        "payload": {
            "TransactionType": "Customer Pay Bill Online",
            "TransID": "TEST003",
            "TransTime": datetime.now().strftime("%Y%m%d%H%M%S"),
            "TransAmount": "2500.00",
            "BusinessShortCode": "174379",
            "BillRefNumber": "ORDER123",
            "InvoiceNumber": "WEB-2023-003",
            "OrgAccountBalance": "53500.00",
            "ThirdPartyTransID": "",
            "MSISDN": "254723456789",
            "FirstName": "Alice",
            "MiddleName": "Grace",
            "LastName": "Johnson"
        }
    }
]

def test_webhook(payload, test_name="Test"):
    """Send test payload to webhook endpoint"""
    try:
        print(f"\n=== {test_name} ===")
        print(f"Sending payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(
            WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("✅ Webhook processed successfully")
        else:
            print(f"❌ Webhook failed with status {response.status_code}")
            
        return response.status_code == 200
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def test_duplicate_handling():
    """Test duplicate transaction handling"""
    print("\n=== Testing Duplicate Transaction Handling ===")
    
    duplicate_payload = {
        "TransactionType": "Pay Bill",
        "TransID": "DUPLICATE_TEST",
        "TransTime": datetime.now().strftime("%Y%m%d%H%M%S"),
        "TransAmount": "100.00",
        "BusinessShortCode": "174379",
        "BillRefNumber": "DUP001",
        "MSISDN": "254700000000",
        "FirstName": "Duplicate",
        "LastName": "Test"
    }
    
    # Send first time
    print("Sending transaction first time...")
    first_result = test_webhook(duplicate_payload, "First Transaction")
    
    # Send duplicate
    print("Sending same transaction again...")
    second_result = test_webhook(duplicate_payload, "Duplicate Transaction")
    
    return first_result and second_result


def main():
    """Run webhook tests"""
    print("🚀 FinGuard Lite - Daraja Webhook Test")
    print(f"Testing webhook endpoint: {WEBHOOK_URL}")
    print("Make sure your FastAPI server is running!")
    
    # Test basic connectivity
    try:
        health_response = requests.get("http://localhost:8000/health", timeout=5)
        if health_response.status_code == 200:
            print("✅ Server is running")
        else:
            print("❌ Server health check failed")
            return
    except:
        print("❌ Cannot connect to server. Make sure it's running on localhost:8000")
        return
    
    success_count = 0
    total_tests = len(test_payloads) + 2  # +2 for example payload and duplicate test
    
    # Test example payload
    if test_webhook(example_payload, "Example Payload"):
        success_count += 1
    
    # Test all scenarios
    for test_case in test_payloads:
        if test_webhook(test_case["payload"], test_case["name"]):
            success_count += 1
    
    # Test duplicate handling
    if test_duplicate_handling():
        success_count += 1
    
    # Summary
    print(f"\n{'='*50}")
    print(f"Test Summary: {success_count}/{total_tests} tests passed")
    
    if success_count == total_tests:
        print("🎉 All tests passed! Your webhook is working correctly.")
    else:
        print(f"⚠️  {total_tests - success_count} tests failed. Check the logs above.")


if __name__ == "__main__":
    main()