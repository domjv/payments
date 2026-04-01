# Copyright (c) 2025, Frappe Technologies and Contributors
# See license.txt

import json

import frappe
from frappe.tests.utils import FrappeTestCase


class TestEasebuzzMerchant(FrappeTestCase):
	def setUp(self):
		"""Set up test data"""
		# Clean up any existing test merchants
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
	
	def test_create_merchant_with_valid_split_payments(self):
		"""Test creating a merchant with valid split payments configuration"""
		split_config = {
			"label_HDFC": 150,
			"label_ICICI": 100
		}
		
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
		self.assertEqual(merchant.split_payments_config, json.dumps(split_config))
	
	def test_invalid_json_format(self):
		"""Test that invalid JSON format raises error"""
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
		"""Test that non-dictionary split config raises error"""
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
	
	def test_invalid_amount_type(self):
		"""Test that non-numeric amounts raise error"""
		split_config = {
			"label_HDFC": "not_a_number",
			"label_ICICI": 100
		}
		
		merchant = frappe.get_doc({
			"doctype": "Easebuzz Merchant",
			"merchant_name": "Test Merchant Invalid Amount",
			"merchant_key": "TEST_KEY_111",
			"salt": "TEST_SALT_111",
			"environment": "Test",
			"split_payments_config": json.dumps(split_config)
		})
		
		with self.assertRaises(frappe.ValidationError):
			merchant.insert()
	
	def test_negative_amount(self):
		"""Test that negative amounts raise error"""
		split_config = {
			"label_HDFC": -100,
			"label_ICICI": 100
		}
		
		merchant = frappe.get_doc({
			"doctype": "Easebuzz Merchant",
			"merchant_name": "Test Merchant Negative",
			"merchant_key": "TEST_KEY_222",
			"salt": "TEST_SALT_222",
			"environment": "Test",
			"split_payments_config": json.dumps(split_config)
		})
		
		with self.assertRaises(frappe.ValidationError):
			merchant.insert()
	
	def test_zero_amount(self):
		"""Test that zero amounts raise error"""
		split_config = {
			"label_HDFC": 0,
			"label_ICICI": 100
		}
		
		merchant = frappe.get_doc({
			"doctype": "Easebuzz Merchant",
			"merchant_name": "Test Merchant Zero",
			"merchant_key": "TEST_KEY_333",
			"salt": "TEST_SALT_333",
			"environment": "Test",
			"split_payments_config": json.dumps(split_config)
		})
		
		with self.assertRaises(frappe.ValidationError):
			merchant.insert()
	
	def test_empty_label(self):
		"""Test that empty labels raise error"""
		split_config = {
			"": 100,
			"label_ICICI": 100
		}
		
		merchant = frappe.get_doc({
			"doctype": "Easebuzz Merchant",
			"merchant_name": "Test Merchant Empty Label",
			"merchant_key": "TEST_KEY_444",
			"salt": "TEST_SALT_444",
			"environment": "Test",
			"split_payments_config": json.dumps(split_config)
		})
		
		with self.assertRaises(frappe.ValidationError):
			merchant.insert()
	
	def test_multiple_labels(self):
		"""Test creating merchant with multiple split labels"""
		split_config = {
			"label_account_1": 100,
			"label_account_2": 50,
			"label_account_3": 30,
			"label_account_4": 20
		}
		
		merchant = frappe.get_doc({
			"doctype": "Easebuzz Merchant",
			"merchant_name": "Test Merchant Multiple",
			"merchant_key": "TEST_KEY_555",
			"salt": "TEST_SALT_555",
			"environment": "Test",
			"split_payments_config": json.dumps(split_config)
		})
		merchant.insert()
		
		self.assertTrue(merchant.name)
		saved_config = json.loads(merchant.split_payments_config)
		self.assertEqual(len(saved_config), 4)
		self.assertEqual(saved_config["label_account_1"], 100)
	
	def test_decimal_amounts(self):
		"""Test that decimal amounts are accepted"""
		split_config = {
			"label_HDFC": 150.50,
			"label_ICICI": 99.50
		}
		
		merchant = frappe.get_doc({
			"doctype": "Easebuzz Merchant",
			"merchant_name": "Test Merchant Decimal",
			"merchant_key": "TEST_KEY_666",
			"salt": "TEST_SALT_666",
			"environment": "Test",
			"split_payments_config": json.dumps(split_config)
		})
		merchant.insert()
		
		self.assertTrue(merchant.name)
		saved_config = json.loads(merchant.split_payments_config)
		self.assertEqual(saved_config["label_HDFC"], 150.50)
