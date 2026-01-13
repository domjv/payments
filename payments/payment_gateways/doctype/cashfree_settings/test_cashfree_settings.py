# Copyright (c) 2025, Frappe Technologies and Contributors
# License: MIT. See LICENSE

import unittest

import frappe


class TestCashfreeSettings(unittest.TestCase):
	def setUp(self):
		# Create test Cashfree Settings
		if not frappe.db.exists("Cashfree Settings", "Test Cashfree"):
			frappe.get_doc({
				"doctype": "Cashfree Settings",
				"gateway_name": "Test Cashfree",
				"client_id": "TEST_CLIENT_ID",
				"client_secret": "TEST_CLIENT_SECRET",
				"environment": "Sandbox",
				"is_default": 1
			}).insert(ignore_permissions=True)
			frappe.db.commit()

	def tearDown(self):
		# Clean up
		if frappe.db.exists("Cashfree Settings", "Test Cashfree"):
			frappe.delete_doc("Cashfree Settings", "Test Cashfree", force=1)
			frappe.db.commit()

	def test_cashfree_settings_creation(self):
		"""Test that Cashfree Settings can be created"""
		settings = frappe.get_doc("Cashfree Settings", "Test Cashfree")
		self.assertEqual(settings.gateway_name, "Test Cashfree")
		self.assertEqual(settings.environment, "Sandbox")
		self.assertTrue(settings.is_default)

	def test_payment_gateway_created(self):
		"""Test that Payment Gateway is created on save"""
		gateway_name = "Cashfree-Test Cashfree"
		if frappe.db.exists("Payment Gateway", gateway_name):
			gateway = frappe.get_doc("Payment Gateway", gateway_name)
			self.assertEqual(gateway.gateway_controller, "Test Cashfree")

	def test_webhook_url_generated(self):
		"""Test that webhook URL is auto-generated"""
		settings = frappe.get_doc("Cashfree Settings", "Test Cashfree")
		self.assertTrue(settings.webhook_url)
		self.assertIn("cashfree_webhook", settings.webhook_url)

	def test_get_cashfree_settings_by_company(self):
		"""Test getting Cashfree settings by company"""
		from payments.payment_gateways.doctype.cashfree_settings.cashfree_settings import CashfreeSettings
		
		# Should return default settings when no company specified
		settings = CashfreeSettings.get_cashfree_settings_by_company()
		self.assertEqual(settings.name, "Test Cashfree")

	def test_validate_transaction_currency(self):
		"""Test currency validation"""
		settings = frappe.get_doc("Cashfree Settings", "Test Cashfree")
		
		# INR should be supported
		try:
			settings.validate_transaction_currency("INR")
		except Exception as e:
			self.fail(f"INR should be supported: {e}")
		
		# Invalid currency should raise error
		with self.assertRaises(frappe.exceptions.ValidationError):
			settings.validate_transaction_currency("XXX")
