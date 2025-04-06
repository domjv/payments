# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE
import json

import frappe
from frappe import _

from payments.utils.utils import validate_integration_request

no_cache = 1

expected_keys = (
    "amount",
    "title",
    "description",
    "reference_doctype",
    "reference_docname",
    "payer_name",
    "payer_email",
    "order_id",
    "currency",
)


def get_context(context):
    context.no_cache = 1

    # Validate the integration request
    try:
        validate_integration_request(frappe.form_dict["token"])
        
        # Get the integration request doc
        doc = frappe.get_doc("Integration Request", frappe.form_dict["token"])
        payment_details = json.loads(doc.data)
        
        # Ensure all expected keys are in the form_dict
        for key in expected_keys:
            context[key] = payment_details.get(key)
            
        # Generate CCAvenue payment form data
        ccavenue_settings = frappe.get_doc("CCAvenue Settings")
        context.payment_data = ccavenue_settings.create_encrypted_request_data(**payment_details)
        
        # Set API URL based on environment
        context.api_url = ccavenue_settings.get_api_url()
        
        # Add other context variables
        context.token = frappe.form_dict["token"]
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