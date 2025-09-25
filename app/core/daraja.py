"""
Daraja API client for M-Pesa integration
Handles communication with Safaricom's Daraja API
"""

import asyncio
from typing import Optional, Dict, Any
import httpx
import base64
from datetime import datetime
import logging

from ..config import settings

# Configure logging
logger = logging.getLogger(__name__)


class DarajaError(Exception):
    """Custom exception for Daraja API errors"""
    pass


class DarajaClient:
    """
    Client for Safaricom Daraja API
    Handles authentication and API calls to M-Pesa services
    """
    
    def __init__(self):
        self.consumer_key = settings.daraja_consumer_key
        self.consumer_secret = settings.daraja_consumer_secret
        self.base_url = settings.daraja_base_url
        self.passkey = settings.daraja_passkey
        self.shortcode = settings.daraja_shortcode
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
    
    async def _get_access_token(self) -> str:
        """
        Get OAuth access token from Daraja API
        Caches token until expiration
        
        Returns:
            str: Access token
            
        Raises:
            DarajaError: If token request fails
        """
        # Return cached token if still valid
        if (self._access_token and self._token_expires_at and 
            datetime.utcnow() < self._token_expires_at):
            return self._access_token
        
        # Prepare credentials
        credentials = f"{self.consumer_key}:{self.consumer_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/json"
        }
        
        url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, timeout=30)
                
                if response.status_code != 200:
                    logger.error(f"Daraja auth failed: {response.status_code} - {response.text}")
                    raise DarajaError(f"Authentication failed: {response.status_code}")
                
                data = response.json()
                self._access_token = data["access_token"]
                
                # Cache token (expires in 1 hour minus 5 minutes for safety)
                expires_in_seconds = int(data.get("expires_in", 3600)) - 300
                self._token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in_seconds)
                
                logger.info("Daraja access token obtained successfully")
                return self._access_token
                
        except httpx.RequestError as e:
            logger.error(f"Daraja auth request error: {e}")
            raise DarajaError(f"Network error during authentication: {e}")
        except Exception as e:
            logger.error(f"Daraja auth error: {e}")
            raise DarajaError(f"Authentication error: {e}")
    
    async def register_urls(self, confirmation_url: str, validation_url: str) -> bool:
        """
        Register callback URLs for C2B transactions
        
        Args:
            confirmation_url: URL for transaction confirmations
            validation_url: URL for transaction validation
            
        Returns:
            bool: True if registration successful
        """
        access_token = await self._get_access_token()
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "ShortCode": self.shortcode,
            "ResponseType": "Completed",  # Only get confirmation, not validation
            "ConfirmationURL": confirmation_url,
            "ValidationURL": validation_url
        }
        
        url = f"{self.base_url}/mpesa/c2b/v1/registerurl"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers, timeout=30)
                
                if response.status_code == 200:
                    logger.info("Daraja URLs registered successfully")
                    return True
                else:
                    logger.error(f"URL registration failed: {response.status_code} - {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"URL registration error: {e}")
            return False
    
    async def simulate_c2b_transaction(self, phone: str, amount: float, 
                                     account_reference: str = "test") -> Dict[str, Any]:
        """
        Simulate C2B transaction (for testing only)
        
        Args:
            phone: Customer phone number
            amount: Transaction amount
            account_reference: Account reference
            
        Returns:
            Dict: API response
        """
        access_token = await self._get_access_token()
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "ShortCode": self.shortcode,
            "CommandID": "CustomerPayBillOnline",
            "Amount": amount,
            "Msisdn": phone,
            "BillRefNumber": account_reference
        }
        
        url = f"{self.base_url}/mpesa/c2b/v1/simulate"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers, timeout=30)
                
                logger.info(f"C2B simulation response: {response.status_code}")
                return {
                    "success": response.status_code == 200,
                    "status_code": response.status_code,
                    "response": response.json() if response.status_code == 200 else response.text
                }
                
        except Exception as e:
            logger.error(f"C2B simulation error: {e}")
            return {"success": False, "error": str(e)}
    
    async def initiate_stk_push(self, phone: str, amount: float, 
                               account_reference: str, transaction_desc: str) -> Dict[str, Any]:
        """
        Initiate STK Push (Lipa Na M-Pesa Online)
        
        Args:
            phone: Customer phone number
            amount: Transaction amount
            account_reference: Account reference
            transaction_desc: Transaction description
            
        Returns:
            Dict: API response with checkout request ID
        """
        access_token = await self._get_access_token()
        
        # Generate timestamp
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        
        # Generate password (Base64 encoded string)
        password_string = f"{self.shortcode}{self.passkey}{timestamp}"
        password = base64.b64encode(password_string.encode()).decode()
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # Ensure phone number is in correct format
        if phone.startswith('0'):
            phone = '254' + phone[1:]
        elif not phone.startswith('254'):
            phone = '254' + phone
        
        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": amount,
            "PartyA": phone,  # Customer phone number
            "PartyB": self.shortcode,  # Business shortcode
            "PhoneNumber": phone,
            "CallBackURL": f"{settings.app_base_url}/api/daraja/stk-callback",
            "AccountReference": account_reference,
            "TransactionDesc": transaction_desc
        }
        
        url = f"{self.base_url}/mpesa/stkpush/v1/processrequest"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers, timeout=30)
                
                logger.info(f"STK Push response: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "checkout_request_id": data.get("CheckoutRequestID"),
                        "merchant_request_id": data.get("MerchantRequestID"),
                        "response_code": data.get("ResponseCode"),
                        "response_description": data.get("ResponseDescription"),
                        "customer_message": data.get("CustomerMessage")
                    }
                else:
                    return {
                        "success": False,
                        "status_code": response.status_code,
                        "error": response.text
                    }
                    
        except Exception as e:
            logger.error(f"STK Push error: {e}")
            return {"success": False, "error": str(e)}
    
    async def query_stk_status(self, checkout_request_id: str) -> Dict[str, Any]:
        """
        Query STK Push transaction status
        
        Args:
            checkout_request_id: Checkout request ID from STK push
            
        Returns:
            Dict: Transaction status response
        """
        access_token = await self._get_access_token()
        
        # Generate timestamp and password
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        password_string = f"{self.shortcode}{self.passkey}{timestamp}"
        password = base64.b64encode(password_string.encode()).decode()
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id
        }
        
        url = f"{self.base_url}/mpesa/stkpushquery/v1/query"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers, timeout=30)
                
                if response.status_code == 200:
                    return {"success": True, "data": response.json()}
                else:
                    return {"success": False, "error": response.text}
                    
        except Exception as e:
            logger.error(f"STK status query error: {e}")
            return {"success": False, "error": str(e)}


# Global client instance
daraja_client = DarajaClient()


def validate_webhook_signature(payload: bytes, signature: str) -> bool:
    """
    Validate webhook signature from Daraja
    
    Args:
        payload: Raw request body
        signature: Signature header value
        
    Returns:
        bool: True if signature is valid
    """
    # For now, this is a stub - Safaricom doesn't always provide HMAC signatures
    # In production, you might want to validate the source IP or use other security measures
    
    # Basic validation - check if payload is not empty
    if not payload:
        return False
    
    # In a real implementation, you would:
    # 1. Generate HMAC signature using webhook secret
    # 2. Compare with provided signature
    # 3. Return True only if signatures match
    
    logger.info("Webhook signature validation (stub implementation)")
    return True


# Utility function to format Kenyan phone numbers
def format_kenyan_phone(phone: str) -> str:
    """
    Format phone number to Kenyan international format
    
    Args:
        phone: Phone number in various formats
        
    Returns:
        str: Phone number in 254XXXXXXXXX format
    """
    # Remove any non-digits
    phone = ''.join(filter(str.isdigit, phone))
    
    # Convert to international format
    if phone.startswith('254'):
        return phone
    elif phone.startswith('0') and len(phone) == 10:
        return '254' + phone[1:]
    elif len(phone) == 9:
        return '254' + phone
    else:
        raise ValueError(f"Invalid phone number format: {phone}")


# Import timedelta here to avoid circular imports
from datetime import timedelta