# License: MIT. See LICENSE

# DEPRECATED: This web-based checkout is deprecated in favor of API-based integration.
# For new implementations, use the API endpoints:
# - initiate_payment: To create payment requests from frontend/mobile
# - webhook_callback: To handle payment callbacks
# - check_payment_status: To verify payment status
# See CCAVENUE_API_INTEGRATION.md for details.

import json

import frappe
from frappe import _

from payments.utils.utils import validate_integration_request

no_cache = 1

def get_context(context):
    context.no_cache = 1

    # Validate the integration request
    try:
        token = frappe.form_dict.get("token")
        if not token:
            raise ValueError("Missing token")
        validate_integration_request(token)
        # Load Integration Request without permission check – token is the secret (Guest can open checkout URL)
        doc = frappe.get_doc("Integration Request", token, check_permission=False)
        payment_details = json.loads(doc.data)
        # Generate CCAvenue payment form data (Settings readable for checkout)
        ccavenue_settings = frappe.get_doc("CCAvenue Settings", None, check_permission=False)
        context.payment_data = ccavenue_settings.create_encrypted_request_data(doc.name, **payment_details)
        
        # Set API URL based on environment
        context.api_url = ccavenue_settings.get_api_url()
        
        # Same-window redirect avoids CCAvenue iframe blocking (X-Frame-Options)
        context.same_window = frappe.form_dict.get("same_window") in (1, "1", "true", "yes")
        
        # Add other context variables
        context.token = token
        context.header_img = ccavenue_settings.header_img
        
    except Exception as e:
        frappe.log_error(
            f"token={frappe.form_dict.get('token')}\n{frappe.get_traceback()}",
            "CCAvenue Checkout Error",
        )
        frappe.redirect_to_message(
            _("Invalid Token"),
            _("Seems token you are using is invalid!"),
            http_status_code=400,
            indicator_color="red",
        )
        frappe.local.flags.redirect_location = frappe.local.response.location
        raise frappe.Redirect