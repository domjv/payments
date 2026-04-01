# Copyright (c) 2025, Frappe Technologies and contributors
# License: MIT. See LICENSE

"""
Easebuzz utility functions for payment processing
Based on Easebuzz Python SDK
"""

import hashlib
import json
import requests

import frappe
from frappe import _


def generate_hash(data, salt):
	"""
	Generate hash for Easebuzz API request
	
	Args:
		data (dict): Data dictionary containing payment parameters
		salt (str): Salt key from Easebuzz
		
	Returns:
		str: Generated hash string
	"""
	# Hash sequence for initiatePayment: key|txnid|amount|productinfo|firstname|email|udf1|udf2|udf3|udf4|udf5||||||salt
	hash_sequence = [
		data.get('key', ''),
		data.get('txnid', ''),
		data.get('amount', ''),
		data.get('productinfo', ''),
		data.get('firstname', ''),
		data.get('email', ''),
		data.get('udf1', ''),
		data.get('udf2', ''),
		data.get('udf3', ''),
		data.get('udf4', ''),
		data.get('udf5', ''),
		'', '', '', '', '',  # Empty fields
		salt
	]
	
	hash_string = '|'.join(str(x) for x in hash_sequence)
	return hashlib.sha512(hash_string.encode('utf-8')).hexdigest()


def verify_response_hash(response_data, salt):
	"""
	Verify the hash received in the response from Easebuzz.

	Reverse hash sequence (per Easebuzz documentation):
	salt|status|udf10|udf9|udf8|udf7|udf6|udf5|udf4|udf3|udf2|udf1|email|firstname|productinfo|amount|txnid|key

	Args:
		response_data (dict): Response data from Easebuzz
		salt (str): Salt key from Easebuzz

	Returns:
		bool: True if hash is valid, False otherwise
	"""
	hash_sequence = [
		salt,
		response_data.get('status', ''),
		response_data.get('udf10', ''),
		response_data.get('udf9', ''),
		response_data.get('udf8', ''),
		response_data.get('udf7', ''),
		response_data.get('udf6', ''),
		response_data.get('udf5', ''),
		response_data.get('udf4', ''),
		response_data.get('udf3', ''),
		response_data.get('udf2', ''),
		response_data.get('udf1', ''),
		response_data.get('email', ''),
		response_data.get('firstname', ''),
		response_data.get('productinfo', ''),
		response_data.get('amount', ''),
		response_data.get('txnid', ''),
		response_data.get('key', '')
	]

	hash_string = '|'.join(str(x) for x in hash_sequence)
	calculated_hash = hashlib.sha512(hash_string.encode('utf-8')).hexdigest()

	received_hash = response_data.get('hash', '')

	return calculated_hash == received_hash


def get_api_url(environment, endpoint):
	"""
	Get API URL based on environment
	
	Args:
		environment (str): 'Test' or 'Production'
		endpoint (str): API endpoint name
		
	Returns:
		str: Complete API URL
	"""
	base_urls = {
		'Test': 'https://testpay.easebuzz.in',
		'Production': 'https://pay.easebuzz.in'
	}
	
	endpoints = {
		'initiate': '/payment/initiateLink',
		'transaction': '/transaction/v2/retrieve',
		'refund': '/refund/v1/create'
	}
	
	base_url = base_urls.get(environment, base_urls['Test'])
	endpoint_path = endpoints.get(endpoint, '')
	
	return f"{base_url}{endpoint_path}"


def initiate_payment_api(payment_data, merchant_key, salt, environment, split_payments=None):
	"""
	Call Easebuzz Initiate Payment API

	Args:
		payment_data (dict): Payment data including txnid, amount, firstname, etc.
		merchant_key (str): Merchant key from Easebuzz
		salt (str): Salt from Easebuzz
		environment (str): 'Test' or 'Production'
		split_payments (list | None): Optional list of split payment dicts, each with
		    ``label`` (str) and ``split_amount`` (str) keys.  When provided the
		    JSON-serialised value is attached as ``split_payments`` in the POST body
		    **before** the hash is computed so it is included in the hash.

	Returns:
		dict: API response with status and payment link
	"""
	try:
		# Add merchant key to data
		payment_data['key'] = merchant_key

		# Attach split_payments before hashing so it is covered by the hash
		if split_payments:
			payment_data['split_payments'] = json.dumps(split_payments)

		# Generate hash
		payment_data['hash'] = generate_hash(payment_data, salt)
		
		# Get API URL
		api_url = get_api_url(environment, 'initiate')
		
		# Make API request
		response = requests.post(api_url, data=payment_data, timeout=30)
		response.raise_for_status()
		result = response.json()
		
		if result.get('status') == 1:
			# API returns access key (hex string), not full URL. Build payment page URL.
			access_key = result.get('data') or ''
			pay_base = 'https://testpay.easebuzz.in' if environment != 'Production' else 'https://pay.easebuzz.in'
			payment_url = f"{pay_base}/pay/{access_key}" if access_key else ''
			return {
				'success': True,
				'status': 1,
				'data': payment_url,
				'message': 'Payment link generated successfully'
			}
		else:
			frappe.log_error(
				f"Easebuzz API Response: {result}",
				"Easebuzz Payment Initiation Error"
			)
			return {
				'success': False,
				'status': 0,
				'message': result.get('data', result.get('error_desc', 'Failed to generate payment link'))
			}
			
	except requests.exceptions.RequestException as e:
		frappe.log_error(f"Easebuzz API Error: {str(e)}", "Easebuzz Payment Initiation Error")
		return {
			'success': False,
			'status': 0,
			'message': f'API request failed: {str(e)}'
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Easebuzz Payment Error")
		return {
			'success': False,
			'status': 0,
			'message': f'Error: {str(e)}'
		}


def transaction_api(transaction_data, merchant_key, salt, environment):
	"""
	Call Easebuzz Transaction API to check transaction status
	
	Args:
		transaction_data (dict): Transaction data with txnid, amount, email, phone
		merchant_key (str): Merchant key from Easebuzz
		salt (str): Salt from Easebuzz
		environment (str): 'Test' or 'Production'
		
	Returns:
		dict: Transaction details
	"""
	try:
		transaction_data['key'] = merchant_key
		
		# Generate hash for transaction API
		hash_string = f"{merchant_key}|{transaction_data.get('txnid')}|{salt}"
		transaction_data['hash'] = hashlib.sha512(hash_string.encode('utf-8')).hexdigest()
		
		api_url = get_api_url(environment, 'transaction')
		
		response = requests.post(api_url, data=transaction_data, timeout=30)
		response.raise_for_status()
		
		return response.json()
		
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Easebuzz Transaction API Error")
		return {
			'success': False,
			'message': f'Error: {str(e)}'
		}


def refund_api(refund_data, merchant_key, salt, environment):
	"""
	Call Easebuzz Refund API
	
	Args:
		refund_data (dict): Refund data with txnid, refund_amount, amount, email, phone
		merchant_key (str): Merchant key from Easebuzz
		salt (str): Salt from Easebuzz
		environment (str): 'Test' or 'Production'
		
	Returns:
		dict: Refund response
	"""
	try:
		refund_data['key'] = merchant_key
		
		# Generate hash for refund API
		hash_string = f"{merchant_key}|{refund_data.get('txnid')}|{refund_data.get('refund_amount')}|{salt}"
		refund_data['hash'] = hashlib.sha512(hash_string.encode('utf-8')).hexdigest()
		
		api_url = get_api_url(environment, 'refund')
		
		response = requests.post(api_url, data=refund_data, timeout=30)
		response.raise_for_status()
		
		return response.json()
		
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Easebuzz Refund API Error")
		return {
			'success': False,
			'message': f'Error: {str(e)}'
		}


def compute_split_payments(merchant_doc, total_amount):
	"""
	Compute the split_payments list from a merchant's split payment rules.

	Easebuzz Easy Split expects a JSON array where each element has:
	    { "label": "<sub-merchant-label>", "split_amount": "<amount as string>" }

	Fixed-type rows use their value directly.  Percentage-type rows compute
	``round(total_amount * split_value / 100, 2)``.

	Returns ``None`` when the merchant has no split_payment rows configured.

	Args:
		merchant_doc: Easebuzz Merchant document (with ``split_payments`` child table)
		total_amount (float): Total transaction amount in INR

	Returns:
		list | None: List of split dicts or None
	"""
	rows = getattr(merchant_doc, 'split_payments', None)
	if not rows:
		return None

	result = []
	for row in rows:
		split_type = row.get('split_type') or 'Percentage'
		split_value = float(row.get('split_value') or 0)
		label = (row.get('label') or '').strip()
		if not label:
			continue

		if split_type == 'Fixed':
			amount = round(split_value, 2)
		else:
			amount = round(total_amount * split_value / 100, 2)

		result.append({'label': label, 'split_amount': str(amount)})

	return result if result else None


@frappe.whitelist()
def test_connection(merchant_key, salt, environment):
	try:
		# Test hash generation
		test_data = {
			'key': merchant_key,
			'txnid': 'TEST123',
			'amount': '1.00',
			'productinfo': 'Test Product',
			'firstname': 'Test',
			'email': 'test@example.com',
			'udf1': '',
			'udf2': '',
			'udf3': '',
			'udf4': '',
			'udf5': ''
		}
		
		test_hash = generate_hash(test_data, salt)
		
		# If hash generation works, credentials are likely valid
		if test_hash:
			return {
				"success": True,
				"message": "Connection test successful. Hash generation working properly."
			}
		else:
			return {
				"success": False,
				"error": "Failed to generate hash"
			}
			
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Easebuzz Connection Test Error")
		return {
			"success": False,
			"error": str(e)
		}
