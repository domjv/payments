# Easebuzz Multi-Merchant – Agent / Skill Guide

> **Last updated:** June 2026  
> **Scope:** Easebuzz multi-merchant integration for Ivy Living / ERPNext Hostel Management

---

## 1. Architecture Overview

```
Customer (ERPNext) → custom_hostel_name → Company
        │
        ▼
Easebuzz Settings (Single – global fallback creds + redirect_to)
        │
        ▼
Easebuzz Merchant (one per company/hostel)
        │  merchant_key, salt (Password)
        │  environment (Test | Production)
        │  company, bank_account, debtors_account
        │  split_payments → Easebuzz Split Payment (child table)
        ▼
Merchant Resolution:
  1. explicit merchant_name arg
  2. Merchant where company = X
  3. is_default = 1
  4. get_default_merchant() helper
  5. Throws
```

---

## 2. File Map

| File | Role |
|---|---|
| `payments/payment_gateways/doctype/easebuzz_settings/easebuzz_settings.py` | Main controller + all API endpoints |
| `payments/payment_gateways/doctype/easebuzz_settings/easebuzz_utils.py` | Hash generation (`generate_hash`/`verify_response_hash`), `initiate_payment_api`, `transaction_api`, `refund_api`, `compute_split_payments` |
| `payments/payment_gateways/doctype/easebuzz_merchant/easebuzz_merchant.py` | Merchant record controller |
| `payments/payment_gateways/doctype/easebuzz_merchant/easebuzz_merchant.json` | Merchant doctype |
| `payments/payment_gateways/doctype/easebuzz_split_payment/` | Split Payment child table |
| `payments/templates/pages/easebuzz_checkout.*` | Simple checkout page (redirect to Easebuzz hosted URL) |
| `payments/utils/ivyliving_methods.py` | Payment Request + Customer handlers |
| `payments/overrides/sales_invoice.py` | Sales Invoice payment entry handler |

---

## 3. Key Classes and Functions

### `EasebuzzSettings` (Document – Single DocType)

```python
get_merchant_for_company(company=None, merchant_name=None) → EasebuzzMerchant
get_payment_url(**kwargs) → str                     # → /easebuzz_checkout?token=...
create_payment_request_data(ir_name, **kwargs) → dict  # Full payload + split_payments
get_api_url(environment=None) → str                 # Test/Production base URL
authorize_payment() → dict                          # Update IR, call handlers, redirect
```

### Module-level whitelisted APIs

| Function | Guest? | Method | Purpose |
|---|---|---|---|
| `initiate_payment(**kwargs)` | ✓ | POST | Create payment link via Easebuzz API, return URL |
| `check_payment_status(integration_request_name)` | ✓ | GET | Poll Integration Request status |
| `verify_transaction(return_json=False)` | ✓ | POST | Browser return URL + optional JSON mode |
| `webhook_callback()` | ✓ | POST | S2S JSON webhook – duplicate-safe |
| `refund_status()` | ✓ | POST | Refund webhook → `on_refund_status_update` |

---

## 4. Hash Algorithm

Easebuzz uses **SHA-512** for request signing and response verification.

### Outbound hash (request)

```python
from payments.payment_gateways.doctype.easebuzz_settings.easebuzz_utils import generate_hash

# Hash = SHA512(key|txnid|amount|productinfo|firstname|email|udf1|udf2|udf3|udf4|udf5||||||salt)
hash_value = generate_hash(payment_data, merchant_key, merchant_salt)
```

### Inbound hash (response)

```python
from payments.payment_gateways.doctype.easebuzz_settings.easebuzz_utils import verify_response_hash

# Reverse hash: SHA512(salt|status||||||udf5|udf4|udf3|udf2|udf1|email|firstname|productinfo|amount|txnid|key)
is_valid = verify_response_hash(response_data, merchant_salt)
```

---

## 5. UDF Field Mapping

Set during `create_payment_request_data()`, parsed in `_merchant_data_from_response()`:

| UDF Field | Outbound value | Parsed as (callback) |
|---|---|---|
| `udf1` | `reference_doctype` | `reference_doctype` |
| `udf2` | `reference_docname` | `reference_docname` |
| `udf3` | `token` (= Integration Request name) | `token` |
| `udf4` | `frappe.session.user` or `"Guest"` | `user` |
| `udf5` | `merchant_doc.name` | `merchant_name` |

**Legacy format:** single `udf1` as JSON `{...}` or pipe-separated `key=value` pairs. `_merchant_data_from_response()` handles both.

**Sanitization:** UDF values allow `[a-zA-Z.0-9/\\,\s_#@\-=+&]` up to 300 chars. `_udf_sanitize()` replaces illegal chars with `_`.

---

## 6. Split Payments (Easy Split)

Configure split payment rules on `Easebuzz Merchant → split_payments` child table:

| Field | Description |
|---|---|
| `label` | Easebuzz Easy Split sub-merchant label |
| `split_percent` | Percentage of payment amount to route to this sub-merchant |

`compute_split_payments(merchant_doc, final_amount)` → `[{label, amount}, ...]`

The hash is computed **after** `split_payments` is added to the POST body.

---

## 7. Payment Flows

### External Frontend / Mobile API path

```
initiate_payment(**kwargs)
  → resolve merchant → create_payment_request_data()
  → initiate_payment_api() → POST to Easebuzz /payment/initiateLink
  → {payment_token, payment_url, txnid, merchant_name, company}

Frontend redirects browser / opens iframe to payment_url

Easebuzz POST to surl/furl → verify_transaction?merchant={name}
  → verify SHA-512 hash
  → restore user session from udf4
  → authorize_payment()
  → redirect_to + ?integration_id=...

S2S JSON webhook → webhook_callback?merchant={name}
  → duplicate-safe (checks IR status)
  → returns JSON

Refund → refund_status?merchant={name}
```

### Webhook URL patterns

```
surl / furl = {site}/api/method/...easebuzz_settings.verify_transaction?merchant={name}
webhook     = {site}/api/method/...easebuzz_settings.webhook_callback?merchant={name}
refund      = {site}/api/method/...easebuzz_settings.refund_status?merchant={name}
```

---

## 8. Integration Request Data Structure

After `initiate_payment`:
```json
{
  "amount": 600.0,
  "currency": "INR",
  "reference_doctype": "Sales Invoice",
  "reference_docname": "SINV-0001",
  "custom_merchant_name": "Hostel-A",
  "company": "Hostel A Pvt Ltd",
  "order_id": "INT-00123"
}
```

After callback:
```json
{
  "status": "success",
  "txnid": "INT-00123",
  "easepayid": "EASE123456",
  "bank_ref_num": "BANK789",
  "mode": "NB",
  "error_Message": ""
}
```

---

## 9. Sales Invoice GL Account Resolution

```
service = "Easebuzz"
→ merchant_name = data.get("custom_merchant_name")
→ merchant_doc = Easebuzz Merchant by name or company
→ paid_from = merchant_doc.debtors_account + " - " + company_abbr
→ paid_to   = merchant_doc.bank_account    + " - " + company_abbr
→ reference_no = data.get("easepayid") or data.get("txnid")
→ mode_of_payment = "Easebuzz"
```

---

## 10. Credential Resolution

```python
# In create_payment_request_data():
global_key  = settings.merchant_key or ""
global_salt = settings.get_password("salt") or ""
global_env  = settings.environment or "Test"

merchant_key  = merchant_doc.merchant_key or ""
merchant_salt = merchant_doc.get_password("salt") or ""

selected_key  = merchant_key  or global_key   # merchant preferred
selected_salt = merchant_salt or global_salt
selected_env  = merchant_doc.environment or global_env
```

---

## 11. Common Issues

| Issue | Cause | Fix |
|---|---|---|
| Hash mismatch in `verify_transaction` | Wrong salt on merchant record | Verify salt matches Easebuzz dashboard |
| `initiate_payment` returns "success": false | Easebuzz API rejected the request | Check `initiate_payment_api()` error in Error Log |
| Payment Entry not created | GL account `Easebuzz - {abbr}` missing | Create account or set `bank_account` on merchant |
| Split payment hash invalid | `split_payments` added after hash calculation | Must use `compute_split_payments()` before hash |
| UDF sanitization drops chars | Special chars in docname | `_udf_sanitize()` replaces with `_` – check parsed values |
| `webhook_callback` ignoring duplicate | Already Completed | Expected – duplicate-safe guard working correctly |

---

## 12. Testing Checklist

- [ ] Create `Easebuzz Merchant` with test key/salt, `environment = Test`, `is_default = 1`
- [ ] Test Connection from merchant form
- [ ] Call `initiate_payment` → verify `payment_url` returned
- [ ] Complete test payment on Easebuzz test page
- [ ] `verify_transaction` or `webhook_callback` fires → `Integration Request` → `Completed`
- [ ] `Payment Entry` created with mode `Easebuzz`, correct GL accounts
- [ ] Test split payments: configure `split_payments` on merchant, verify Easebuzz splits funds
- [ ] Trigger refund → `refund_status` fires → `on_refund_status_update` called
