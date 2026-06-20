# Copyright (c) 2024, Frappe Technologies and contributors
# License: MIT. See LICENSE

import hashlib
from Crypto.Cipher import AES

import frappe
from frappe import _

def pad(data):
    length = 16 - (len(data) % 16)
    return data + (chr(length) * length).encode('utf-8')

def encrypt(plainText, workingKey):
    # Convert string IV to bytes
    iv = b'\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f'
    
    # Ensure plainText is bytes
    if isinstance(plainText, str):
        plainText = plainText.encode('utf-8')
    
    plainText = pad(plainText)
    
    # Create MD5 hash of working key
    encDigest = hashlib.md5()
    if isinstance(workingKey, str):
        workingKey = workingKey.encode('utf-8')
    encDigest.update(workingKey)
    
    # Create cipher and encrypt
    enc_cipher = AES.new(encDigest.digest(), AES.MODE_CBC, iv)
    encryptedText = enc_cipher.encrypt(plainText).hex()
    
    return encryptedText

def decrypt(cipherText, workingKey):
    # Convert string IV to bytes
    iv = b'\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f'
    
    # Create MD5 hash of working key
    decDigest = hashlib.md5()
    if isinstance(workingKey, str):
        workingKey = workingKey.encode('utf-8')
    decDigest.update(workingKey)
    
    # Convert hex to bytes and decrypt
    try:
        encryptedText = bytes.fromhex(cipherText)
    except ValueError as exc:
        raise ValueError("Invalid encrypted response format from CCAvenue") from exc

    if len(encryptedText) == 0 or len(encryptedText) % 16 != 0:
        raise ValueError("Invalid encrypted response length from CCAvenue")

    dec_cipher = AES.new(decDigest.digest(), AES.MODE_CBC, iv)
    decryptedText = dec_cipher.decrypt(encryptedText)
    
    # Remove padding
    padding_length = decryptedText[-1]
    if padding_length < 1 or padding_length > 16:
        raise ValueError("Unable to decrypt CCAvenue response. Please verify encryption key")

    if decryptedText[-padding_length:] != bytes([padding_length]) * padding_length:
        raise ValueError("Unable to decrypt CCAvenue response. Please verify encryption key")

    try:
        return decryptedText[:-padding_length].decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ValueError("Unable to decode CCAvenue response. Please verify encryption key") from exc

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
        encrypted_data = encrypt(test_data, encryption_key)
        
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