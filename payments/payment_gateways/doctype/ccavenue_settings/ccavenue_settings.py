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
from urllib.parse import urlencode, quote_plus
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
        """
        if merchant_name:
            try:
                return frappe.get_doc("CCAvenue Merchant", merchant_name)
            except frappe.DoesNotExistError:
                frappe.log_error(f"CCAvenue Merchant {merchant_name} not found, falling back to company/default merchant")
        if company:
            merchant = frappe.db.get_value(
                "CCAvenue Merchant",
                {"company": company},
                ["name"],
                as_dict=False
            )
            if merchant:
                return frappe.get_doc("CCAvenue Merchant", merchant)
        default_merchant_name = frappe.db.get_value(
            "CCAvenue Merchant",
            {"is_default": 1},
            "name"
        )
        if default_merchant_name:
            return frappe.get_doc("CCAvenue Merchant", default_merchant_name)
        from payments.payment_gateways.doctype.ccavenue_merchant.ccavenue_merchant import get_default_merchant
        default_merchant_name = get_default_merchant()
        if default_merchant_name:
            return frappe.get_doc("CCAvenue Merchant", default_merchant_name)
        frappe.throw(
            _("No CCAvenue Merchant configuration found. Please create a merchant configuration.")
        )

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
        if data.get("order_status") == "Success" or data.get("order_status") == "Shipped":
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
        order_id = kwargs.get('order_id') or integration_request_name
        token = order_id + "@" + integration_request_name
        merchant_name = kwargs.get('custom_merchant_name')
        customer_name = kwargs.get('payer_name', '').strip()
        customer_dict = {}
        try:
            if customer_name and frappe.db.exists("Customer", customer_name):
                customer_dict = frappe.get_doc("Customer", customer_name, check_permission=False).as_dict()
        except Exception:
            pass
        billing_name = customer_dict.get("customer_name") or customer_name or "Customer"
        charge_list = frappe.get_all("Payment Charge",filters={'disabled':0},fields=['*'])
        outstanding_amount = kwargs.get('amount')
        total_charges = 0
        for charge in charge_list:
            charge_amount = (outstanding_amount * charge.charge_percent / 100)
            charge_amount = math.ceil(charge_amount * 100) / 100
            total_charges = total_charges + charge_amount
        final_amount = outstanding_amount + total_charges

        if merchant_name:
            merchant_doc = frappe.get_doc("CCAvenue Merchant", merchant_name)
            merchant_dict = merchant_doc.as_dict()
            merchant_data = {
                'merchant_id': merchant_dict.get('merchant_id'),
                'order_id': token,
                'currency': kwargs.get('currency' , 'INR'),
                'amount': str(final_amount),
                'redirect_url': get_url(
                    f"/api/method/payments.payment_gateways.doctype.ccavenue_settings.ccavenue_settings.verify_transaction?merchant={merchant_name}"),
                'cancel_url': get_url(
                    f"/api/method/payments.payment_gateways.doctype.ccavenue_settings.ccavenue_settings.verify_transaction?merchant={merchant_name}"),
                'language': 'EN',
                'integration_type': 'iframe_normal',
                "merchant_param1": json.dumps({
                    "reference_doctype": kwargs.get("reference_doctype"),
                    "reference_docname": kwargs.get("reference_docname"),
                    "token": token,
                    "user": frappe.session.user  # Add the current user
                }),
                'customer_identifier': kwargs.get('payer_email', ''),
                'billing_name': billing_name,
                'billing_address':f'{customer_dict.get("custom_house_no__floor", "")} + {customer_dict.get("custom_building__block_number", "")} + {customer_dict.get("custom_landmark__area_name", "")}',
                'billing_city':customer_dict.get('custom_city', "NA"),
                'billing_zip':kwargs.get('custom_pincode','NA'),
                'billing_state':kwargs.get('custom_pincode','NA'),
                'billing_email':frappe.session.user,
                'billing_country':'india'
            }

            merchant_data_string = '&'.join([
                f"{key}={value}" for key, value in merchant_data.items()
            ])
            merchant_data_string = merchant_data_string + '&'

            # Encrypt the data using CCAvenue's encryption method
            encrypted_data = encrypt(merchant_data_string,
                                     merchant_doc.get_password(fieldname="encryption_key", raise_exception=False))

            return {
                "encRequest": encrypted_data,
                "access_code": merchant_dict.get('access_code'),
                "merchant_id": merchant_dict.get('merchant_id'),
                "non_encrypted_data": merchant_data_string
            }
        merchant_data = {
            'merchant_id': self.merchant_id,
            'order_id': token,
            'currency': kwargs.get('currency', 'INR'),
            'amount': str(final_amount),
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
            'customer_identifier': kwargs.get('payer_email', ''),
            'billing_name': billing_name,
            'billing_address':f'{customer_dict.get("custom_house_no__floor", "")} + {customer_dict.get("custom_building__block_number", "")} + {customer_dict.get("custom_landmark__area_name", "")}',
            'billing_city':customer_dict.get('custom_city', "NA"),
            'billing_zip':kwargs.get('custom_pincode','NA'),
            'billing_state':kwargs.get('custom_pincode','NA'),
            'billing_email':frappe.session.user,
            'billing_country':'india'
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
    Returns the same shape as Easebuzz so the frontend can use one flow for both gateways.
    payment_url is the checkout page URL; opening it redirects to CCAvenue.
    """
    try:
        
        required_params = ['amount', 'reference_doctype', 'reference_docname', 'payer_email', 'payer_name']
        for param in required_params:
            if not kwargs.get(param):
                return {
                    "success": False,
                    "error": f"Missing required parameter: {param}"
                }
        kwargs.setdefault('currency', 'INR')
        kwargs.setdefault('payment_gateway', 'CCAvenue')
        integration_request = create_request_log(kwargs, service_name="CCAvenue")
        kwargs['order_id'] = integration_request.name
        # same_window=1 avoids CCAvenue iframe blocking when frontend opens URL in new tab
        payment_url = get_url(f"/ccavenue_checkout?token={integration_request.name}&same_window=1")
        merchant_name = kwargs.get('custom_merchant_name') or None
        if not merchant_name and kwargs.get('company'):
            try:
                settings = frappe.get_doc("CCAvenue Settings")
                merchant_doc = settings.get_merchant_for_company(company=kwargs.get('company'))
                if merchant_doc:
                    merchant_name = merchant_doc.name
            except Exception:
                pass
        # return {
        #     "success": True,
        #     "payment_token": integration_request.name,
        #     "payment_url": payment_url,
        #     "txnid": integration_request.name,
        #     "merchant_name": merchant_name
        # }
        
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
        frappe.log_error(f"CCAvenue initiate_payment error: {str(e)}\n{frappe.get_traceback()}", "CCAvenue Payment Initiation Error")
        return {
            "success": False,
            "error": str(e)
        }


@frappe.whitelist(allow_guest=True)
def check_payment_status(integration_request_name):
    """
    API endpoint to check the status of a CCAvenue payment.
    Same shape as Easebuzz so the frontend can use one flow for both gateways.
    """
    try:
        integration_request = frappe.get_doc("Integration Request", integration_request_name)
        data = json.loads(integration_request.data) if integration_request.data else {}
        order_status = data.get("order_status") or ""
        # Explicit "pending" when still Queued so frontend does not treat as "failed"
        if order_status in ("Success", "Shipped"):
            payment_status = "success"
        elif order_status and str(order_status).lower() in ("failed", "aborted", "invalid", "failure"):
            payment_status = "failure"
        elif integration_request.status == "Failed":
            payment_status = "failure"
        elif not order_status and integration_request.status == "Queued":
            payment_status = "pending"
        else:
            payment_status = order_status.lower() if order_status else "pending"
        return {
            "success": True,
            "status": integration_request.status,
            "payment_status": payment_status,
            "transaction_id": data.get("tracking_id"),
            "bank_ref_no": data.get("bank_ref_no"),
            "payment_mode": data.get("payment_mode"),
            "error_message": data.get("failure_message"),
            "reference_doctype": integration_request.reference_doctype,
            "reference_docname": integration_request.reference_docname,
            "amount": data.get("amount"),
            "currency": data.get("currency"),
        }
    except frappe.DoesNotExistError:
        return {
            "success": False,
            "error": "Payment request not found"
        }
    except Exception as e:
        frappe.log_error(f"CCAvenue check_payment_status error: {str(e)}\n{frappe.get_traceback()}", "CCAvenue Payment Status Error")
        return {
            "success": False,
            "error": str(e)
        }


@frappe.whitelist(allow_guest=True)
def verify_transaction():
    """Handle CCAvenue's return request after payment"""
    try:
        # 1. Read encrypted response and merchant name (if any)
        encResp = frappe.request.form.get("encResp")
        merchant_name = None
        if frappe.request.query_string.decode("utf-8") != '':
            merchant_name_encoded = frappe.request.query_string.decode('utf-8').split('=')[1]
            merchant_name = urllib.parse.unquote(merchant_name_encoded)

        if not encResp:
            frappe.local.response["type"] = "redirect"
            frappe.local.response["location"] = get_url("payment-failed")
            return

        # 2. Decrypt response
        settings = frappe.get_doc("CCAvenue Settings")
        if merchant_name:
            merchant_doc = frappe.get_doc("CCAvenue Merchant", merchant_name)
            decrypted_data = decrypt(encResp, merchant_doc.get_password(fieldname="encryption_key", raise_exception=False))
        else:
            decrypted_data = decrypt(encResp, settings.get_password(fieldname="encryption_key", raise_exception=False))

        # 3. Parse decrypted response
        response_data = {}
        for param in decrypted_data.split('&'):
            if param and '=' in param:
                key, value = param.split('=', 1)
                response_data[key] = value

        merchant_param_str = response_data.get("merchant_param1", "")
        merchant_data = {}

        try:
            if merchant_param_str:
                parts = merchant_param_str.split(", ")
                for part in parts:
                    if ":" in part:
                        k, v = part.split(":", 1)
                        merchant_data[k.strip()] = v.strip()
                    elif " " in part:
                        k, v = part.split(" ", 1)
                        merchant_data[k.strip()] = v.strip()

            # Restore user session
            user = merchant_data.get("user")
            if user and user != "Guest" and frappe.session.user == "Guest":
                frappe.set_user(user)
                frappe.local.login_manager.login_as(user)
                frappe.logger().info(f"CCAvenue: Restored user session for {user}")
        except Exception as e:
            frappe.log_error(f"Error parsing merchant data: {str(e)}")
            frappe.local.response["type"] = "redirect"
            frappe.local.response["location"] = get_url("payment-failed")
            return

        frappe.logger().info(f"CCAvenue callback - Current user: {frappe.session.user}")

        # 4. Check integration request
        order_id = merchant_data.get("token")
        if not order_id:
            frappe.local.response["type"] = "redirect"
            frappe.local.response["location"] = get_url("payment-failed")
            return

        try:
            integration_request = frappe.get_doc("Integration Request", order_id.split('@')[1])
        except frappe.DoesNotExistError:
            frappe.log_error(f"Integration request not found for token: {order_id}", "CCAvenue Payment Error")
            frappe.local.response["type"] = "redirect"
            frappe.local.response["location"] = get_url("payment-failed")
            return

        # 5. Check if already paid
        payment_request_name = merchant_data.get("reference_docname")
        if payment_request_name:
            try:
                pr = frappe.get_doc("Payment Request", payment_request_name)
                if pr.status == "Paid":
                    frappe.logger().info(f"Payment Request {payment_request_name} already paid. Skipping controller logic.")
                    redirect_url = f"payment-success?doctype=Payment Request&docname={payment_request_name}"
                    frappe.local.response["type"] = "redirect"
                    frappe.local.response["location"] = get_url(redirect_url)

                    if user and user != "Guest":
                        frappe.local.cookie_manager.set_cookie("system_user", user)
                        frappe.local.cookie_manager.set_cookie("full_name", frappe.db.get_value("User", user, "full_name") or "")
                        frappe.local.cookie_manager.set_cookie("user_id", user)
                        frappe.local.cookie_manager.set_cookie("sid", frappe.session.sid)
                        frappe.local.response["set_cookie"] = frappe.local.cookie_manager.cookies

                    return
            except frappe.DoesNotExistError:
                frappe.logger().warning(f"Could not find Payment Request: {payment_request_name}")

        # 6. Continue normal controller flow
        data = json.loads(integration_request.data)
        data["user"] = user or frappe.session.user
        data.update({
            "order_status": response_data.get("order_status"),
            "tracking_id": response_data.get("tracking_id"),
            "bank_ref_no": response_data.get("bank_ref_no"),
            "payment_mode": response_data.get("payment_mode"),
            "failure_message": response_data.get("failure_message"),
            "ccavenue_response": response_data
        })

        integration_request.data = json.dumps(data)
        integration_request.save(ignore_permissions=True)

        controller = frappe.get_doc("CCAvenue Settings")
        controller.data = frappe._dict(data)
        controller.integration_request = integration_request

        if response_data.get("order_status") == "Success":
            controller.flags.status_changed_to = "Completed"

        result = controller.authorize_payment()
        redirect_location = get_url(result["redirect_to"])

        if user and user != "Guest":
            frappe.local.cookie_manager.set_cookie("system_user", user)
            frappe.local.cookie_manager.set_cookie("full_name", frappe.db.get_value("User", user, "full_name") or "")
            frappe.local.cookie_manager.set_cookie("user_id", user)
            frappe.local.cookie_manager.set_cookie("sid", frappe.session.sid)

        frappe.local.response["set_cookie"] = frappe.local.cookie_manager.cookies
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

@frappe.whitelist()
def get_working_key():
    """Get CCAvenue working key"""
    settings = frappe.get_doc("CCAvenue Settings")
    working_key = settings.get_password(fieldname="encryption_key", raise_exception=False)
    return working_key

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
