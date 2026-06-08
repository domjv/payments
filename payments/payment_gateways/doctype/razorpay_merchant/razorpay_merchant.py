# Copyright (c) 2026, Frappe Technologies and contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.model.document import Document


class RazorpayMerchant(Document):
	def validate(self):
		self._validate_single_default()

	def _validate_single_default(self):
		"""Ensure only one merchant is marked as default."""
		if self.is_default:
			existing = frappe.db.get_value(
				"Razorpay Merchant",
				{"is_default": 1, "name": ["!=", self.name]},
				"name",
			)
			if existing:
				frappe.throw(
					_("Merchant {0} is already set as the default Razorpay merchant. Only one merchant can be the default.").format(existing)
				)


def get_default_merchant():
	"""Return the name of the default Razorpay Merchant, or None if none exists."""
	return frappe.db.get_value("Razorpay Merchant", {"is_default": 1}, "name")
