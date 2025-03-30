# Copyright (c) 2024, Frappe Technologies and contributors
# License: MIT. See LICENSE

import base64
import hashlib
import json
from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.integrations.utils import create_request_log
from frappe.model.document import Document
from frappe.utils import call_hook_method, get_url

from payments.utils import create_payment_gateway

# Import necessary libraries for CCAvenue encryption/decryption
from Crypto.Cipher import AES
import binascii

class CCAvenueSettings(Document):
    supported_currencies = ("INR", "USD", "SGD", "GBP", "EUR")

    def validate(self):
        create_payment_gateway("CCAvenue")
        call_hook_method("payment_gateway_enabled", gateway="CCAvenue")
        if not self.flags.ignore_mandatory:
            self.validate_ccavenue_credentials()

    def validate_ccavenue_credentials(self):
        if self.merchant_id and self.access_code and self.encryption_key:
            # We can't validate CCAvenue credentials without making an actual API call
            pass

    def validate_transaction_currency(self, currency):
        if currency not in self.supported_currencies:
            frappe.throw(
                _(
                    "Please select another payment method. CCAvenue does not support transactions in currency '{0}'"
                ).format(currency)
            )

    def get_payment_url(self, **kwargs):
        """Return payment url with several params"""
        # Create unique order id by making it equal to the integration request
        integration_request = create_request_log(kwargs, service_name="CCAvenue")
        kwargs.update(dict(order_id=integration_request.name))

        return get_url(f"./ccavenue_checkout?token={integration_request.name}")

    def create_request(self, data):
        self.data = frappe._dict(data)

        try:
            self.integration_request = frappe.get_doc("Integration Request", self.data.token)
            self.integration_request.update_status(self.data, "Queued")
            return self.authorize_payment()

        except Exception:
            frappe.log_error(frappe.get_traceback())
            return {
                "redirect_to": frappe.redirect_to_message(
                    _("Server Error"),
                    _(
                        "Seems issue with server's CCAvenue configuration. Don't worry, in case of failure amount will get refunded to your account."
                    ),
                ),
                "status": 401,
            }

    def authorize_payment(self):
        """
        Authorize payment when user submits the form on CCAvenue page
        """
        data = self.data
        
        # Get payment status from data
        if data.get("order_status") == "Success":
            status = "Completed"
            self.integration_request.update_status(data, "Completed")
            self.flags.status_changed_to = "Completed"
        else:
            status = "Failed"
            self.integration_request.update_status(data, "Failed")
            
        redirect_to = data.get("redirect_to") or None
        redirect_message = data.get("redirect_message") or None

        if self.flags.status_changed_to == "Completed":
            if self.data.reference_doctype and self.data.reference_docname:
                custom_redirect_to = None
                try:
                    custom_redirect_to = frappe.get_doc(
                        self.data.reference_doctype, self.data.reference_docname
                    ).run_method("on_payment_authorized", self.flags.status_changed_to)
                except Exception:
                    frappe.log_error(frappe.get_traceback())

                if custom_redirect_to:
                    redirect_to = custom_redirect_to

            redirect_url = (
                f"payment-success?doctype={self.data.reference_doctype}&docname={self.data.reference_docname}"
            )
        else:
            redirect_url = "payment-failed"

        if redirect_to:
            redirect_url += "&" + urlencode({"redirect_to": redirect_to})
        if redirect_message:
            redirect_url += "&" + urlencode({"redirect_message": redirect_message})

        return {"redirect_to": redirect_url, "status": status}

    def create_encrypted_request_data(self, **kwargs):
        """Create encrypted data for CCAvenue request"""
        # Format the data as required by CCAvenue
        request_data = {
            "merchant_id": self.merchant_id,
            "order_id": kwargs.get("order_id"),
            "amount": kwargs.get("amount"),
            "currency": kwargs.get("currency", "INR"),
            "redirect_url": get_url(f"/api/method/payments.payment_gateways.doctype.ccavenue_settings.ccavenue_settings.verify_transaction"),
            "cancel_url": get_url(f"/api/method/payments.payment_gateways.doctype.ccavenue_settings.ccavenue_settings.verify_transaction"),
            "language": "EN",
            "billing_name": kwargs.get("payer_name"),
            "billing_email": kwargs.get("payer_email"),
            "merchant_param1": json.dumps({
                "reference_doctype": kwargs.get("reference_doctype"),
                "reference_docname": kwargs.get("reference_docname"),
                "token": kwargs.get("order_id")
            })
        }
        
        # Convert dictionary to query string
        merchant_data = urlencode(request_data)
        
        # Encrypt the data using CCAvenue's encryption method
        encrypted_data = self.encrypt_data(merchant_data)
        
        return {
            "encRequest": encrypted_data,
            "access_code": self.access_code
        }
    
    def encrypt_data(self, merchant_data):
        """Encrypt data using CCAvenue's AES encryption"""
        working_key = self.encryption_key
        
        # AES requires data length to be multiple of 16, pad if needed
        iv = '\x00' * 16
        padded_data = self._pad(merchant_data)
        
        # Create cipher object and encrypt data
        cipher = AES.new(working_key.encode('utf-8'), AES.MODE_CBC, iv.encode('utf-8'))
        encrypted_data = cipher.encrypt(padded_data.encode('utf-8'))
        
        # Encode the encrypted binary data to hexadecimal string
        encrypted_hex = binascii.hexlify(encrypted_data).decode('utf-8')
        return encrypted_hex
    
    def decrypt_data(self, encrypted_data):
        """Decrypt data received from CCAvenue"""
        working_key = self.encryption_key
        
        # Convert the hexadecimal string to binary
        encrypted_binary = binascii.unhexlify(encrypted_data)
        
        # Create cipher object and decrypt data
        iv = '\x00' * 16
        cipher = AES.new(working_key.encode('utf-8'), AES.MODE_CBC, iv.encode('utf-8'))
        decrypted_data = cipher.decrypt(encrypted_binary)
        
        # Remove padding
        return self._unpad(decrypted_data.decode('utf-8'))
    
    def _pad(self, data):
        """Pad data to multiple of 16 bytes (128 bits)"""
        padding_size = 16 - (len(data) % 16)
        padding = chr(padding_size) * padding_size
        return data + padding
    
    def _unpad(self, data):
        """Remove padding from decrypted data"""
        padding_size = ord(data[-1])
        return data[:-padding_size]

    @frappe.whitelist()
    def clear(self):
        self.merchant_id = self.access_code = None
        self.encryption_key = None
        self.redirect_url = None
        self.flags.ignore_mandatory = True
        self.save()

@frappe.whitelist(allow_guest=True)
def verify_transaction():
    """Handle CCAvenue's return request after payment"""
    try:
        # Get the encrypted response from CCAvenue
        encResp = frappe.request.form.get("encResp")
        
        if not encResp:
            frappe.local.response["type"] = "redirect"
            frappe.local.response["location"] = get_url("payment-failed")
            return
            
        # Get merchant param1 which contains reference doctype, docname and token
        settings = frappe.get_doc("CCAvenue Settings")
        
        # Decrypt the response
        decrypted_data = settings.decrypt_data(encResp)
        
        # Parse the decrypted data (URL encoded key-value pairs)
        response_data = {}
        for param in decrypted_data.split('&'):
            key, value = param.split('=')
            response_data[key] = value
        
        # Extract merchant_param1 and parse the JSON
        merchant_data = json.loads(response_data.get("merchant_param1", "{}"))
        
        # Get the integration request
        token = merchant_data.get("token")
        integration_request = frappe.get_doc("Integration Request", token)
        
        # Update the data with the response from CCAvenue
        data = json.loads(integration_request.data)
        data.update({
            "order_status": response_data.get("order_status"),
            "tracking_id": response_data.get("tracking_id"),
            "bank_ref_no": response_data.get("bank_ref_no"),
            "payment_mode": response_data.get("payment_mode"),
            "failure_message": response_data.get("failure_message"),
            "ccavenue_response": response_data
        })
        
        # Create a new controller instance
        controller = frappe.get_doc("CCAvenue Settings")
        controller.data = frappe._dict(data)
        controller.integration_request = integration_request
        
        # Set status based on order_status
        if response_data.get("order_status") == "Success":
            controller.flags.status_changed_to = "Completed"
        
        # Call authorize_payment to complete the flow
        result = controller.authorize_payment()
        
        # Redirect to success/failure page
        frappe.local.response["type"] = "redirect"
        frappe.local.response["location"] = get_url(result["redirect_to"])
        
    except Exception:
        frappe.log_error(frappe.get_traceback(), "CCAvenue Payment Verification Error")
        frappe.local.response["type"] = "redirect"
        frappe.local.response["location"] = get_url("payment-failed")