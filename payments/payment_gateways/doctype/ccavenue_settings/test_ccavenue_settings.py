# Copyright (c) 2024, Frappe Technologies and Contributors
# License: MIT. See LICENSE
import unittest

import frappe


class TestCCAvenueSettings(unittest.TestCase):
    def setUp(self):
        # Create test settings
        if not frappe.db.exists("CCAvenue Settings"):
            settings = frappe.new_doc("CCAvenue Settings")
            settings.merchant_id = "test_merchant_id"
            settings.access_code = "test_access_code"
            settings.encryption_key = "test_encryption_key"
            settings.environment = "Sandbox"
            settings.save()
    
    def test_create_payment_gateway(self):
        """Test if CCAvenue Payment Gateway is created"""
        self.assertTrue(frappe.db.exists("Payment Gateway", "CCAvenue"))
    
    def test_supported_currencies(self):
        """Test if supported currencies are properly defined"""
        settings = frappe.get_doc("CCAvenue Settings")
        self.assertTrue("INR" in settings.supported_currencies)
        self.assertTrue("USD" in settings.supported_currencies)
    
    def tearDown(self):
        # Clean up test data
        if frappe.db.exists("CCAvenue Settings"):
            frappe.db.rollback()