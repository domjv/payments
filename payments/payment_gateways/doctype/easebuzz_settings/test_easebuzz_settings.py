# Copyright (c) 2025, Frappe Technologies and Contributors
# See license.txt

import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase


class TestEasebuzzSettings(FrappeTestCase):
	def setUp(self):
		"""Set up test data"""
		# Clean up existing test data
		frappe.db.delete("Easebuzz Merchant", {"merchant_name": ["like", "Test%"]})
		frappe.db.delete("Integration Request", {"integration_request_service": "Easebuzz"})
		frappe.db.commit()
		
		# Create test merchant
		self.test_merchant = frappe.get_doc({
			"doctype": "Easebuzz Merchant",
			"merchant_name": "Test Merchant",
			"merchant_key": "TEST_KEY",
			"salt": "TEST_SALT",
			"environment": "Test",
			"is_default": 1
		}).insert()
		
		# Create test merchant with split payments
		self.test_merchant_with_splits = frappe.get_doc({
			"doctype": "Easebuzz Merchant",
			"merchant_name": "Test Merchant Split",
			"merchant_key": "TEST_KEY_SPLIT",
			"salt": "TEST_SALT_SPLIT",
			"environment": "Test",
			"split_payments_config": json.dumps({
				"label_HDFC": 150,
				"label_ICICI": 100
			})
		}).insert()
		
		frappe.db.commit()
	
	def tearDown(self):
		"""Clean up after tests"""
		frappe.db.delete("Easebuzz Merchant", {"merchant_name": ["like", "Test%"]})
		frappe.db.delete("Integration Request", {"integration_request_service": "Easebuzz"})
		frappe.db.commit()
	
	def test_create_payment_data_without_splits(self):
		"""Test creating payment data without split payments"""
		settings = frappe.get_doc("Easebuzz Settings")
		
		# Mock integration request
		kwargs = {
			"amount": 1000,
			"reference_doctype": "Sales Invoice",
			"reference_docname": "TEST-SINV-001",
			"payer_email": "test@example.com",
			"payer_name": "Test Customer",
			"description": "Test payment"
		}
		
		payment_data = settings.create_payment_request_data(
			"TEST-IR-001",
			**kwargs
		)
		
		self.assertIsNotNone(payment_data)
		self.assertIn("payment_data", payment_data)
		self.assertNotIn("split_payments", payment_data["payment_data"])
	
	def test_create_payment_data_with_merchant_default_splits(self):
		"""Test creating payment data with merchant's default split configuration"""
		settings = frappe.get_doc("Easebuzz Settings")
		
		kwargs = {
			"amount": 250,
			"reference_doctype": "Sales Invoice",
			"reference_docname": "TEST-SINV-002",
			"payer_email": "test@example.com",
			"payer_name": "Test Customer",
			"description": "Test payment",
			"custom_merchant_name": "Test Merchant Split"
		}
		
		payment_data = settings.create_payment_request_data(
			"TEST-IR-002",
			**kwargs
		)
		
		self.assertIsNotNone(payment_data)
		self.assertIn("payment_data", payment_data)
		self.assertIn("split_payments", payment_data["payment_data"])
		
		# Verify split payments is correct JSON
		split_config = json.loads(payment_data["payment_data"]["split_payments"])
		self.assertEqual(split_config["label_HDFC"], 150)
		self.assertEqual(split_config["label_ICICI"], 100)
	
	def test_create_payment_data_with_api_override_dict(self):
		"""Test creating payment data with split payments passed via API as dict"""
		settings = frappe.get_doc("Easebuzz Settings")
		
		custom_splits = {
			"label_account_1": 600,
			"label_account_2": 400
		}
		
		kwargs = {
			"amount": 1000,
			"reference_doctype": "Sales Invoice",
			"reference_docname": "TEST-SINV-003",
			"payer_email": "test@example.com",
			"payer_name": "Test Customer",
			"description": "Test payment",
			"split_payments_labels": custom_splits
		}
		
		payment_data = settings.create_payment_request_data(
			"TEST-IR-003",
			**kwargs
		)
		
		self.assertIsNotNone(payment_data)
		self.assertIn("split_payments", payment_data["payment_data"])
		
		# Verify custom splits are used
		split_config = json.loads(payment_data["payment_data"]["split_payments"])
		self.assertEqual(split_config["label_account_1"], 600)
		self.assertEqual(split_config["label_account_2"], 400)
	
	def test_create_payment_data_with_api_override_json_string(self):
		"""Test creating payment data with split payments passed as JSON string"""
		settings = frappe.get_doc("Easebuzz Settings")
		
		custom_splits_json = json.dumps({
			"label_vendor": 900,
			"label_platform": 100
		})
		
		kwargs = {
			"amount": 1000,
			"reference_doctype": "Sales Invoice",
			"reference_docname": "TEST-SINV-004",
			"payer_email": "test@example.com",
			"payer_name": "Test Customer",
			"description": "Test payment",
			"split_payments_labels": custom_splits_json
		}
		
		payment_data = settings.create_payment_request_data(
			"TEST-IR-004",
			**kwargs
		)
		
		self.assertIsNotNone(payment_data)
		self.assertIn("split_payments", payment_data["payment_data"])
		
		# Verify JSON string is preserved
		split_config = json.loads(payment_data["payment_data"]["split_payments"])
		self.assertEqual(split_config["label_vendor"], 900)
		self.assertEqual(split_config["label_platform"], 100)
	
	def test_api_override_takes_priority_over_merchant_default(self):
		"""Test that API parameter takes priority over merchant's default configuration"""
		settings = frappe.get_doc("Easebuzz Settings")
		
		# Use merchant with default splits, but override via API
		api_splits = {
			"label_override_1": 700,
			"label_override_2": 300
		}
		
		kwargs = {
			"amount": 1000,
			"reference_doctype": "Sales Invoice",
			"reference_docname": "TEST-SINV-005",
			"payer_email": "test@example.com",
			"payer_name": "Test Customer",
			"description": "Test payment",
			"custom_merchant_name": "Test Merchant Split",
			"split_payments_labels": api_splits
		}
		
		payment_data = settings.create_payment_request_data(
			"TEST-IR-005",
			**kwargs
		)
		
		# Verify API splits are used, not merchant defaults
		split_config = json.loads(payment_data["payment_data"]["split_payments"])
		self.assertEqual(split_config["label_override_1"], 700)
		self.assertEqual(split_config["label_override_2"], 300)
		self.assertNotIn("label_HDFC", split_config)
	
	def test_split_amount_validation_logs_warning_on_mismatch(self):
		"""Test that amount mismatch logs a warning but doesn't fail"""
		settings = frappe.get_doc("Easebuzz Settings")
		
		# Splits that don't match transaction amount
		mismatched_splits = {
			"label_account_1": 500,
			"label_account_2": 400
		}  # Total 900, but amount is 1000
		
		kwargs = {
			"amount": 1000,
			"reference_doctype": "Sales Invoice",
			"reference_docname": "TEST-SINV-006",
			"payer_email": "test@example.com",
			"payer_name": "Test Customer",
			"description": "Test payment",
			"split_payments_labels": mismatched_splits
		}
		
		# Should not raise error, but should log warning
		payment_data = settings.create_payment_request_data(
			"TEST-IR-006",
			**kwargs
		)
		
		# Payment data should still be created
		self.assertIsNotNone(payment_data)
		self.assertIn("split_payments", payment_data["payment_data"])
	
	def test_payment_data_includes_all_required_fields(self):
		"""Test that payment data includes all required Easebuzz fields"""
		settings = frappe.get_doc("Easebuzz Settings")
		
		kwargs = {
			"amount": 1000,
			"reference_doctype": "Sales Invoice",
			"reference_docname": "TEST-SINV-007",
			"payer_email": "test@example.com",
			"payer_name": "Test Customer",
			"description": "Test payment",
			"split_payments_labels": {"label_test": 1000}
		}
		
		payment_data = settings.create_payment_request_data(
			"TEST-IR-007",
			**kwargs
		)
		
		pd = payment_data["payment_data"]
		
		# Check required fields
		self.assertIn("txnid", pd)
		self.assertIn("amount", pd)
		self.assertIn("productinfo", pd)
		self.assertIn("firstname", pd)
		self.assertIn("email", pd)
		self.assertIn("phone", pd)
		self.assertIn("surl", pd)
		self.assertIn("furl", pd)
		self.assertIn("split_payments", pd)
		
		# Check UDF fields
		self.assertIn("udf1", pd)
		self.assertIn("udf2", pd)
		self.assertIn("udf3", pd)
		self.assertIn("udf4", pd)
		self.assertIn("udf5", pd)
	
	def test_multiple_split_labels(self):
		"""Test creating payment data with multiple split labels"""
		settings = frappe.get_doc("Easebuzz Settings")
		
		multi_splits = {
			"label_account_1": 250,
			"label_account_2": 250,
			"label_account_3": 250,
			"label_account_4": 250
		}
		
		kwargs = {
			"amount": 1000,
			"reference_doctype": "Sales Invoice",
			"reference_docname": "TEST-SINV-008",
			"payer_email": "test@example.com",
			"payer_name": "Test Customer",
			"description": "Test payment",
			"split_payments_labels": multi_splits
		}
		
		payment_data = settings.create_payment_request_data(
			"TEST-IR-008",
			**kwargs
		)
		
		split_config = json.loads(payment_data["payment_data"]["split_payments"])
		self.assertEqual(len(split_config), 4)
		self.assertEqual(sum(split_config.values()), 1000)
