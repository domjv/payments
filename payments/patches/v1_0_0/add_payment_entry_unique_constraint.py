# Copyright (c) 2024, Frappe Technologies and contributors
# License: MIT. See LICENSE

import frappe
from payments.utils.ivyliving_methods import cleanup_duplicate_payment_entries

def execute():
    """Clean up duplicate Payment Entries"""
    # Cleanup any existing duplicates
    cleanup_duplicate_payment_entries() 