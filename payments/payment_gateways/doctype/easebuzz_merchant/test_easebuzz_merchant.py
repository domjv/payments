# Copyright (c) 2025, Frappe Technologies and Contributors
# See license.txt

import json

import frappe
from frappe.tests.utils import FrappeTestCase


class TestEasebuzzMerchant(FrappeTestCase):
	def setUp(self):
		"""Set up test data"""
		frappe.db.delete("Easebuzz Merchant", {"merchant_name": ["like", "Test%"]})
		frappe.db.commit()

	def tearDown(self):
		"""Clean up after tests"""
		frappe.db.delete("Easebuzz Merchant", {"merchant_name": ["like", "Test%"]})
		frappe.db.commit()

	def test_create_merchant_without_split_payments(self):
		"""Test creating a merchant without split payments configuration"""
		merchant = frappe.get_doc({
			"doctype": "Easebuzz Merchant",
			"merchant_name": "Test Merchant Basic",
			"merchant_key": "TEST_KEY_123",
			"salt": "TEST_SALT_123",
			"environment": "Test",
			"is_default": 1
		})
		merchant.insert()

		self.assertTrue(merchant.name)
		self.assertEqual(merchant.merchant_name, "Test Merchant Basic")
		self.assertFalse(merchant.split_payments_config)

	def test_create_merchant_with_valid_split_payments_two_labels(self):
		"""Test creating a merchant with a valid 2-label percentage split (must sum to 100)"""
		split_config = {"label_HDFC": 60, "label_ICICI": 40}

		merchant = frappe.get_doc({
			"doctype": "Easebuzz Merchant",
			"merchant_name": "Test Merchant Split",
			"merchant_key": "TEST_KEY_456",
			"salt": "TEST_SALT_456",
			"environment": "Test",
			"split_payments_config": json.dumps(split_config)
		})
		merchant.insert()

		self.assertTrue(merchant.name)
		saved = json.loads(merchant.split_payments_config)
		self.assertAlmostEqual(saved["label_HDFC"], 60)
		self.assertAlmostEqual(saved["label_ICICI"], 40)

	def test_create_merchant_with_three_way_split(self):
		"""Test a 3-label split configuration"""
		split_config = {"label_platform": 10, "label_vendor_a": 55, "label_vendor_b": 35}

		merchant = frappe.get_doc({
			"doctype": "Easebuzz Merchant",
			"merchant_name": "Test Merchant Three Way",
			"merchant_key": "TEST_KEY_3W",
			"salt": "TEST_SALT_3W",
			"environment": "Test",
			"split_payments_config": json.dumps(split_config)
		})
		merchant.insert()

		self.assertTrue(merchant.name)
		saved = json.loads(merchant.split_payments_config)
		self.assertEqual(len(saved), 3)
		self.assertAlmostEqual(sum(saved.values()), 100)

	def test_invalid_json_format(self):
		"""Invalid JSON raises ValidationError"""
		merchant = frappe.get_doc({
			"doctype": "Easebuzz Merchant",
			"merchant_name": "Test Merchant Invalid JSON",
			"merchant_key": "TEST_KEY_789",
			"salt": "TEST_SALT_789",
			"environment": "Test",
			"split_payments_config": "invalid json {label: 100}"
		})
		with self.assertRaises(frappe.ValidationError):
			merchant.insert()

	def test_non_dict_split_config(self):
		"""Non-dictionary JSON raises ValidationError"""
		merchant = frappe.get_doc({
			"doctype": "Easebuzz Merchant",
			"merchant_name": "Test Merchant Invalid Type",
			"merchant_key": "TEST_KEY_999",
			"salt": "TEST_SALT_999",
			"environment": "Test",
			"split_payments_config": json.dumps(["label_HDFC", "label_ICICI"])
		})
		with self.assertRaises(frappe.ValidationError):
			merchant.insert()

	def test_only_one_label_raises_error(self):
		"""Only one label raises ValidationError (need at least 2)"""
		merchant = frappe.get_doc({
			"doctype": "Easebuzz Merchant",
			"merchant_name": "Test Merchant One Label",
			"merchant_key": "TEST_KEY_1L",
			"salt": "TEST_SALT_1L",
			"environment": "Test",
			"split_payments_config": json.dumps({"label_only": 100})
		})
		with self.assertRaises(frappe.ValidationError):
			merchant.insert()

	def test_percentages_not_summing_to_100(self):
		"""Percentages that don't sum to 100 raise ValidationError"""
		merchant = frappe.get_doc({
			"doctype": "Easebuzz Merchant",
			"merchant_name": "Test Merchant Bad Sum",
			"merchant_key": "TEST_KEY_BS",
			"salt": "TEST_SALT_BS",
			"environment": "Test",
			"split_payments_config": json.dumps({"label_HDFC": 60, "label_ICICI": 30})  # 90 total
		})
		with self.assertRaises(frappe.ValidationError):
			merchant.insert()

	def test_negative_percentage_raises_error(self):
		"""Negative percentage raises ValidationError"""
		merchant = frappe.get_doc({
			"doctype": "Easebuzz Merchant",
			"merchant_name": "Test Merchant Neg Pct",
			"merchant_key": "TEST_KEY_NP",
			"salt": "TEST_SALT_NP",
			"environment": "Test",
			"split_payments_config": json.dumps({"label_HDFC": -10, "label_ICICI": 110})
		})
		with self.assertRaises(frappe.ValidationError):
			merchant.insert()

	def test_zero_percentage_raises_error(self):
		"""Zero percentage raises ValidationError"""
		merchant = frappe.get_doc({
			"doctype": "Easebuzz Merchant",
			"merchant_name": "Test Merchant Zero Pct",
			"merchant_key": "TEST_KEY_ZP",
			"salt": "TEST_SALT_ZP",
			"environment": "Test",
			"split_payments_config": json.dumps({"label_HDFC": 0, "label_ICICI": 100})
		})
		with self.assertRaises(frappe.ValidationError):
			merchant.insert()

	def test_over_100_percentage_raises_error(self):
		"""Individual percentage > 100 raises ValidationError"""
		merchant = frappe.get_doc({
			"doctype": "Easebuzz Merchant",
			"merchant_name": "Test Merchant Over Pct",
			"merchant_key": "TEST_KEY_OP",
			"salt": "TEST_SALT_OP",
			"environment": "Test",
			"split_payments_config": json.dumps({"label_HDFC": 110, "label_ICICI": -10})
		})
		with self.assertRaises(frappe.ValidationError):
			merchant.insert()

	def test_empty_label_raises_error(self):
		"""Empty string label raises ValidationError"""
		merchant = frappe.get_doc({
			"doctype": "Easebuzz Merchant",
			"merchant_name": "Test Merchant Empty Label",
			"merchant_key": "TEST_KEY_EL",
			"salt": "TEST_SALT_EL",
			"environment": "Test",
			"split_payments_config": json.dumps({"": 50, "label_ICICI": 50})
		})
		with self.assertRaises(frappe.ValidationError):
			merchant.insert()

	def test_four_way_split_with_rounding(self):
		"""Four-label split where percentages use decimal precision"""
		# 25 + 25 + 25 + 25 = 100 exactly
		split_config = {
			"label_a": 25,
			"label_b": 25,
			"label_c": 25,
			"label_d": 25
		}
		merchant = frappe.get_doc({
			"doctype": "Easebuzz Merchant",
			"merchant_name": "Test Merchant Four Way",
			"merchant_key": "TEST_KEY_4W",
			"salt": "TEST_SALT_4W",
			"environment": "Test",
			"split_payments_config": json.dumps(split_config)
		})
		merchant.insert()
		self.assertTrue(merchant.name)

	def test_decimal_percentages_summing_to_100(self):
		"""Decimal percentages that sum to 100 are accepted"""
		split_config = {"label_a": 33.33, "label_b": 33.33, "label_c": 33.34}
		merchant = frappe.get_doc({
			"doctype": "Easebuzz Merchant",
			"merchant_name": "Test Merchant Decimal Pct",
			"merchant_key": "TEST_KEY_DP",
			"salt": "TEST_SALT_DP",
			"environment": "Test",
			"split_payments_config": json.dumps(split_config)
		})
		merchant.insert()
		self.assertTrue(merchant.name)

