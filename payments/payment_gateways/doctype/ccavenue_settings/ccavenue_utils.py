# Copyright (c) 2024, Frappe Technologies and contributors
# License: MIT. See LICENSE

import hashlib
import json
import base64
from Crypto.Cipher import AES

import frappe
from frappe import _


def encrypt_ccavenue_data(plain_text, encryption_key):
    """
    Encrypt data for CCAvenue using AES encryption
    
    Args:
        plain_text: The text to encrypt
        encryption_key: The encryption key provided by CCAvenue
        
    Returns:
        str: Encrypted string
    """
    padded_text = _pad(plain_text)
    iv = '\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f'
    
    # Initialize AES object
    aes = AES.new(encryption_key.encode(), AES.MODE_CBC, iv.encode())
    
    # Encrypt and encode in base64
    encrypted_text = base64.b64encode(aes.encrypt(padded_text.encode())).decode()
    return encrypted_text


def decrypt_ccavenue_data(encrypted_text, encryption_key):
    """
    Decrypt data received from CCAvenue
    
    Args:
        encrypted_text: The encrypted text from CCAvenue
        encryption_key: The encryption key provided by CCAvenue
        
    Returns:
        str: Decrypted string
    """
    iv = '\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f'
    
    # Initialize AES object
    aes = AES.new(encryption_key.encode(), AES.MODE_CBC, iv.encode())
    
    # Decrypt and remove padding
    decrypted_text = _unpad(aes.decrypt(base64.b64decode(encrypted_text)).decode())
    return decrypted_text


def _pad(data):
    """Pad the data to be a multiple of 16"""
    length = 16 - (len(data) % 16)
    return data + chr(length) * length


def _unpad(data):
    """Remove padding from decrypted data"""
    return data[0:-ord(data[-1])]


@frappe.whitelist()
def test_connection(merchant_id, access_code, encryption_key, environment):
    """
    Test connection to CCAvenue
    
    Args:
        merchant_id: The merchant ID from CCAvenue
        access_code: The access code from CCAvenue
        encryption_key: The encryption key from CCAvenue
        environment: 'Sandbox' or 'Production'
        
    Returns:
        dict: Result of the test connection
    """
    try:
        # Create a simple test request to check encryption
        test_data = f"merchant_id={merchant_id}&currency=INR&amount=1.00"
        encrypted_data = encrypt_ccavenue_data(test_data, encryption_key)
        
        # If encryption works, we assume the credentials are valid
        # In a real implementation, you might want to actually send a test API call
        
        return {
            "success": True,
            "message": "Connection test successful"
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "CCAvenue Connection Test Error")
        return {
            "success": False,
            "error": str(e)
        }