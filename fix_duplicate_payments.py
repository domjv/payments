#!/usr/bin/env python3
"""
Script to fix duplicate Payment Entries in CCAvenue payments.
Run this script to clean up existing duplicates and prevent future ones.

Usage:
    bench --site your-site.com execute fix_duplicate_payments.py
"""

import frappe
from payments.utils.ivyliving_methods import cleanup_duplicate_payment_entries

def main():
    """Main function to fix duplicate Payment Entries"""
    print("Starting duplicate Payment Entry cleanup...")
    
    try:
        # Clean up existing duplicates
        cleanup_duplicate_payment_entries()
        
        print("✅ Successfully cleaned up duplicate Payment Entries")
        
    except Exception as e:
        print(f"❌ Failed to fix duplicate Payment Entries: {str(e)}")
        frappe.log_error(f"Failed to fix duplicate Payment Entries: {str(e)}", "Payment Entry Fix Error")

if __name__ == "__main__":
    main() 