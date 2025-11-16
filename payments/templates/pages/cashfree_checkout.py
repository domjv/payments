# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and Contributors
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

	try:
		# Validate token
		validate_integration_request(frappe.form_dict["token"])

		# Get integration request
		doc = frappe.get_doc("Integration Request", frappe.form_dict["token"])
		payment_details = json.loads(doc.data)

		# Set context variables
		for key in expected_keys:
			context[key] = payment_details.get(key, "")

		context["token"] = frappe.form_dict["token"]
		context["amount"] = float(context["amount"])
		
		# Get Cashfree-specific data
		context["payment_session_id"] = payment_details.get("payment_session_id", "")
		context["cf_order_id"] = payment_details.get("cf_order_id", "")
		
		# Get environment (sandbox or production)
		context["environment"] = payment_details.get("environment", "sandbox")

	except Exception:
		frappe.redirect_to_message(
			_("Invalid Token"),
			_("Seems token you are using is invalid!"),
			http_status_code=400,
			indicator_color="red",
		)

		frappe.local.flags.redirect_location = frappe.local.response.location
		raise frappe.Redirect


@frappe.whitelist(allow_guest=True)
def make_payment(order_id, payment_session_id, reference_doctype, reference_docname, token):
	"""Process payment after Cashfree checkout"""
	data = {
		"order_id": order_id,
		"payment_session_id": payment_session_id,
		"reference_docname": reference_docname,
		"reference_doctype": reference_doctype,
		"token": token,
	}

	# Get the appropriate Cashfree settings
	from payments.payment_gateways.doctype.cashfree_settings.cashfree_settings import CashfreeSettings
	
	# Get integration request to find company
	integration_request = frappe.get_doc("Integration Request", token)
	request_data = json.loads(integration_request.data)
	company = request_data.get("company")
	
	# Get Cashfree settings
	settings = CashfreeSettings.get_cashfree_settings_by_company(company)
	
	# Process payment
	response = settings.create_request(data)
	frappe.db.commit()
	
	return response
