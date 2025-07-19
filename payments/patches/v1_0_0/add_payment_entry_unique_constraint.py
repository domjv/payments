# Copyright (c) 2024, Frappe Technologies and contributors
# License: MIT. See LICENSE

import frappe
from payments.utils.ivyliving_methods import cleanup_duplicate_payment_entries, ensure_payment_entry_unique_constraint

def execute():
    """Add unique constraint to Payment Entry reference_no field to prevent duplicates"""
    # First cleanup any existing duplicates
    cleanup_duplicate_payment_entries()
    
    # Then add the unique constraint
    ensure_payment_entry_unique_constraint() 