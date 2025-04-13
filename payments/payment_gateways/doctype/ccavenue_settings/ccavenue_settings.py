# Copyright (c) 2024, Frappe Technologies and contributors
# License: MIT. See LICENSE

"""
# Integrating CCAvenue

### 1. Validate Currency Support

Example:

    from payments.utils import get_payment_gateway_controller

    controller = get_payment_gateway_controller("CCAvenue")
    controller().validate_transaction_currency(currency)

### 2. Redirect for payment

Example:

    payment_details = {
        "amount": 600,
        "title": "Payment for bill : 111",
        "description": "payment via cart",
        "reference_doctype": "Payment Request",
        "reference_docname": "PR0001",
        "payer_email": "NuranVerkleij@example.com",
        "payer_name": "Nuran Verkleij",
        "order_id": "111",
        "currency": "INR",
        "payment_gateway": "CCAvenue"
    }

    # Redirect the user to this url
    url = controller().get_payment_url(**payment_details)


### 3. On Completion of Payment

Write a method for `on_payment_authorized` in the reference doctype

Example:

    def on_payment_authorized(payment_status):
        # this method will be called when payment is complete


##### Notes:

payment_status - payment gateway will put payment status on callback.
For CCAvenue payment status is Completed
"""

import json
from urllib.parse import urlencode, quote_plus

import frappe
from frappe import _
from frappe.integrations.utils import create_request_log
from frappe.model.document import Document
from frappe.utils import call_hook_method, get_url, random_string

from payments.payment_gateways.doctype.ccavenue_settings.ccavenue_utils import decrypt, encrypt
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
        """Create a CCAvenue request"""
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

    def create_encrypted_request_data(self, integration_request_name, **kwargs):
        """Create encrypted data for CCAvenue request"""
        # Format the data as required by CCAvenue
        token = kwargs.get('order_id')+"@"+integration_request_name
        merchant_data = {
            'merchant_id': self.merchant_id,
            'order_id': token,
            'currency': kwargs.get('currency', 'INR'),
            'amount': str(kwargs.get('amount')),
            'redirect_url': get_url(
                "/api/method/payments.payment_gateways.doctype.ccavenue_settings.ccavenue_settings.verify_transaction"),
            'cancel_url': get_url(
                "/api/method/payments.payment_gateways.doctype.ccavenue_settings.ccavenue_settings.verify_transaction"),
            'language': 'EN',
            'integration_type': 'iframe_normal',
            "merchant_param1": json.dumps({
                "reference_doctype": kwargs.get("reference_doctype"),
                "reference_docname": kwargs.get("reference_docname"),
                "token": token,
                "user": frappe.session.user  # Add the current user
            }),
            'customer_identifier': kwargs.get('payer_email', '')
        }

        # Create the merchant data string exactly as CCAvenue expects
        merchant_data_string = '&'.join([
            f"{key}={value}" for key, value in merchant_data.items()
        ])
        merchant_data_string = merchant_data_string + '&'

        # Encrypt the data using CCAvenue's encryption method
        encrypted_data = encrypt(merchant_data_string,
                                 self.get_password(fieldname="encryption_key", raise_exception=False))

        return {
            "encRequest": encrypted_data,
            "access_code": self.access_code,
            "merchant_id": self.merchant_id,
            "non_encrypted_data": merchant_data_string
        }

    def get_api_url(self):
        """Get the CCAvenue API URL based on environment"""
        if self.environment == "Production":
            return "https://secure.ccavenue.com/transaction/transaction.do?command=initiateTransaction"
        else:
            return "https://test.ccavenue.com/transaction/transaction.do?command=initiateTransaction"

    @frappe.whitelist()
    def clear(self):
        """Clear all CCAvenue settings"""
        self.merchant_id = self.access_code = None
        self.encryption_key = None
        self.header_img = None
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

        # Get CCAvenue settings
        settings = frappe.get_doc("CCAvenue Settings")

        # Decrypt the response
        decrypted_data = decrypt(encResp, settings.get_password(fieldname="encryption_key", raise_exception=False))

        # Parse the decrypted data (URL encoded key-value pairs)
        response_data = {}
        for param in decrypted_data.split('&'):
            if param and '=' in param:
                key, value = param.split('=', 1)
                response_data[key] = value

        # Extract merchant_param1 and parse the JSON
        merchant_param_str = response_data.get("merchant_param1", "")
        merchant_data = {}

        try:
            # Properly parse the JSON data
            if merchant_param_str:
                parts = merchant_param_str.split(", ")
                for part in parts:
                    if ":" in part:
                        k, v = part.split(":", 1)
                        merchant_data[k.strip()] = v.strip()
                    elif " " in part:
                        k, v = part.split(" ", 1)
                        merchant_data[k.strip()] = v.strip()
            # CRITICAL: Set the session user from merchant_data if available
            user = merchant_data.get("user")
            if user and user != "Guest" and frappe.session.user == "Guest":
                frappe.set_user(user)

                # Create a new session for the user
                frappe.local.login_manager.login_as(user)

                # Log that we've restored the user
                frappe.logger().info(f"CCAvenue: Restored user session for {user}")

        except Exception as e:
            frappe.log_error(f"Error parsing merchant data: {str(e)}")
            frappe.local.response["type"] = "redirect"
            frappe.local.response["location"] = get_url("payment-failed")
            return

        # For security, log the current user
        frappe.logger().info(f"CCAvenue callback - Current user: {frappe.session.user}")

        # Get the integration request
        order_id = merchant_data.get("token")
        integration_request = None

        if order_id:
            integration_request = frappe.get_doc("Integration Request", order_id.split('@')[1])

        if not integration_request:
            frappe.log_error(f"Integration request not found for token: {order_id}", "CCAvenue Payment Error")
            frappe.local.response["type"] = "redirect"
            frappe.local.response["location"] = get_url("payment-failed")
            return


        # Update the data with the response from CCAvenue
        data = json.loads(integration_request.data)

        # Save the user in the integration request data for future reference
        data["user"] = user or frappe.session.user

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

        # Update the integration request with the updated data
        integration_request.data = json.dumps(data)
        integration_request.save()

        # Set status based on order_status
        if response_data.get("order_status") == "Success":
            controller.flags.status_changed_to = "Completed"

        # Call authorize_payment to complete the flow
        result = controller.authorize_payment()

        # Preserve cookies in the redirect
        redirect_location = get_url(result["redirect_to"])

        # Make sure to authenticate user via session cookie
        if user and user != "Guest":
            # Set session cookies explicitly
            frappe.local.cookie_manager.set_cookie("system_user", user)
            frappe.local.cookie_manager.set_cookie("full_name", frappe.db.get_value("User", user, "full_name") or "")
            frappe.local.cookie_manager.set_cookie("user_id", user)
            frappe.local.cookie_manager.set_cookie("sid", frappe.session.sid)

        # Set the cookies in response
        frappe.local.response["set_cookie"] = frappe.local.cookie_manager.cookies

        # Set the redirect with cookie preservation
        frappe.local.response["type"] = "redirect"
        frappe.local.response["location"] = redirect_location

    except Exception as e:
        frappe.log_error(f"{str(e)}\n{frappe.get_traceback()}", "CCAvenue Payment Verification Error")
        frappe.local.response["type"] = "redirect"
        frappe.local.response["location"] = get_url("payment-failed")


@frappe.whitelist(allow_guest=True)
def get_api_key():
    """Get CCAvenue API key (access code)"""
    return frappe.db.get_single_value("CCAvenue Settings", "access_code")


@frappe.whitelist(allow_guest=True)
def restore_user_session():
    """Attempt to restore user session from stored payment data"""
    try:
        # Check if we can get the user from URL params
        reference_doctype = frappe.form_dict.get("reference_doctype")
        reference_docname = frappe.form_dict.get("reference_docname")

        if reference_doctype and reference_docname:
            # Find the most recent integration request for this reference
            integration_requests = frappe.get_all("Integration Request",
                                                  filters={
                                                      "reference_doctype": reference_doctype,
                                                      "reference_docname": reference_docname,
                                                      "status": ["in", ["Completed", "Authorized"]]
                                                  },
                                                  order_by="creation desc",
                                                  limit=1)

            if integration_requests:
                integration_request = frappe.get_doc("Integration Request", integration_requests[0].name)
                data = json.loads(integration_request.data)

                # Try to extract user from data
                user = None

                # First try to get from integration request data
                if data.get("user"):
                    user = data.get("user")

                # Next try merchant_param1 in data
                if not user:
                    merchant_data = {}
                    try:
                        if data.get("merchant_param1"):
                            merchant_data = json.loads(data["merchant_param1"])
                    except:
                        pass

                    user = merchant_data.get("user")

                if user and user != "Guest":
                    # Create a new session for the user
                    frappe.set_user(user)

                    # Create a session using login_manager
                    frappe.local.login_manager.login_as(user)

                    # Set session cookies
                    frappe.local.cookie_manager.set_cookie("system_user", user)
                    frappe.local.cookie_manager.set_cookie("full_name",
                                                           frappe.db.get_value("User", user, "full_name") or "")
                    frappe.local.cookie_manager.set_cookie("user_id", user)
                    frappe.local.cookie_manager.set_cookie("sid", frappe.session.sid)

                    # Set cookies in response
                    frappe.local.response["set_cookie"] = frappe.local.cookie_manager.cookies

                    return {"success": True, "user": user}

        return {"success": False}
    except Exception as e:
        frappe.log_error(f"Session restoration error: {str(e)}\n{frappe.get_traceback()}")
        return {"success": False, "error": str(e)}
