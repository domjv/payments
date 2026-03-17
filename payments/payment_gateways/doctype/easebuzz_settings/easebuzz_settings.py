# Copyright (c) 2025, Frappe Technologies and contributors
# License: MIT. See LICENSE

"""
# Integrating Easebuzz

### 1. Validate Currency Support

Example:

    from payments.utils import get_payment_gateway_controller

    controller = get_payment_gateway_controller("Easebuzz")
    controller().validate_transaction_currency(currency)

### 2. Redirect for payment

Example:

    payment_details = {
        "amount": 600,
        "title": "Payment for bill : 111",
        "description": "payment via cart",
        "reference_doctype": "Payment Request",
        "reference_docname": "PR0001",
        "payer_email": "customer@example.com",
        "payer_name": "Customer Name",
        "order_id": "111",
        "currency": "INR",
        "payment_gateway": "Easebuzz"
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
For Easebuzz payment status is Completed
"""

import json
import urllib
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse
import math

import frappe
from frappe import _
from frappe.integrations.utils import create_request_log
from frappe.model.document import Document
from frappe.utils import call_hook_method
from frappe.utils.data import get_url

from payments.payment_gateways.doctype.easebuzz_settings.easebuzz_utils import (
    generate_hash,
    verify_response_hash,
    initiate_payment_api,
    transaction_api,
    refund_api
)
from payments.utils import create_payment_gateway


class EasebuzzSettings(Document):
    supported_currencies = ("INR",)

    def validate(self):
        create_payment_gateway("Easebuzz")
        call_hook_method("payment_gateway_enabled", gateway="Easebuzz")
        if not self.flags.ignore_mandatory:
            self.validate_easebuzz_credentials()

    def validate_easebuzz_credentials(self):
        if self.merchant_key and self.salt:
            # We can validate by generating a test hash
            pass

    def get_merchant_for_company(self, company=None, merchant_name=None):
        """
        Get the appropriate merchant configuration based on company.
        Priority: 
        1. Explicit merchant_name if provided
        2. Company-specific merchant
        3. Default merchant
        
        Args:
            company (str): Company name to find merchant for
            merchant_name (str): Explicit merchant name to use
            
        Returns:
            Document: Easebuzz Merchant document or None
        """
        # If explicit merchant name provided, use it
        if merchant_name:
            try:
                return frappe.get_doc("Easebuzz Merchant", merchant_name)
            except frappe.DoesNotExistError:
                frappe.log_error(f"Merchant {merchant_name} not found, falling back to company/default merchant")
        
        # Try to find company-specific merchant
        if company:
            merchant = frappe.db.get_value(
                "Easebuzz Merchant",
                {"company": company},
                ["name"],
                as_dict=False
            )
            if merchant:
                return frappe.get_doc("Easebuzz Merchant", merchant)
        
        # Fall back to default merchant
        default_merchant_name = frappe.db.get_value(
            "Easebuzz Merchant",
            {"is_default": 1},
            "name"
        )
        
        if default_merchant_name:
            return frappe.get_doc("Easebuzz Merchant", default_merchant_name)
        
        # If no default exists, try to create or get one
        from payments.payment_gateways.doctype.easebuzz_merchant.easebuzz_merchant import get_default_merchant
        default_merchant_name = get_default_merchant()
        
        if default_merchant_name:
            return frappe.get_doc("Easebuzz Merchant", default_merchant_name)
        
        frappe.throw(_("No Easebuzz Merchant configuration found. Please create a merchant configuration."))

    def validate_transaction_currency(self, currency):
        if currency not in self.supported_currencies:
            frappe.throw(
                _(
                    "Please select another payment method. Easebuzz does not support transactions in currency '{0}'"
                ).format(currency)
            )

    def get_payment_url(self, **kwargs):
        """Return payment url with several params"""
        # Create unique order id by making it equal to the integration request
        integration_request = create_request_log(kwargs, service_name="Easebuzz")
        kwargs.update(dict(order_id=integration_request.name))

        return get_url(f"./easebuzz_checkout?token={integration_request.name}")

    def create_request(self, data):
        """Create an Easebuzz request"""
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
                        "Seems issue with server's Easebuzz configuration. Don't worry, in case of failure amount will get refunded to your account."
                    ),
                ),
                "status": 401,
            }

    def authorize_payment(self):
        """
        Authorize payment when user completes payment on Easebuzz
        """
        data = self.data
        
        # Get payment status from data
        if data.get("status") == "success":
            status = "Completed"
            self.integration_request.update_status(data, "Completed")
            self.flags.status_changed_to = "Completed"
        else:
            status = "Failed"
            self.integration_request.update_status(data, "Failed")

        # Priority: 1. Easebuzz Settings redirect_to, 2. Custom redirect from doctype
        redirect_to = None
        
        # Check if redirect_to is configured in Easebuzz Settings
        if hasattr(self, 'redirect_to') and self.redirect_to:
            redirect_to = self.redirect_to

        redirect_message = data.get("redirect_message") or None

        if self.flags.status_changed_to == "Completed":
            if self.data.reference_doctype and self.data.reference_docname:
                custom_redirect_to = None
                try:
                    # Get the document
                    doc = frappe.get_doc(self.data.reference_doctype, self.data.reference_docname)
                    
                    # Add comment to track payment source
                    webhook_source = self.data.get("webhook_source", "redirect")
                    comment_text = f"""<b>Easebuzz Payment Processed</b><br>
Source: {webhook_source}<br>
Status: {self.data.get("status", "success")}<br>
Transaction ID: {self.data.get("easepayid", "N/A")}<br>
Payment Mode: {self.data.get("mode", "N/A")}<br>
Integration Request: {self.integration_request.name}"""
                    
                    try:
                        doc.add_comment("Info", comment_text)
                    except Exception as comment_error:
                        frappe.log_error(f"Failed to add comment: {str(comment_error)}", "Easebuzz Comment Error")
                    
                    # Call the appropriate handler based on doctype
                    if self.data.reference_doctype == "Sales Invoice":
                        # Call the handler function directly
                        from payments.overrides.sales_invoice import handle_payment_authorization_sales_invoice
                        custom_redirect_to = handle_payment_authorization_sales_invoice(doc, "on_payment_authorized", self.flags.status_changed_to)
                    elif self.data.reference_doctype == "Payment Request":
                        from payments.utils.ivyliving_methods import handle_payment_authorization_payment_request
                        custom_redirect_to = handle_payment_authorization_payment_request(doc, "on_payment_authorized", self.flags.status_changed_to)
                    elif self.data.reference_doctype == "Customer":
                        from payments.utils.ivyliving_methods import handle_payment_authorization_customer
                        custom_redirect_to = handle_payment_authorization_customer(doc, "on_payment_authorized", self.flags.status_changed_to)
                    else:
                        # Try run_method for other doctypes
                        if hasattr(doc, 'on_payment_authorized'):
                            custom_redirect_to = doc.run_method("on_payment_authorized", self.flags.status_changed_to)
                except Exception as e:
                    frappe.log_error(
                        f"Error in on_payment_authorized for {self.data.reference_doctype} {self.data.reference_docname}: {str(e)}\n{frappe.get_traceback()}",
                        "Easebuzz Payment Authorization Error"
                    )

                # Only use custom redirect if explicitly returned and no redirect_to already set
                if custom_redirect_to and not redirect_to:
                    redirect_to = custom_redirect_to

            # If redirect_to is set, redirect to frontend with integration_id only
            if redirect_to:
                # Parse the redirect_to URL to append params correctly
                parsed_url = urlparse(redirect_to)
                query_params = parse_qs(parsed_url.query)
                
                # Add only integration_id - frontend can fetch all details via API
                payment_params = {
                    "integration_id": self.integration_request.name
                }
                
                # Merge with existing query params
                query_params.update({k: [v] for k, v in payment_params.items()})
                
                # Reconstruct URL with params
                new_query = urlencode({k: v[0] for k, v in query_params.items()})
                redirect_url = urlunparse((
                    parsed_url.scheme,
                    parsed_url.netloc,
                    parsed_url.path,
                    parsed_url.params,
                    new_query,
                    parsed_url.fragment
                ))
            else:
                # Show payment success page without auto-redirect
                redirect_url = (
                    f"payment-success?doctype={self.data.reference_doctype}&docname={self.data.reference_docname}"
                )
        else:
            # Failed payment
            if redirect_to:
                # Redirect to frontend with integration_id only
                parsed_url = urlparse(redirect_to)
                query_params = parse_qs(parsed_url.query)
                
                payment_params = {
                    "integration_id": self.integration_request.name
                }
                
                query_params.update({k: [v] for k, v in payment_params.items()})
                new_query = urlencode({k: v[0] for k, v in query_params.items()})
                redirect_url = urlunparse((
                    parsed_url.scheme,
                    parsed_url.netloc,
                    parsed_url.path,
                    parsed_url.params,
                    new_query,
                    parsed_url.fragment
                ))
            else:
                redirect_url = "payment-failed"

        if redirect_message and not redirect_to:
            redirect_url += "&" + urlencode({"redirect_message": redirect_message}) if "?" in redirect_url else "?" + urlencode({"redirect_message": redirect_message})

        return {"redirect_to": redirect_url, "status": status}

    def create_payment_request_data(self, integration_request_name, **kwargs):
        """Create payment data for Easebuzz request"""
        # Easebuzz txnid: alphanumeric + hyphen only (no @). Use integration request name as unique id.
        order_id = kwargs.get('order_id', integration_request_name)
        txnid = integration_request_name  # unique, gateway-safe format
        token = txnid  # callback uses this to look up Integration Request
        
        # Get company and merchant
        company = kwargs.get('company')
        merchant_name = kwargs.get('custom_merchant_name')
        
        # Get the appropriate merchant configuration
        merchant_doc = self.get_merchant_for_company(company=company, merchant_name=merchant_name)
        
        # Get customer details
        customer_name = kwargs.get('payer_name')  # This should be customer ID/name
        customer_dict = {}
        billing_name = customer_name  # Default to customer ID
        
        # Try to get customer document if it exists
        if customer_name and frappe.db.exists("Customer", customer_name):
            customer_dict = frappe.get_doc("Customer", customer_name).as_dict()
            # Use customer_name field for display name (billing)
            billing_name = customer_dict.get('customer_name') or customer_name
        
        # Calculate charges
        charge_list = frappe.get_all("Payment Charge", filters={'disabled': 0}, fields=['*'])
        outstanding_amount = kwargs.get('amount')
        total_charges = 0
        for charge in charge_list:
            charge_amount = (outstanding_amount * charge.charge_percent / 100)
            charge_amount = math.ceil(charge_amount * 100) / 100
            total_charges = total_charges + charge_amount
        final_amount = outstanding_amount + total_charges
        
        # Get merchant environment
        merchant_environment = merchant_doc.get('environment', 'Test')
        
        # Get customer mobile
        phone = customer_dict.get('mobile_no') or customer_dict.get('phone') or kwargs.get('phone', '9999999999')
        
        # zipcode: Easebuzz expects numeric only (e.g. 6 digits for India)
        zipcode_raw = kwargs.get('custom_pincode') or customer_dict.get('custom_pincode') or ''
        zipcode = "000000"
        if zipcode_raw and str(zipcode_raw).strip():
            s = str(zipcode_raw).strip()
            if s.isdigit():
                zipcode = s[:10]  # cap length
            else:
                zipcode = "".join(c for c in s if c.isdigit()) or "000000"

        # udf1-udf5: one value each (Easebuzz allows ^[a-zA-Z.0-9/\\,\s_#@\-=+&]{1,300}$ per field; no pipe)
        def _udf_sanitize(s):
            if s is None:
                return ""
            allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.0123456789/\\,_ #@-=+&")
            return "".join(c if c in allowed else "_" for c in str(s).strip())[:300]

        udf1_val = _udf_sanitize(kwargs.get("reference_doctype"))
        udf2_val = _udf_sanitize(kwargs.get("reference_docname"))
        udf3_val = _udf_sanitize(token)
        udf4_val = _udf_sanitize(frappe.session.user or "Guest")
        udf5_val = _udf_sanitize(merchant_doc.name)

        # Build payment data
        payment_data = {
            'txnid': txnid,
            'amount': str(final_amount),
            'productinfo': (kwargs.get('description') or 'Payment')[:500],
            'firstname': (billing_name or 'Customer')[:100],
            'phone': str(phone)[:15] if phone else '9999999999',
            'email': kwargs.get('payer_email') or frappe.session.user or '',
            'surl': get_url(
                f"/api/method/payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.verify_transaction?merchant={merchant_doc.name}"),
            'furl': get_url(
                f"/api/method/payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.verify_transaction?merchant={merchant_doc.name}"),
            'udf1': udf1_val,
            'udf2': udf2_val,
            'udf3': udf3_val,
            'udf4': udf4_val,
            'udf5': udf5_val,
            'address1': (f'{customer_dict.get("custom_house_no__floor", "")} {customer_dict.get("custom_building__block_number", "")} {customer_dict.get("custom_landmark__area_name", "")}'.strip() or "NA")[:250],
            'address2': '',
            'city': (customer_dict.get('custom_city') or "NA")[:50],
            'state': (kwargs.get('custom_state') or customer_dict.get('custom_state') or 'NA')[:50],
            'country': 'India',
            'zipcode': zipcode,
        }
        
        return {
            "payment_data": payment_data,
            "merchant_key": merchant_doc.get('merchant_key'),
            "salt": merchant_doc.get_password(fieldname="salt", raise_exception=False),
            "merchant_name": merchant_doc.name,
            "environment": merchant_environment
        }

    def get_api_url(self, environment=None):
        """Get the Easebuzz API URL based on environment"""
        if not environment:
            environment = self.environment
        
        if environment == "Production":
            return "https://pay.easebuzz.in"
        else:
            return "https://testpay.easebuzz.in"

    @frappe.whitelist()
    def clear(self):
        """Clear all Easebuzz settings"""
        self.merchant_key = self.salt = None
        self.header_img = None
        self.flags.ignore_mandatory = True
        self.save()


@frappe.whitelist(allow_guest=True)
def initiate_payment(**kwargs):
    """
    API endpoint to initiate an Easebuzz payment from frontend/mobile app.
    
    Args:
        amount (float): Payment amount
        currency (str): Currency code (default: INR)
        reference_doctype (str): Reference document type
        reference_docname (str): Reference document name
        company (str): Company name for merchant selection
        payer_email (str): Payer email address
        payer_name (str): Customer ID or name
        description (str): Payment description
        custom_merchant_name (str, optional): Specific merchant to use
        custom_pincode (str, optional): Customer pincode
        custom_state (str, optional): Customer state
        phone (str, optional): Customer phone number
        
    Returns:
        dict: Payment initiation data including:
            - payment_token: Integration request name
            - payment_url: Easebuzz payment page URL
            - txnid: Transaction ID
    """
    try:
        # Debug log line
        frappe.log_error(f"Initiate payment: {kwargs}", "Easebuzz Payment Initiation Error")
        # Validate required parameters
        required_params = ['amount', 'reference_doctype', 'reference_docname', 'payer_email', 'payer_name']
        
        for param in required_params:
            if not kwargs.get(param):
                return {
                    "success": False,
                    "error": f"Missing required parameter: {param}"
                }
        
        # Set defaults
        kwargs.setdefault('currency', 'INR')
        kwargs.setdefault('payment_gateway', 'Easebuzz')
        
        # Create integration request
        integration_request = create_request_log(kwargs, service_name="Easebuzz")
        kwargs['order_id'] = integration_request.name
        
        # Get Easebuzz settings
        easebuzz_settings = frappe.get_doc("Easebuzz Settings")
        
        # Create payment data
        payment_request_data = easebuzz_settings.create_payment_request_data(
            integration_request.name,
            **kwargs
        )
        
        # Call Easebuzz API to initiate payment
        result = initiate_payment_api(
            payment_request_data['payment_data'],
            payment_request_data['merchant_key'],
            payment_request_data['salt'],
            payment_request_data['environment']
        )
        
        frappe.log_error(f"Initiate payment result: {result}", "Easebuzz Payment Initiation Error")
        if result.get('success'):
            return {
                "success": True,
                "payment_token": integration_request.name,
                "payment_url": result['data'],
                "txnid": payment_request_data['payment_data']['txnid'],
                "merchant_name": payment_request_data.get('merchant_name')
            }
        else:
            return {
                "success": False,
                "error": result.get('message', 'Failed to initiate payment')
            }
        
    except Exception as e:
        frappe.log_error(f"Payment initiation error: {str(e)}\n{frappe.get_traceback()}", "Easebuzz Payment Initiation Error")
        return {
            "success": False,
            "error": str(e)
        }


@frappe.whitelist(allow_guest=True)
def check_payment_status(integration_request_name):
    """
    API endpoint to check the status of a payment.
    
    Args:
        integration_request_name (str): Integration request name/token
        
    Returns:
        dict: Payment status information
    """
    try:
        # Get integration request
        integration_request = frappe.get_doc("Integration Request", integration_request_name)
        
        # Parse data
        data = json.loads(integration_request.data) if integration_request.data else {}
        
        return {
            "success": True,
            "status": integration_request.status,
            "payment_status": data.get("status"),
            "transaction_id": data.get("easepayid"),
            "bank_ref_no": data.get("bank_ref_num"),
            "payment_mode": data.get("mode"),
            "error_message": data.get("error_Message"),
            "reference_doctype": integration_request.reference_doctype,
            "reference_docname": integration_request.reference_docname,
            "amount": data.get("amount"),
            "currency": data.get("currency")
        }
        
    except frappe.DoesNotExistError:
        return {
            "success": False,
            "error": "Payment request not found"
        }
    except Exception as e:
        frappe.log_error(f"Payment status check error: {str(e)}\n{frappe.get_traceback()}", "Easebuzz Payment Status Error")
        return {
            "success": False,
            "error": str(e)
        }


def _merchant_data_from_response(response_data):
    """
    Build merchant_data from Easebuzz callback.
    New format: udf1=reference_doctype, udf2=reference_docname, udf3=token, udf4=user, udf5=merchant_name.
    Legacy: single udf1 with JSON or pipe-separated key=value.
    """
    # New format: one value per UDF
    token = (response_data.get("udf3") or "").strip()
    if token:
        return {
            "reference_doctype": (response_data.get("udf1") or "").strip(),
            "reference_docname": (response_data.get("udf2") or "").strip(),
            "token": token,
            "user": (response_data.get("udf4") or "").strip(),
            "merchant_name": (response_data.get("udf5") or "").strip(),
        }
    # Legacy: parse single udf1 (JSON or pipe key=value)
    udf1_str = response_data.get("udf1", "") or ""
    if not udf1_str.strip():
        return {}
    s = udf1_str.strip()
    if s.startswith("{"):
        try:
            return json.loads(s)
        except Exception:
            pass
    out = {}
    for part in s.split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


@frappe.whitelist(allow_guest=True)
def verify_transaction(return_json=False):
    """
    Handle Easebuzz's return request after payment.
    
    Args:
        return_json (bool): If True, returns JSON response instead of redirect.
                           Used for API mode integration.
    
    Returns:
        For redirect mode: Sets response redirect
        For JSON mode: Returns dict with payment status
    """
    try:
        # Get response data from Easebuzz
        response_data = dict(frappe.request.form)
        merchant_name = frappe.request.args.get('merchant')
        
        if not response_data:
            if return_json or frappe.form_dict.get('return_json'):
                return {
                    "success": False,
                    "status": "Failed",
                    "error": "No response received"
                }
            frappe.local.response["type"] = "redirect"
            frappe.local.response["location"] = get_url("payment-failed")
            return

        # Get Easebuzz settings
        settings = frappe.get_doc("Easebuzz Settings")
        
        # Get merchant configuration
        if merchant_name:
            merchant_doc = frappe.get_doc("Easebuzz Merchant", merchant_name)
            merchant_salt = merchant_doc.get_password(fieldname="salt", raise_exception=False)
        else:
            merchant_doc = settings.get_merchant_for_company()
            merchant_salt = merchant_doc.get_password(fieldname="salt", raise_exception=False) if merchant_doc else settings.get_password(fieldname="salt", raise_exception=False)

        # Verify hash
        if not verify_response_hash(response_data, merchant_salt):
            frappe.log_error("Hash verification failed for Easebuzz response", "Easebuzz Hash Verification Error")

        # Build merchant_data from udf1-udf5 (or legacy single udf1)
        merchant_data = _merchant_data_from_response(response_data)

        try:
            # Set the session user from merchant_data if available
            user = merchant_data.get("user")
            if user and user != "Guest" and frappe.session.user == "Guest":
                frappe.set_user(user)
                frappe.local.login_manager.login_as(user)
                frappe.logger().info(f"Easebuzz: Restored user session for {user}")

        except Exception as e:
            frappe.log_error(f"Error parsing merchant data: {str(e)}")
            if return_json or frappe.form_dict.get('return_json'):
                return {
                    "success": False,
                    "status": "Failed",
                    "error": "Error parsing payment data"
                }
            frappe.local.response["type"] = "redirect"
            frappe.local.response["location"] = get_url("payment-failed")
            return

        # Get the integration request (token is integration request name, or legacy "order_id@name")
        token = merchant_data.get("token")
        integration_request = None

        if token:
            ir_name = token.split('@')[1] if '@' in token else token
            integration_request = frappe.get_doc("Integration Request", ir_name)

        if not integration_request:
            frappe.log_error(f"Integration request not found for token: {token}", "Easebuzz Payment Error")
            if return_json or frappe.form_dict.get('return_json'):
                return {
                    "success": False,
                    "status": "Failed",
                    "error": "Payment request not found"
                }
            frappe.local.response["type"] = "redirect"
            frappe.local.response["location"] = get_url("payment-failed")
            return

        # Update the data with the response from Easebuzz
        data = json.loads(integration_request.data)
        data["user"] = user or frappe.session.user
        
        if merchant_data.get("merchant_name"):
            data["custom_merchant_name"] = merchant_data.get("merchant_name")

        data.update({
            "status": response_data.get("status"),
            "txnid": response_data.get("txnid"),
            "easepayid": response_data.get("easepayid"),
            "bank_ref_num": response_data.get("bank_ref_num"),
            "mode": response_data.get("mode"),
            "error_Message": response_data.get("error_Message"),
            "easebuzz_response": response_data
        })

        # Create a new controller instance
        controller = frappe.get_doc("Easebuzz Settings")
        controller.data = frappe._dict(data)
        controller.integration_request = integration_request

        # Update the integration request with the updated data
        integration_request.data = json.dumps(data)
        integration_request.save(ignore_permissions=True)
        frappe.db.commit()

        # Set status based on response status
        if response_data.get("status") == "success":
            controller.flags.status_changed_to = "Completed"

        # Call authorize_payment to complete the flow
        result = controller.authorize_payment()

        # Check if JSON response is requested
        if return_json or frappe.form_dict.get('return_json'):
            return {
                "success": True,
                "status": result.get("status"),
                "transaction_id": data.get("easepayid"),
                "payment_status": data.get("status"),
                "reference_doctype": data.get("reference_doctype"),
                "reference_docname": data.get("reference_docname"),
                "redirect_to": result.get("redirect_to")
            }

        # Preserve cookies in the redirect
        redirect_location = get_url(result["redirect_to"])

        # Make sure to authenticate user via session cookie
        if user and user != "Guest":
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
        frappe.log_error(f"{str(e)}\n{frappe.get_traceback()}", "Easebuzz Payment Verification Error")
        if return_json or frappe.form_dict.get('return_json'):
            return {
                "success": False,
                "status": "Failed",
                "error": str(e)
            }
        frappe.local.response["type"] = "redirect"
        frappe.local.response["location"] = get_url("payment-failed")


@frappe.whitelist(allow_guest=True)
def webhook_callback():
    """
    Webhook endpoint for Easebuzz payment callbacks.
    Returns JSON response instead of redirect.
    Used by frontend/mobile apps to handle payment completion.
    """
    try:
        # Get response data from Easebuzz
        response_data = dict(frappe.request.form)
        merchant_name = frappe.request.args.get('merchant')
        
        if not response_data:
            return {
                "success": False,
                "status": "Failed",
                "error": "No response received"
            }
        
        # Get Easebuzz settings
        settings = frappe.get_doc("Easebuzz Settings")
        
        # Get merchant configuration
        if merchant_name:
            merchant_doc = frappe.get_doc("Easebuzz Merchant", merchant_name)
            merchant_salt = merchant_doc.get_password(fieldname="salt", raise_exception=False)
        else:
            merchant_doc = settings.get_merchant_for_company()
            merchant_salt = merchant_doc.get_password(fieldname="salt", raise_exception=False) if merchant_doc else None
        
        # Verify hash
        if merchant_salt and not verify_response_hash(response_data, merchant_salt):
            frappe.log_error("Hash verification failed", "Easebuzz Webhook Error")
        
        # Build merchant_data from udf1-udf5 (or legacy single udf1)
        merchant_data = _merchant_data_from_response(response_data)

        # Get the integration request (token is integration request name, or legacy "order_id@name")
        token = merchant_data.get("token")
        if token:
            ir_name = token.split('@')[1] if '@' in token else token
            integration_request = frappe.get_doc("Integration Request", ir_name)
        else:
            return {
                "success": False,
                "status": "Failed",
                "error": "Invalid token"
            }
        
        # Update the data
        data = json.loads(integration_request.data)
        data.update({
            "status": response_data.get("status"),
            "txnid": response_data.get("txnid"),
            "easepayid": response_data.get("easepayid"),
            "bank_ref_num": response_data.get("bank_ref_num"),
            "mode": response_data.get("mode"),
            "error_Message": response_data.get("error_Message"),
            "easebuzz_response": response_data,
            "webhook_source": "webhook_callback"
        })
        
        # Create controller instance
        controller = frappe.get_doc("Easebuzz Settings")
        controller.data = frappe._dict(data)
        controller.integration_request = integration_request
        
        # Update integration request
        integration_request.data = json.dumps(data)
        integration_request.save(ignore_permissions=True)
        
        # Set status
        if response_data.get("status") == "success":
            controller.flags.status_changed_to = "Completed"
        
        # Call authorize_payment
        result = controller.authorize_payment()
        
        return {
            "success": True,
            "status": result.get("status"),
            "transaction_id": data.get("easepayid"),
            "payment_status": data.get("status"),
            "reference_doctype": data.get("reference_doctype"),
            "reference_docname": data.get("reference_docname"),
            "redirect_to": result.get("redirect_to")
        }
        
    except Exception as e:
        frappe.log_error(f"{str(e)}\n{frappe.get_traceback()}", "Easebuzz Webhook Error")
        return {
            "success": False,
            "status": "Failed",
            "error": str(e)
        }
