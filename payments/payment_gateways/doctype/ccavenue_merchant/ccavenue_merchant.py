# Copyright (c) 2025, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CCAvenueMerchant(Document):
	def validate(self):
		"""Validate merchant configuration"""
		# Ensure only one default merchant exists
		if self.is_default:
			self.ensure_single_default()
	
	def ensure_single_default(self):
		"""Ensure only one merchant is marked as default"""
		existing_defaults = frappe.get_all(
			"CCAvenue Merchant",
			filters={"is_default": 1, "name": ["!=", self.name]},
			fields=["name"]
		)
		
		if existing_defaults:
			# Uncheck other defaults
			for default in existing_defaults:
				frappe.db.set_value("CCAvenue Merchant", default.name, "is_default", 0)
			
			frappe.msgprint(
				_("Previous default merchant has been updated. This is now the default merchant."),
				indicator="blue"
			)


def get_default_merchant():
	"""Get the default merchant or create one if none exists"""
	default_merchant = frappe.db.get_value(
		"CCAvenue Merchant",
		{"is_default": 1},
		["name", "merchant_name"],
		as_dict=True
	)
	
	if not default_merchant:
		# Check if any merchant exists
		any_merchant = frappe.db.get_value(
			"CCAvenue Merchant",
			{},
			["name", "merchant_name"],
			as_dict=True
		)
		
		if any_merchant:
			# Mark the first merchant as default
			frappe.db.set_value("CCAvenue Merchant", any_merchant.name, "is_default", 1)
			frappe.db.commit()
			return any_merchant.name
		else:
			# Create a default merchant with test credentials
			try:
				default_company = frappe.defaults.get_defaults().get("company")
				merchant_name = f"Default - {default_company}" if default_company else "Default Merchant"
				
				new_merchant = frappe.get_doc({
					"doctype": "CCAvenue Merchant",
					"merchant_name": merchant_name,
					"is_default": 1,
					"merchant_id": "TEST_MERCHANT_ID",
					"access_code": "TEST_ACCESS_CODE",
					"encryption_key": "TEST_ENCRYPTION_KEY",
					"enviroment": "Sandbox",
					"company": default_company if default_company else None
				})
				new_merchant.insert(ignore_permissions=True)
				frappe.db.commit()
				
				frappe.msgprint(
					_(f"Default merchant '{merchant_name}' created with test credentials. Please update with actual CCAvenue credentials."),
					indicator="orange"
				)
				
				return new_merchant.name
			except Exception as e:
				frappe.log_error(f"Failed to create default merchant: {str(e)}")
				return None
	
	return default_merchant.name
