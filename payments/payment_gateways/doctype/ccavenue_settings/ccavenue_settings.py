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
import urllib
from urllib.parse import urlencode, quote_plus, urlparse, parse_qs, urlunparse
import math

import frappe
from frappe import _
from frappe.integrations.utils import create_request_log
from frappe.model.document import Document
from frappe.utils import call_hook_method
from frappe.utils.data import get_url

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
            Document: CCAvenue Merchant document or None
        """
        # If explicit merchant name provided, use it
        if merchant_name:
            try:
                return frappe.get_doc("CCAvenue Merchant", merchant_name)
            except frappe.DoesNotExistError:
                frappe.log_error(f"Merchant {merchant_name} not found, falling back to company/default merchant")
        
        # Try to find company-specific merchant
        if company:
            merchant = frappe.db.get_value(
                "CCAvenue Merchant",
                {"company": company},
                ["name"],
                as_dict=False
            )
            if merchant:
                return frappe.get_doc("CCAvenue Merchant", merchant)
        
        # Fall back to default merchant
        default_merchant_name = frappe.db.get_value(
            "CCAvenue Merchant",
            {"is_default": 1},
            "name"
        )
        
        if default_merchant_name:
            return frappe.get_doc("CCAvenue Merchant", default_merchant_name)
        
        # If no default exists, try to create or get one
        from payments.payment_gateways.doctype.ccavenue_merchant.ccavenue_merchant import get_default_merchant
        default_merchant_name = get_default_merchant()
        
        if default_merchant_name:
            return frappe.get_doc("CCAvenue Merchant", default_merchant_name)
        
        frappe.throw(_("No CCAvenue Merchant configuration found. Please create a merchant configuration."))


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

        # Priority: 1. CCAvenue Settings redirect_to, 2. Custom redirect from doctype
        redirect_to = None
        
        # Check if redirect_to is configured in CCAvenue Settings
        if hasattr(self, 'redirect_to') and self.redirect_to:
            redirect_to = self.redirect_to

        redirect_message = data.get("redirect_message") or None

        if self.flags.status_changed_to == "Completed":
            if self.data.reference_doctype and self.data.reference_docname:
                custom_redirect_to = None
                try:
                    # Get the document
                    doc = frappe.get_doc(self.data.reference_doctype, self.data.reference_docname)
                    
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
                        "CCAvenue Payment Authorization Error"
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

    def create_encrypted_request_data(self, integration_request_name, **kwargs):
        """Create encrypted data for CCAvenue request"""
        # Format the data as required by CCAvenue
        order_id = kwargs.get('order_id', integration_request_name)
        token = order_id + "@" + integration_request_name
        
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
        
        log_message = f"CCAvenue Charges - Original: {outstanding_amount}, "
        for charge in charge_list:
            charge_amount = (outstanding_amount * charge.charge_percent / 100)
            charge_amount = math.ceil(charge_amount * 100) / 100
            total_charges = total_charges + charge_amount
            log_message += f"Charge: {charge.charge_percent}%={charge_amount}, "
        log_message += f"Total: {total_charges}, Final: {outstanding_amount + total_charges}"
        frappe.log_error(log_message, "CCAvenue Payment Charges")
        
        final_amount = outstanding_amount + total_charges
        
        # Get merchant environment for API URL
        merchant_environment = merchant_doc.get('enviroment', 'Sandbox')
        
        # Build merchant data
        merchant_data = {
            'merchant_id': merchant_doc.get('merchant_id'),
            'order_id': token,
            'currency': kwargs.get('currency', 'INR'),
            'amount': str(final_amount),
            'redirect_url': get_url(
                f"/api/method/payments.payment_gateways.doctype.ccavenue_settings.ccavenue_settings.verify_transaction?merchant={merchant_doc.name}"),
            'cancel_url': get_url(
                f"/api/method/payments.payment_gateways.doctype.ccavenue_settings.ccavenue_settings.verify_transaction?merchant={merchant_doc.name}"),
            'language': 'EN',
            'integration_type': 'iframe_normal',
            "merchant_param1": json.dumps({
                "reference_doctype": kwargs.get("reference_doctype"),
                "reference_docname": kwargs.get("reference_docname"),
                "token": token,
                "user": frappe.session.user,
                "merchant_name": merchant_doc.name
            }),
            'customer_identifier': kwargs.get('payer_email', ''),
            'billing_name': billing_name,
            'billing_address': f'{customer_dict.get("custom_house_no__floor", "")} {customer_dict.get("custom_building__block_number", "")} {customer_dict.get("custom_landmark__area_name", "")}'.strip() or "NA",
            'billing_city': customer_dict.get('custom_city', "NA"),
            'billing_zip': kwargs.get('custom_pincode', 'NA'),
            'billing_state': kwargs.get('custom_state', customer_dict.get('custom_state', 'NA')),
            'billing_email': frappe.session.user,
            'billing_country': 'India'
        }
        
        # Create the merchant data string exactly as CCAvenue expects
        merchant_data_string = '&'.join([
            f"{key}={value}" for key, value in merchant_data.items()
        ])
        merchant_data_string = merchant_data_string + '&'
        
        # Encrypt the data using CCAvenue's encryption method
        encrypted_data = encrypt(
            merchant_data_string,
            merchant_doc.get_password(fieldname="encryption_key", raise_exception=False)
        )
        
        return {
            "encRequest": encrypted_data,
            "access_code": merchant_doc.get('access_code'),
            "merchant_id": merchant_doc.get('merchant_id'),
            "merchant_name": merchant_doc.name,
            "environment": merchant_environment,
            "non_encrypted_data": merchant_data_string
        }

    def get_api_url(self, environment=None):
        """Get the CCAvenue API URL based on environment"""
        if not environment:
            environment = self.environment
        
        if environment == "Production":
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
def initiate_payment(**kwargs):
    """
    API endpoint to initiate a CCAvenue payment from frontend/mobile app.
    
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
        
    Returns:
        dict: Payment initiation data including:
            - payment_token: Integration request name
            - encrypted_data: Encrypted payment data
            - access_code: Merchant access code
            - merchant_id: Merchant ID
            - api_url: CCAvenue API URL
            - order_id: Order ID
    """
    try:
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
        kwargs.setdefault('payment_gateway', 'CCAvenue')
        
        # Create integration request
        integration_request = create_request_log(kwargs, service_name="CCAvenue")
        kwargs['order_id'] = integration_request.name
        
        # Get CCAvenue settings
        ccavenue_settings = frappe.get_doc("CCAvenue Settings")
        
        # Create encrypted payment data
        payment_data = ccavenue_settings.create_encrypted_request_data(
            integration_request.name,
            **kwargs
        )
        
        # Get API URL
        api_url = ccavenue_settings.get_api_url(payment_data.get('environment'))
        
        return {
            "success": True,
            "payment_token": integration_request.name,
            "encrypted_data": payment_data['encRequest'],
            "access_code": payment_data['access_code'],
            "merchant_id": payment_data['merchant_id'],
            "merchant_name": payment_data.get('merchant_name'),
            "api_url": api_url,
            "order_id": integration_request.name,
            "iframe_url": f"{api_url}&merchant_id={payment_data['merchant_id']}&encRequest={payment_data['encRequest']}&access_code={payment_data['access_code']}"
        }
        
    except Exception as e:
        frappe.log_error(f"Payment initiation error: {str(e)}\n{frappe.get_traceback()}", "CCAvenue Payment Initiation Error")
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
        dict: Payment status information including:
            - status: Payment status (Completed, Failed, Pending, etc.)
            - order_status: CCAvenue order status
            - tracking_id: CCAvenue tracking ID
            - payment_mode: Payment mode used
            - reference_doctype: Reference document type
            - reference_docname: Reference document name
    """
    try:
        # Get integration request
        integration_request = frappe.get_doc("Integration Request", integration_request_name)
        
        # Parse data
        data = json.loads(integration_request.data) if integration_request.data else {}
        
        return {
            "success": True,
            "status": integration_request.status,
            "order_status": data.get("order_status"),
            "tracking_id": data.get("tracking_id"),
            "bank_ref_no": data.get("bank_ref_no"),
            "payment_mode": data.get("payment_mode"),
            "failure_message": data.get("failure_message"),
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
        frappe.log_error(f"Payment status check error: {str(e)}\n{frappe.get_traceback()}", "CCAvenue Payment Status Error")
        return {
            "success": False,
            "error": str(e)
        }


@frappe.whitelist(allow_guest=True)
def webhook_callback():
    """
    Webhook endpoint for CCAvenue payment callbacks.
    Returns JSON response instead of redirect.
    Used by frontend/mobile apps to handle payment completion.
    """
    try:
        # Get the encrypted response from CCAvenue
        encResp = frappe.request.form.get("encResp")
        merchant_name = None
        
        if frappe.request.query_string.decode("utf-8") != '':
            merchant_name_encoded = frappe.request.query_string.decode('utf-8').split('=')[1]
            merchant_name = urllib.parse.unquote(merchant_name_encoded)
        
        if not encResp:
            return {
                "success": False,
                "status": "Failed",
                "error": "No encrypted response received"
            }
        
        # Get CCAvenue settings
        settings = frappe.get_doc("CCAvenue Settings")
        
        # Decrypt the response
        if merchant_name:
            merchant_doc = frappe.get_doc("CCAvenue Merchant", merchant_name)
            decrypted_data = decrypt(encResp, merchant_doc.get_password(fieldname="encryption_key", raise_exception=False))
        else:
            # Try to get default merchant
            merchant_doc = settings.get_merchant_for_company()
            if merchant_doc:
                decrypted_data = decrypt(encResp, merchant_doc.get_password(fieldname="encryption_key", raise_exception=False))
            else:
                decrypted_data = decrypt(encResp, settings.get_password(fieldname="encryption_key", raise_exception=False))
        
        # Parse the decrypted data
        response_data = {}
        for param in decrypted_data.split('&'):
            if param and '=' in param:
                key, value = param.split('=', 1)
                response_data[key] = value
        
        # Extract merchant_param1 and parse the JSON
        merchant_param_str = response_data.get("merchant_param1", "")
        merchant_data = {}
        
        try:
            if merchant_param_str:
                merchant_data = json.loads(merchant_param_str)
        except:
            # Fallback parsing
            if merchant_param_str:
                parts = merchant_param_str.split(", ")
                for part in parts:
                    if ":" in part:
                        k, v = part.split(":", 1)
                        merchant_data[k.strip()] = v.strip()
        
        # Get the integration request
        order_id = merchant_data.get("token")
        if order_id:
            integration_request = frappe.get_doc("Integration Request", order_id.split('@')[1])
        else:
            return {
                "success": False,
                "status": "Failed",
                "error": "Invalid order ID"
            }
        
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
        
        # Create controller instance
        controller = frappe.get_doc("CCAvenue Settings")
        controller.data = frappe._dict(data)
        controller.integration_request = integration_request
        
        # Update integration request
        integration_request.data = json.dumps(data)
        integration_request.save(ignore_permissions=True)
        
        # Set status based on order_status
        if response_data.get("order_status") == "Success":
            controller.flags.status_changed_to = "Completed"
        
        # Call authorize_payment
        result = controller.authorize_payment()
        
        return {
            "success": True,
            "status": result.get("status"),
            "tracking_id": data.get("tracking_id"),
            "order_status": data.get("order_status"),
            "reference_doctype": data.get("reference_doctype"),
            "reference_docname": data.get("reference_docname"),
            "redirect_to": result.get("redirect_to")
        }
        
    except Exception as e:
        frappe.log_error(f"{str(e)}\n{frappe.get_traceback()}", "CCAvenue Webhook Error")
        return {
            "success": False,
            "status": "Failed",
            "error": str(e)
        }


@frappe.whitelist(allow_guest=True)
def verify_transaction(return_json=False):
    """
    Handle CCAvenue's return request after payment.
    
    Args:
        return_json (bool): If True, returns JSON response instead of redirect.
                           Used for API mode integration.
    
    Returns:
        For redirect mode: Sets response redirect
        For JSON mode: Returns dict with payment status
    """
    try:
        # Get the encrypted response from CCAvenue
        encResp = frappe.request.form.get("encResp")
        merchant_name = None
        if frappe.request.query_string.decode("utf-8") != '':
            merchant_name_encoded = frappe.request.query_string.decode('utf-8').split('=')[1]
            merchant_name =  urllib.parse.unquote(merchant_name_encoded)
        if not encResp:
            if return_json or frappe.form_dict.get('return_json'):
                return {
                    "success": False,
                    "status": "Failed",
                    "error": "No encrypted response received"
                }
            frappe.local.response["type"] = "redirect"
            frappe.local.response["location"] = get_url("payment-failed")
            return

        # Get CCAvenue settings
        settings = frappe.get_doc("CCAvenue Settings")

        # Decrypt the response
        if merchant_name:
            merchat_doc = frappe.get_doc("CCAvenue Merchant", merchant_name)
            decrypted_data = decrypt(encResp, merchat_doc.get_password(fieldname="encryption_key", raise_exception=False))
        else:
            # Try to get default merchant for decryption
            try:
                default_merchant = settings.get_merchant_for_company()
                if default_merchant:
                    decrypted_data = decrypt(encResp, default_merchant.get_password(fieldname="encryption_key", raise_exception=False))
                else:
                    decrypted_data = decrypt(encResp, settings.get_password(fieldname="encryption_key", raise_exception=False))
            except:
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
            # Properly parse the JSON data (CCAvenue returns it as plain string)
            if merchant_param_str:
                # First try JSON parse
                try:
                    merchant_data = json.loads(merchant_param_str)
                except:
                    # Fallback to string parsing: "key value, key value"
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
            if return_json or frappe.form_dict.get('return_json'):
                return {
                    "success": False,
                    "status": "Failed",
                    "error": "Error parsing payment data"
                }
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
            if return_json or frappe.form_dict.get('return_json'):
                return {
                    "success": False,
                    "status": "Failed",
                    "error": "Payment request not found"
                }
            frappe.local.response["type"] = "redirect"
            frappe.local.response["location"] = get_url("payment-failed")
            return

        # Update the data with the response from CCAvenue
        data = json.loads(integration_request.data)

        # Save the user in the integration request data for future reference
        data["user"] = user or frappe.session.user
        
        # Add parsed merchant data to integration request for on_payment_authorized
        if merchant_data.get("merchant_name"):
            data["custom_merchant_name"] = merchant_data.get("merchant_name")

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
        
        # Use ignore_permissions=True to bypass permission checks
        integration_request.save(ignore_permissions=True)
        frappe.db.commit()  # Commit to ensure data is available for on_payment_authorized

        # Set status based on order_status
        if response_data.get("order_status") == "Success":
            controller.flags.status_changed_to = "Completed"

        # Call authorize_payment to complete the flow
        result = controller.authorize_payment()

        # Check if JSON response is requested
        if return_json or frappe.form_dict.get('return_json'):
            return {
                "success": True,
                "status": result.get("status"),
                "tracking_id": data.get("tracking_id"),
                "order_status": data.get("order_status"),
                "reference_doctype": data.get("reference_doctype"),
                "reference_docname": data.get("reference_docname"),
                "redirect_to": result.get("redirect_to")
            }

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
        if return_json or frappe.form_dict.get('return_json'):
            return {
                "success": False,
                "status": "Failed",
                "error": str(e)
            }
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
