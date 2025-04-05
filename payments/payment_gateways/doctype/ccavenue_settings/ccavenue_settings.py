# Copyright (c) 2024, Frappe Technologies and contributors
# License: MIT. See LICENSE

import hashlib
import json
import urllib.parse
from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.integrations.utils import create_request_log
from frappe.model.document import Document
from frappe.utils import call_hook_method, get_url

from payments.utils import create_payment_gateway


class CCAvenueSettings(Document):
    supported_currencies = ("INR", "USD", "SGD", "GBP", "EUR")

    def validate(self):
        create_payment_gateway("CCAvenue")
        call_hook_method("payment_gateway_enabled", gateway="CCAvenue")
        if not self.flags.ignore_mandatory:
            self.validate_ccavenue_credentials()

    def validate_ccavenue_credentials(self):
        if self.merchant_id and self.access_code and self.encryption_key:
            # CCAvenue credentials validation
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
        """Create CCAvenue request"""
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
                    _("Seems issue with server's CCAvenue configuration. Don't worry, in case of failure amount will get refunded to your account."),
                ),
                "status": 401,
            }

    def authorize_payment(self):
        """
        Authorize payment when user submits the form on CCAvenue page
        """
        # Process data returned by CCAvenue
        data = self.data
        
        # Identify the status from CCAvenue's response
        if data.get("order_status") == "Success":
            status_changed_to = "Completed"
            self.integration_request.update_status(data, "Completed")
        else:
            status_changed_to = "Failed"
            self.integration_request.update_status(data, "Failed")
        
        self.flags.status_changed_to = status_changed_to
        
        redirect_to = data.get("redirect_to") or None
        redirect_message = data.get("redirect_message") or None

        if self.flags.status_changed_to in ("Authorized", "Verified", "Completed"):
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

            redirect_url = f"payment-success?doctype={self.data.reference_doctype}&docname={self.data.reference_docname}"
        else:
            redirect_url = "payment-failed"

        if redirect_to:
            redirect_url += "&" + urlencode({"redirect_to": redirect_to})
        if redirect_message:
            redirect_url += "&" + urlencode({"redirect_message": redirect_message})

        return {"redirect_to": redirect_url, "status": status_changed_to}

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
        
        # CCAvenue requires the request data to be a query string
        query_string = urllib.parse.urlencode(request_data)
        
        # Encrypt the query string using CCAvenue's encryption method
        encrypted_data = self.encrypt_request_data(query_string)
        
        return {
            "encRequest": encrypted_data,
            "access_code": self.access_code
        }
    
    def encrypt_request_data(self, data):
        """
        Encrypt request data using AES encryption
        
        Note: This is a placeholder. You'll need to implement the actual
        encryption logic according to CCAvenue's documentation.
        """
        # You need to implement AES encryption here according to CCAvenue's documentation
        # Most likely will need to use the Crypto.Cipher.AES module
        
        # For example:
        # from Crypto.Cipher import AES
        # import base64
        # iv = '\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f'
        # aes = AES.new(self.encryption_key.encode(), AES.MODE_CBC, iv.encode())
        # encrypted_data = base64.b64encode(aes.encrypt(self._pad(data).encode())).decode()
        # return encrypted_data
        
        return data  # Replace this with actual encryption logic

    def _pad(self, data):
        """Pad the data to be a multiple of 16"""
        length = 16 - (len(data) % 16)
        return data + chr(length) * length
    
    def decrypt_request_data(self, encrypted_data):
        """
        Decrypt data received from CCAvenue
        
        Note: This is a placeholder. You'll need to implement the actual
        decryption logic according to CCAvenue's documentation.
        """
        # You need to implement AES decryption here according to CCAvenue's documentation
        # Similar to the encryption logic
        
        return encrypted_data  # Replace this with actual decryption logic


@frappe.whitelist(allow_guest=True)
def verify_transaction():
    """Handle CCAvenue's return request after payment"""
    try:
        settings = frappe.get_doc("CCAvenue Settings")
        data = frappe.request.form
        
        # Decrypt the response from CCAvenue
        encrypted_response = data.get("encResp")
        decrypted_data = settings.decrypt_request_data(encrypted_response)
        
        # Parse the decrypted response
        parsed_data = urllib.parse.parse_qs(decrypted_data)
        
        # Get merchant_param1 which contains our reference information
        merchant_param1 = parsed_data.get("merchant_param1", ["{}"])[0]
        reference_info = json.loads(merchant_param1)
        
        token = reference_info.get("token")
        
        # Get the integration request
        integration_request = frappe.get_doc("Integration Request", token)
        
        # Create a response to be processed by the authorize_payment method
        response = {
            "order_status": parsed_data.get("order_status", ["Failure"])[0],
            "tracking_id": parsed_data.get("tracking_id", [""])[0],
            "reference_doctype": reference_info.get("reference_doctype"),
            "reference_docname": reference_info.get("reference_docname"),
            "token": token
        }
        
        # Process the response
        settings.data = frappe._dict(response)
        result = settings.authorize_payment()
        
        # Redirect to appropriate URL
        frappe.local.response["type"] = "redirect"
        frappe.local.response["location"] = get_url(result.get("redirect_to"))
        
    except Exception:
        frappe.log_error(frappe.get_traceback(), "CCAvenue Payment Verification Error")
        frappe.local.response["type"] = "redirect"
        frappe.local.response["location"] = get_url("payment-failed")


@frappe.whitelist()
def get_api_key():
    """Get CCAvenue API key"""
    settings = frappe.get_doc("CCAvenue Settings")
    return settings.access_code