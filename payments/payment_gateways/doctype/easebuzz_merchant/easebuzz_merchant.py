# Copyright (c) 2025, Frappe Technologies and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document


class EasebuzzMerchant(Document):
	def validate(self):
		"""Validate merchant configuration"""
		# Ensure only one default merchant exists
		if self.is_default:
			self.ensure_single_default()
		
		# Validate split payments configuration if provided
		self.validate_split_payments_config()
	
	def ensure_single_default(self):
		"""Ensure only one merchant is marked as default"""
		existing_defaults = frappe.get_all(
			"Easebuzz Merchant",
			filters={"is_default": 1, "name": ["!=", self.name]},
			fields=["name"]
		)
		
		if existing_defaults:
			# Uncheck other defaults
			for default in existing_defaults:
				frappe.db.set_value("Easebuzz Merchant", default.name, "is_default", 0)
			
			frappe.msgprint(
				_("Previous default merchant has been updated. This is now the default merchant."),
				indicator="blue"
			)
	
	def validate_split_payments_config(self):
		"""Validate split payments JSON format"""
		if not self.split_payments_config:
			return
		
		try:
			split_data = json.loads(self.split_payments_config)
			
			# Validate format: must be a dictionary
			if not isinstance(split_data, dict):
				frappe.throw(_("Split payments configuration must be a JSON object (dictionary)."))
			
			# Validate each label and amount
			for label, amount in split_data.items():
				# Validate label format (should be alphanumeric with underscores)
				if not isinstance(label, str) or not label:
					frappe.throw(_("Split payment labels must be non-empty strings."))
				
				# Validate amount is numeric
				if not isinstance(amount, (int, float)):
					frappe.throw(_("Split payment amount for label '{0}' must be numeric.").format(label))
				
				# Validate amount is positive
				if amount <= 0:
					frappe.throw(_("Split payment amount for label '{0}' must be positive.").format(label))
		
		except json.JSONDecodeError as e:
			frappe.throw(_("Invalid JSON format in split payments configuration: {0}").format(str(e)))
		except Exception as e:
			if "throw" not in str(e.__class__):
				frappe.throw(_("Error validating split payments configuration: {0}").format(str(e)))


def get_default_merchant():
	"""Get the default merchant or create one if none exists"""
	default_merchant = frappe.db.get_value(
		"Easebuzz Merchant",
		{"is_default": 1},
		["name", "merchant_name"],
		as_dict=True
	)
	
	if not default_merchant:
		# Check if any merchant exists
		any_merchant = frappe.db.get_value(
			"Easebuzz Merchant",
			{},
			["name", "merchant_name"],
			as_dict=True
		)
		
		if any_merchant:
			# Mark first merchant as default
			frappe.db.set_value("Easebuzz Merchant", any_merchant.name, "is_default", 1)
			frappe.db.commit()
			return any_merchant.name
		
		# No merchants exist, return None
		return None
	
	return default_merchant.name


def get_merchant_for_company(company=None, merchant_name=None):
	"""
	Get the appropriate merchant configuration based on company.
	Priority: 
	1. Explicit merchant_name if provided
	2. Company-specific merchant
	3. Default merchant
	
	Args:
		company (str): Company name to find merchant for
		merchant_name (str): Explicit merchant name to use
		
	Returns:
		Document: Easebuzz Merchant document or None
	"""
	# If explicit merchant name provided, use it
	if merchant_name:
		try:
			return frappe.get_doc("Easebuzz Merchant", merchant_name)
		except frappe.DoesNotExistError:
			frappe.log_error(f"Merchant {merchant_name} not found, falling back to company/default merchant")
	
	# Try to find company-specific merchant
	if company:
		merchant = frappe.db.get_value(
			"Easebuzz Merchant",
			{"company": company},
			["name"],
			as_dict=False
		)
		if merchant:
			return frappe.get_doc("Easebuzz Merchant", merchant)
	
	# Fall back to default merchant
	default_merchant_name = get_default_merchant()
	
	if default_merchant_name:
		return frappe.get_doc("Easebuzz Merchant", default_merchant_name)
	
	frappe.throw(_("No Easebuzz Merchant configuration found. Please create a merchant configuration."))
