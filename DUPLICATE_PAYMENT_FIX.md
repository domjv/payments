# Duplicate Payment Entry Fix

## Problem
The CCAvenue payment integration was creating duplicate Payment Entries when both the normal flow and webhook flow processed the same payment simultaneously. This resulted in two Payment Entries with the same `reference_no` (tracking_id).

## Root Cause
Both the normal flow (`verify_transaction` function) and webhook flow (`order_status_echo`, `reconciliation_status` functions) were calling the same utility function `handle_payment_authorization_payment_request` without proper coordination, leading to race conditions.

## Solution Implemented

### 1. Centralized Payment Processing
- Created `process_ccavenue_payment_safely()` function in `payments/utils/ivyliving_methods.py`
- This function uses database-level checks and transactions to prevent duplicates
- Both normal flow and webhook flow now use this centralized function

### 2. Database-Level Protection
- Added unique constraint on Payment Entry `reference_no` field
- Added cleanup function to remove existing duplicates
- Added error handling for duplicate key violations

### 3. Improved Error Handling
- Better logging for debugging
- Graceful handling of existing duplicates
- Proper status updates even when duplicates are detected

## Files Modified

1. **`payments/utils/ivyliving_methods.py`**
   - Added `process_ccavenue_payment_safely()` function
   - Added `cleanup_duplicate_payment_entries()` function
   - Added `ensure_payment_entry_unique_constraint()` function
   - Added `fix_duplicate_payment_entries()` function

2. **`payments/payment_gateways/doctype/ccavenue_settings/ccavenue_settings.py`**
   - Updated `_create_payment_entry_if_needed()` to use centralized function

3. **`payments/payment_gateways/webhooks/ccavenue.py`**
   - Updated `_process_payment_update()` to use centralized function

4. **`payments/patches/v1_0_0/add_payment_entry_unique_constraint.py`**
   - Added patch to clean up duplicates and add unique constraint

## How to Fix Existing Duplicates

### Option 1: Run the Patch (Recommended)
```bash
bench --site your-site.com migrate
```

### Option 2: Run the Manual Script
```bash
bench --site your-site.com execute fix_duplicate_payments.py
```

### Option 3: Call the Function via API
```python
import frappe
from payments.utils.ivyliving_methods import fix_duplicate_payment_entries

result = fix_duplicate_payment_entries()
print(result)
```

## What the Fix Does

1. **Cleans up existing duplicates**: Keeps the first (oldest) Payment Entry for each tracking_id and deletes the rest
2. **Adds unique constraint**: Prevents future duplicates at the database level
3. **Improves coordination**: Both payment flows now use the same centralized function
4. **Better error handling**: Gracefully handles race conditions and existing duplicates

## Prevention

The fix ensures that:
- Only one Payment Entry is created per tracking_id
- Both normal flow and webhook flow are coordinated
- Database-level constraints prevent duplicates
- Proper logging helps with debugging

## Testing

After applying the fix:
1. Test a new payment to ensure only one Payment Entry is created
2. Check logs to verify proper coordination between flows
3. Verify that existing duplicates are cleaned up
4. Confirm that the unique constraint is in place

## Monitoring

Monitor the logs for:
- `"Payment Entry already exists for tracking_id"`
- `"Payment processed successfully via"`
- `"Duplicate Payment Entries fixed"`

These messages indicate the fix is working correctly. 