# Copyright (c) 2025, Frappe Technologies and Contributors
# See license.txt

import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase


class TestEasebuzzSettings(FrappeTestCase):
	def setUp(self):
		"""Set up test data"""
		frappe.db.delete("Easebuzz Merchant", {"merchant_name": ["like", "Test%"]})
		frappe.db.delete("Integration Request", {"integration_request_service": "Easebuzz"})
		frappe.db.commit()

		# Basic merchant (no splits)
		self.test_merchant = frappe.get_doc({
			"doctype": "Easebuzz Merchant",
			"merchant_name": "Test Merchant",
			"merchant_key": "TEST_KEY",
			"salt": "TEST_SALT",
			"environment": "Test",
			"is_default": 1
		}).insert()

		# Merchant with 2-label 60/40 percentage split
		self.test_merchant_with_splits = frappe.get_doc({
			"doctype": "Easebuzz Merchant",
			"merchant_name": "Test Merchant Split",
			"merchant_key": "TEST_KEY_SPLIT",
			"salt": "TEST_SALT_SPLIT",
			"environment": "Test",
			"split_payments_config": json.dumps({"label_HDFC": 60, "label_ICICI": 40})
		}).insert()

		frappe.db.commit()

	def tearDown(self):
		"""Clean up after tests"""
		frappe.db.delete("Easebuzz Merchant", {"merchant_name": ["like", "Test%"]})
		frappe.db.delete("Integration Request", {"integration_request_service": "Easebuzz"})
		frappe.db.commit()

	def test_create_payment_data_without_splits(self):
		"""Payment data without split configuration omits split_payments key"""
		settings = frappe.get_doc("Easebuzz Settings")
		kwargs = {
			"amount": 1000,
			"reference_doctype": "Sales Invoice",
			"reference_docname": "TEST-SINV-001",
			"payer_email": "test@example.com",
			"payer_name": "Test Customer",
			"description": "Test payment"
		}
		payment_data = settings.create_payment_request_data("TEST-IR-001", **kwargs)

		self.assertIsNotNone(payment_data)
		self.assertIn("payment_data", payment_data)
		self.assertNotIn("split_payments", payment_data["payment_data"])

	def test_create_payment_data_with_merchant_default_percentage_splits(self):
		"""Merchant 60/40 split converts to correct INR amounts for a ₹1000 payment"""
		settings = frappe.get_doc("Easebuzz Settings")
		kwargs = {
			"amount": 1000,
			"reference_doctype": "Sales Invoice",
			"reference_docname": "TEST-SINV-002",
			"payer_email": "test@example.com",
			"payer_name": "Test Customer",
			"description": "Test payment",
			"custom_merchant_name": "Test Merchant Split"
		}
		payment_data = settings.create_payment_request_data("TEST-IR-002", **kwargs)

		self.assertIn("split_payments", payment_data["payment_data"])
		split_result = json.loads(payment_data["payment_data"]["split_payments"])
		# 60% of 1000 = 600, 40% of 1000 = 400
		self.assertAlmostEqual(split_result["label_HDFC"], 600.0, places=2)
		self.assertAlmostEqual(split_result["label_ICICI"], 400.0, places=2)
		self.assertAlmostEqual(sum(split_result.values()), 1000.0, places=2)

	def test_api_override_percentages_as_dict(self):
		"""API-supplied percentage dict is correctly converted to amounts"""
		settings = frappe.get_doc("Easebuzz Settings")
		custom_pct = {"label_platform": 10, "label_vendor_a": 55, "label_vendor_b": 35}
		kwargs = {
			"amount": 1000,
			"reference_doctype": "Sales Invoice",
			"reference_docname": "TEST-SINV-003",
			"payer_email": "test@example.com",
			"payer_name": "Test Customer",
			"description": "Test payment",
			"split_payments_labels": custom_pct
		}
		payment_data = settings.create_payment_request_data("TEST-IR-003", **kwargs)

		split_result = json.loads(payment_data["payment_data"]["split_payments"])
		self.assertEqual(len(split_result), 3)
		self.assertAlmostEqual(split_result["label_platform"], 100.0, places=2)
		self.assertAlmostEqual(split_result["label_vendor_a"], 550.0, places=2)
		self.assertAlmostEqual(split_result["label_vendor_b"], 350.0, places=2)
		self.assertAlmostEqual(sum(split_result.values()), 1000.0, places=2)

	def test_api_override_percentages_as_json_string(self):
		"""API-supplied percentage JSON string is correctly converted to amounts"""
		settings = frappe.get_doc("Easebuzz Settings")
		kwargs = {
			"amount": 500,
			"reference_doctype": "Sales Invoice",
			"reference_docname": "TEST-SINV-004",
			"payer_email": "test@example.com",
			"payer_name": "Test Customer",
			"description": "Test payment",
			"split_payments_labels": json.dumps({"label_vendor": 80, "label_platform": 20})
		}
		payment_data = settings.create_payment_request_data("TEST-IR-004", **kwargs)

		split_result = json.loads(payment_data["payment_data"]["split_payments"])
		self.assertAlmostEqual(split_result["label_vendor"], 400.0, places=2)
		self.assertAlmostEqual(split_result["label_platform"], 100.0, places=2)

	def test_api_override_takes_priority_over_merchant_default(self):
		"""API-supplied percentages override the merchant's stored split_payments_config"""
		settings = frappe.get_doc("Easebuzz Settings")
		api_pct = {"label_override_a": 70, "label_override_b": 30}
		kwargs = {
			"amount": 1000,
			"reference_doctype": "Sales Invoice",
			"reference_docname": "TEST-SINV-005",
			"payer_email": "test@example.com",
			"payer_name": "Test Customer",
			"description": "Test payment",
			"custom_merchant_name": "Test Merchant Split",
			"split_payments_labels": api_pct
		}
		payment_data = settings.create_payment_request_data("TEST-IR-005", **kwargs)

		split_result = json.loads(payment_data["payment_data"]["split_payments"])
		self.assertIn("label_override_a", split_result)
		self.assertNotIn("label_HDFC", split_result)

	def test_rounding_remainder_applied_to_last_label(self):
		"""Rounding remainder is added to the last label so totals equal transaction amount"""
		settings = frappe.get_doc("Easebuzz Settings")
		# 33.33 + 33.33 + 33.34 = 100.00 (but per-label amounts on ₹100 will be 33.33, 33.33, 33.34)
		kwargs = {
			"amount": 100,
			"reference_doctype": "Sales Invoice",
			"reference_docname": "TEST-SINV-006",
			"payer_email": "test@example.com",
			"payer_name": "Test Customer",
			"description": "Test payment",
			"split_payments_labels": {"label_a": 33.33, "label_b": 33.33, "label_c": 33.34}
		}
		payment_data = settings.create_payment_request_data("TEST-IR-006", **kwargs)

		split_result = json.loads(payment_data["payment_data"]["split_payments"])
		self.assertAlmostEqual(sum(split_result.values()), 100.0, places=2)

	def test_four_way_equal_split(self):
		"""4 equal 25% shares all compute correctly"""
		settings = frappe.get_doc("Easebuzz Settings")
		kwargs = {
			"amount": 1000,
			"reference_doctype": "Sales Invoice",
			"reference_docname": "TEST-SINV-007",
			"payer_email": "test@example.com",
			"payer_name": "Test Customer",
			"description": "Test payment",
			"split_payments_labels": {"label_a": 25, "label_b": 25, "label_c": 25, "label_d": 25}
		}
		payment_data = settings.create_payment_request_data("TEST-IR-007", **kwargs)

		split_result = json.loads(payment_data["payment_data"]["split_payments"])
		self.assertEqual(len(split_result), 4)
		for v in split_result.values():
			self.assertAlmostEqual(v, 250.0, places=2)
		self.assertAlmostEqual(sum(split_result.values()), 1000.0, places=2)

	def test_payment_data_includes_all_required_fields(self):
		"""Payment data contains all required Easebuzz fields"""
		settings = frappe.get_doc("Easebuzz Settings")
		kwargs = {
			"amount": 1000,
			"reference_doctype": "Sales Invoice",
			"reference_docname": "TEST-SINV-008",
			"payer_email": "test@example.com",
			"payer_name": "Test Customer",
			"description": "Test payment",
			"split_payments_labels": {"label_test_a": 60, "label_test_b": 40}
		}
		payment_data = settings.create_payment_request_data("TEST-IR-008", **kwargs)
		pd = payment_data["payment_data"]

		for field in ("txnid", "amount", "productinfo", "firstname", "email", "phone",
		              "surl", "furl", "udf1", "udf2", "udf3", "udf4", "udf5", "split_payments"):
			self.assertIn(field, pd)

	def test_no_split_when_config_absent(self):
		"""A merchant with no split_payments_config produces no split_payments key"""
		settings = frappe.get_doc("Easebuzz Settings")
		kwargs = {
			"amount": 500,
			"reference_doctype": "Sales Invoice",
			"reference_docname": "TEST-SINV-009",
			"payer_email": "test@example.com",
			"payer_name": "Test Customer",
			"description": "Test payment",
			"custom_merchant_name": "Test Merchant"  # the no-split merchant
		}
		payment_data = settings.create_payment_request_data("TEST-IR-009", **kwargs)
		self.assertNotIn("split_payments", payment_data["payment_data"])

