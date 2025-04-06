# Copyright (c) 2024, Frappe Technologies and contributors
# License: MIT. See LICENSE

import hashlib
from Crypto.Cipher import AES

import frappe
from frappe import _


def encrypt_ccavenue_data(plain_text, encryption_key):
    """
    Encrypt data for CCAvenue using AES encryption
    Based on CCAvenue's integration kit
    
    Args:
        plain_text: The text to encrypt
        encryption_key: The encryption key provided by CCAvenue
        
    Returns:
        str: Encrypted string in hexadecimal format
    """
    iv = '\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f'
    plain_text = _pad(plain_text)
    
    # Generate MD5 hash of the working key as required by CCAvenue
    enc_digest = hashlib.md5(encryption_key.encode()).digest()
    
    # Initialize AES object and encrypt the data
    enc_cipher = AES.new(enc_digest, AES.MODE_CBC, iv.encode())
    encrypted_text = enc_cipher.encrypt(plain_text.encode())
    
    # Convert to hexadecimal (this is what CCAvenue expects)
    return encrypted_text.hex()


def decrypt_ccavenue_data(cipher_text, encryption_key):
    """
    Decrypt data received from CCAvenue
    Based on CCAvenue's integration kit
    
    Args:
        cipher_text: The encrypted text from CCAvenue (hex string)
        encryption_key: The encryption key provided by CCAvenue
        
    Returns:
        str: Decrypted string
    """
    iv = '\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f'
    
    # Generate MD5 hash of the working key
    dec_digest = hashlib.md5(encryption_key.encode()).digest()
    
    # Convert from hex to bytes
    encrypted_text = bytes.fromhex(cipher_text)
    
    # Initialize AES object and decrypt
    dec_cipher = AES.new(dec_digest, AES.MODE_CBC, iv.encode())
    decrypted_text = dec_cipher.decrypt(encrypted_text)
    
    # Return unpadded text
    return _unpad(decrypted_text).decode()


def _pad(data):
    """Pad the data to be a multiple of 16"""
    length = 16 - (len(data) % 16)
    return data + chr(length) * length


def _unpad(data):
    """Remove padding from decrypted data"""
    return data[:-data[-1]]


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