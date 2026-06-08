# Razorpay Multi-Merchant – Agent / Skill Guide

> **Last updated:** June 2026  
> **Branch:** `pleasantbiz-payment-gateways`  
> **Scope:** Razorpay multi-merchant integration for Ivy Living / ERPNext Hostel Management

---

## 1. What Changed (vs Upstream Razorpay)

This fork converted Razorpay from single-settings to the same multi-merchant pattern used by CCAvenue and Easebuzz:

| Aspect | Before | After |
|---|---|---|
| Credentials | Single `Razorpay Settings` doc | `Razorpay Merchant` records + Settings fallback |
| Multi-merchant | Not supported | Per-company merchant via `get_merchant_for_company()` |
| External API | `get_order` / `order_payment_success` only | `initiate_payment`, `verify_payment`, `check_payment_status` |
| Payment Charges | Not applied | Applied in `create_order()` before Razorpay API call |
| Capture mode | Scheduler-based (`Authorized` → `Completed`) | Auto-capture (`payment_capture=1`) → immediate `Completed` |
| Ivy Living handlers | Generic `run_method` only | Direct handler calls (Sales Invoice, Payment Request, Customer) |
| Refund webhook | Not implemented | `refund_status()` endpoint |
| Per-hostel gateway | Not supported | `Payment Gateway Config` doctype |

---

## 2. File Map

| File | Role |
|---|---|
| `payments/payment_gateways/doctype/razorpay_merchant/razorpay_merchant.json` | Doctype definition |
| `payments/payment_gateways/doctype/razorpay_merchant/razorpay_merchant.py` | Controller + `get_default_merchant()` |
| `payments/payment_gateways/doctype/razorpay_settings/razorpay_settings.py` | Main controller + all API endpoints |
| `payments/payments/doctype/payment_gateway_config/payment_gateway_config.py` | `get_gateway_for_company()` |
| `payments/overrides/sales_invoice.py` | `handle_payment_authorization_sales_invoice()` – Razorpay branch |
| `payments/utils/ivyliving_methods.py` | Payment Request + Customer handlers – Razorpay branch |
| `payments/patches/v1_0/razorpay_merchant_migration.py` | One-time migration patch |
| `patches.txt` | Registers the migration patch |
| `RAZORPAY_SETUP.md` | Setup guide for admins |
| `RAZORPAY_FRONTEND_INTEGRATION.md` | Frontend developer guide |

---

## 3. Key Classes and Functions

### `RazorpaySettings` (Document)

```python
# Credential resolution
get_merchant_for_company(company=None, merchant_name=None) → RazorpayMerchant
get_credentials(data=None, company=None, merchant_name=None) → frappe._dict
get_razorpay_client(creds) → razorpay.Client

# Payment lifecycle
get_payment_url(**kwargs) → str            # Standard ERPNext path
create_order(**kwargs) → dict              # Creates Razorpay order with auto-capture
authorize_payment() → dict                 # Verifies + calls Ivy Living handlers
verify_signature(body, sig, key) → bool

# Subscription (unchanged)
setup_subscription(settings, **kwargs)
cancel_subscription(subscription_id)
```

### Module-level whitelisted APIs

| Function | Guest? | Purpose |
|---|---|---|
| `initiate_payment(**kwargs)` | ✓ | External frontend – create order, return Checkout.js params |
| `verify_payment(payment_id, order_id, sig, token)` | ✓ | Frontend callback – HMAC verify + authorize |
| `check_payment_status(integration_request_name)` | ✓ | Poll Integration Request status |
| `refund_status()` | ✓ | Razorpay → server refund webhook |
| `order_payment_success(integration_request, params)` | ✓ | Legacy modal callback (razorpay.js) |
| `order_payment_failure(integration_request, params)` | ✓ | Legacy modal failure |
| `get_api_key()` | ✓ | Global API key for razorpay.js |
| `validate_merchant_credentials(merchant_name)` | | Test Connection button |
| `capture_payment()` | | Scheduler – captures legacy Authorized records |

### `get_gateway_for_company(company)` → `(gateway_name, merchant_name)`

Lives in `payments/payments/doctype/payment_gateway_config/payment_gateway_config.py`.  
Returns `("CCAvenue", None)` if no config record exists (backward compat).

---

## 4. Credential Resolution Logic

```python
# Priority 1: explicit merchant_name kwarg
# Priority 2: Razorpay Merchant where company = X
# Priority 3: Razorpay Merchant with is_default = 1
# Priority 4: Global Razorpay Settings (fallback, no throw)
# Special: use_sandbox in site config → sandbox creds
creds = settings.get_credentials(data=ir_data, company="Hostel A", merchant_name=None)
# → frappe._dict with api_key, api_secret, environment, redirect_to, merchant_name
```

---

## 5. Payment Flow (External Frontend)

```
1. initiate_payment(amount, reference_doctype, reference_docname, payer_email, ...)
   → creates Razorpay order (payment_capture=1, notes embedded)
   → creates Integration Request
   → returns {order_id, api_key, amount_paise, payment_token, prefill}

2. Frontend opens Checkout.js modal with order_id + api_key
   User pays → Checkout.js fires payment.success
   → {razorpay_payment_id, razorpay_order_id, razorpay_signature}

3. verify_payment(razorpay_payment_id, razorpay_order_id, razorpay_signature, token)
   → HMAC-SHA256 verify: sha256(order_id + "|" + payment_id, api_secret)
   → restore user session from Integration Request notes.user
   → GET /v1/payments/{id} → status = "captured" → IR status = "Completed"
   → handle_payment_authorization_sales_invoice / _payment_request / _customer
   → create Payment Entry (mode: Razorpay, bank: Razorpay Merchant GL accounts)
   → redirect_to from merchant or global settings + ?integration_id=...

4. check_payment_status(integration_request_name)
   → returns current IR status for polling
```

---

## 6. Sales Invoice Payment Entry GL Accounts

When service = `"Razorpay"`, the `handle_payment_authorization_sales_invoice` function resolves GL accounts as:

```
paid_from = merchant.debtors_account + " - " + company_abbr  # e.g. "Debtors - HKP"
paid_to   = merchant.bank_account   + " - " + company_abbr  # e.g. "Razorpay - HKP"
```

Fallback (no merchant): `Debtors - {abbr}` / `Razorpay - {abbr}` / first Bank account.

---

## 7. Migration Notes

### Running for the first time

```bash
bench --site <site> migrate
# Patch: payments.patches.v1_0.razorpay_merchant_migration
# → Seeds default Razorpay Merchant from Settings
# → Captures lingering Authorized Integration Requests
```

### Backward compatibility

- Existing `order_payment_success` / `razorpay.js` modal path still works
- `get_settings(data)` is an alias for `get_credentials(data=data)`
- Subscriptions are fully unchanged
- Scheduler `capture_payment` still runs (handles legacy Authorized records)

---

## 8. Common Issues

| Issue | Likely cause | Fix |
|---|---|---|
| "No Razorpay Merchant configuration found" | No merchant records and Settings has no api_key | Run migration or create a merchant |
| Signature verification failed | Wrong api_secret on merchant record | Update merchant credentials |
| Payment Entry not created | GL account `Razorpay - {abbr}` doesn't exist | Create account or set `bank_account` on merchant |
| `capture_payment` failing for Authorized records | Pre-migration record with no `razorpay_payment_id` | Run migration patch manually |
| `initiate_payment` returns `success: False` | Missing required param or Razorpay API error | Check `frappe.log_error` in Error Log |

---

## 9. Testing Checklist

- [ ] Create `Razorpay Merchant` with test credentials + `is_default = 1`
- [ ] Click **Test Connection** → should succeed
- [ ] Create `Payment Gateway Config` for a hostel → `preferred_gateway = Razorpay`
- [ ] Call `initiate_payment` → verify `order_id` returned
- [ ] Complete test payment in Checkout.js modal
- [ ] Call `verify_payment` → `status = Completed`
- [ ] Check `Integration Request` → `Completed`
- [ ] Check `Payment Entry` created with mode `Razorpay`
- [ ] Check `Sales Invoice` outstanding amount reduced
- [ ] Trigger refund in Razorpay Dashboard → `refund_status` webhook fires → `Integration Request` updated
