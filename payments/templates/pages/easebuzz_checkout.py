# License: MIT. See LICENSE

"""
Easebuzz checkout page: validates token, builds payment data, calls Easebuzz API
to get payment URL, then redirects or shows iframe (same flow as CCAvenue).
"""

import json

import frappe
from frappe import _

from payments.utils.utils import validate_integration_request

no_cache = 1


def get_context(context):
	context.no_cache = 1

	try:
		token = frappe.form_dict.get("token")
		if not token:
			raise ValueError("Missing token")
		validate_integration_request(token)
		# Load without permission check – token is the secret (Guest can open checkout URL)
		doc = frappe.get_doc("Integration Request", token, check_permission=False)
		payment_details = json.loads(doc.data)

		easebuzz_settings = frappe.get_doc("Easebuzz Settings", None, check_permission=False)
		request_data = easebuzz_settings.create_payment_request_data(doc.name, **payment_details)

		from payments.payment_gateways.doctype.easebuzz_settings.easebuzz_utils import initiate_payment_api

		result = initiate_payment_api(
			request_data["payment_data"],
			request_data["merchant_key"],
			request_data["salt"],
			request_data["environment"],
			split_payments=request_data.get("split_payments"),
		)

		if result.get("success") and result.get("data"):
			context.payment_url = result["data"]
			context.token = token
			context.header_img = getattr(easebuzz_settings, "header_img", None)
		else:
			frappe.log_error(
				f"Easebuzz initiate_payment_api failed: {result.get('message', 'Unknown error')}",
				"Easebuzz Checkout Error",
			)
			frappe.redirect_to_message(
				_("Payment Error"),
				_(result.get("message", "Could not start payment. Please try again.")),
				http_status_code=400,
				indicator_color="red",
			)
			frappe.local.flags.redirect_location = frappe.local.response.location
			raise frappe.Redirect

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
