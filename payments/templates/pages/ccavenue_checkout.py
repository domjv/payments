# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE
import json

import frappe
from frappe import _

from payments.utils.utils import validate_integration_request

no_cache = 1

def get_context(context):
    """Build context for the checkout page"""
    context.no_cache = 1

    # Validate the integration request
    try:
        validate_integration_request(frappe.form_dict["token"])
        
        # Get the integration request doc
        integration_request = frappe.get_doc("Integration Request", frappe.form_dict["token"])
        payment_details = json.loads(integration_request.data)
        
        # Set payment details in context
        context.amount = payment_details.get("amount")
        context.title = payment_details.get("title")
        context.description = payment_details.get("description")
        context.reference_doctype = payment_details.get("reference_doctype")
        context.reference_docname = payment_details.get("reference_docname")
        context.payer_name = payment_details.get("payer_name")
        context.payer_email = payment_details.get("payer_email")
        context.order_id = payment_details.get("order_id")
        context.currency = payment_details.get("currency")
        context.token = frappe.form_dict["token"]
        
        # Get CCAvenue settings
        ccavenue_settings = frappe.get_doc("CCAvenue Settings")
        
        # Get encrypted payment data
        context.payment_data = ccavenue_settings.create_encrypted_request_data(**payment_details)
        
        # Set API URL based on environment
        if ccavenue_settings.environment == "Production":
            context.api_url = "https://secure.ccavenue.com/transaction/transaction.do"
        else:
            context.api_url = "https://test.ccavenue.com/transaction/transaction.do"
        
        # Add header image if available
        context.header_img = ccavenue_settings.header_img
        
    except Exception:
        frappe.log_error(frappe.get_traceback(), "CCAvenue Checkout Error")
        frappe.redirect_to_message(
            _("Invalid Token"),
            _("Seems token you are using is invalid!"),
            http_status_code=400,
            indicator_color="red",
        )
        frappe.local.flags.redirect_location = frappe.local.response.location
        raise frappe.Redirect