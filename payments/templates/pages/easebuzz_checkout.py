# Copyright (c) 2025, Frappe Technologies and contributors
# License: MIT. See LICENSE

import json

import frappe
from frappe import _

from payments.utils.utils import validate_integration_request
from payments.payment_gateways.doctype.easebuzz_settings.easebuzz_utils import initiate_payment_api

no_cache = 1

def get_context(context):
    context.no_cache = 1

    # Validate the integration request
    try:
        validate_integration_request(frappe.form_dict["token"])
        
        # Get the integration request doc
        doc = frappe.get_doc("Integration Request", frappe.form_dict["token"])
        payment_details = json.loads(doc.data)
        
        # Generate Easebuzz payment form data
        easebuzz_settings = frappe.get_doc("Easebuzz Settings")
        payment_request_data = easebuzz_settings.create_payment_request_data(doc.name, **payment_details)
        
        # Call Easebuzz API to get payment URL
        result = initiate_payment_api(
            payment_request_data['payment_data'],
            payment_request_data['merchant_key'],
            payment_request_data['salt'],
            payment_request_data['environment']
        )
        
        if result.get('success'):
            context.payment_url = result['data']
        else:
            frappe.throw(_("Failed to initiate payment: {0}").format(result.get('message')))
        
        # Add other context variables
        context.token = frappe.form_dict["token"]
        context.header_img = easebuzz_settings.header_img
        
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Easebuzz Checkout Error")
        frappe.redirect_to_message(
            _("Invalid Token"),
            _("Seems token you are using is invalid!"),
            http_status_code=400,
            indicator_color="red",
        )
        frappe.local.flags.redirect_location = frappe.local.response.location
        raise frappe.Redirect
