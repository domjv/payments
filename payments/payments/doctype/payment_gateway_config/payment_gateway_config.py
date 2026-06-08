# Copyright (c) 2026, Frappe Technologies and contributors
# License: MIT. See LICENSE

import frappe
from frappe.model.document import Document


class PaymentGatewayConfig(Document):
	pass


def get_gateway_for_company(company):
	"""
	Return the preferred payment gateway name and optional merchant name
	for the given company.

	Looks up a Payment Gateway Config record keyed to the company.
	Falls back to "CCAvenue" (legacy default) if none is found.

	Returns:
	    tuple: (gateway_name: str, merchant_name: str | None)

	Example::

	    gateway, merchant = get_gateway_for_company("Hostel A")
	    # gateway = "Razorpay", merchant = "HsA-RP"
	"""
	if not company:
		return "CCAvenue", None

	config = frappe.db.get_value(
		"Payment Gateway Config",
		{"company": company},
		["preferred_gateway", "merchant_name"],
		as_dict=True,
	)

	if config:
		return config.preferred_gateway, config.merchant_name or None

	return "CCAvenue", None
