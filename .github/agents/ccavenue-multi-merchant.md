# CCAvenue Multi-Merchant – Agent / Skill Guide

> **Last updated:** June 2026  
> **Scope:** CCAvenue multi-merchant integration for Ivy Living / ERPNext Hostel Management

---

## 1. Architecture Overview

```
Customer (ERPNext) → custom_hostel_name → Company
        │
        ▼
CCAvenue Settings (Single – global fallback creds)
        │
        ▼
CCAvenue Merchant (one record per company/hostel)
        │  merchant_id, access_code, encryption_key
        │  environment (Sandbox | Production)
        │  company, bank_account, debtors_account
        ▼
Merchant Resolution Priority:
  1. explicit custom_merchant_name
  2. Merchant where company = X
  3. is_default = 1
  4. get_default_merchant() → auto-create fallback
  5. Throws
```

---

## 2. File Map

| File | Role |
|---|---|
| `payments/payment_gateways/doctype/ccavenue_settings/ccavenue_settings.py` | Main controller + all API endpoints |
| `payments/payment_gateways/doctype/ccavenue_settings/ccavenue_utils.py` | AES encryption/decryption, `test_connection` |
| `payments/payment_gateways/doctype/ccavenue_merchant/ccavenue_merchant.py` | Merchant record controller |
| `payments/payment_gateways/doctype/ccavenue_merchant/ccavenue_merchant.json` | Merchant doctype definition |
| `payments/templates/pages/ccavenue_checkout.*` | Deprecated web checkout page |
| `payments/public/js/ccavenue_session_handler.js` | Session restore JS (deprecated for API mode) |
| `payments/public/js/ccavenue.js` | Deprecated desk checkout helper |
| `payments/utils/ivyliving_methods.py` | Payment Request + Customer handlers |
| `payments/overrides/sales_invoice.py` | Sales Invoice payment entry handler |

---

## 3. Key Classes and Functions

### `CCAvenueSettings` (Document – Single DocType)

```python
# Credential / merchant resolution
get_merchant_for_company(company=None, merchant_name=None) → CCAvenueMerchant

# Payment lifecycle
get_payment_url(**kwargs) → str          # Standard ERPNext path → /ccavenue_checkout
create_encrypted_request_data(**kwargs) → dict   # AES-encrypt payload for gateway
authorize_payment() → dict               # Decrypt response, update IR, call handlers

# Settings helpers
get_credentials_for_merchant(merchant_name) → dict
```

### Module-level whitelisted APIs

| Function | Guest? | Method | Purpose |
|---|---|---|---|
| `initiate_payment(**kwargs)` | ✓ | POST | External frontend – create encrypted payload, return payment data |
| `check_payment_status(integration_request_name)` | ✓ | GET | Poll Integration Request status |
| `verify_transaction()` | ✓ | POST | Browser return URL – decrypt `encResp`, authorize, redirect |
| `order_status_echo()` | ✓ | POST | S2S backup webhook – skips if already processed |
| `reconciliation_status()` | ✓ | POST | Delayed/UPI reconciliation webhook |
| `refund_status()` | ✓ | POST | Refund status webhook → `on_refund_status_update` |
| `get_api_key()` | ✓ | GET | Returns `access_code` from Settings |
| `restore_user_session()` | ✓ | GET | Restore Frappe session after Guest callback |
| `test_connection(...)` | | POST | Validate credentials (ccavenue_utils.py) |

---

## 4. Encryption / Decryption

CCAvenue uses AES-128-CBC encryption via `ccavenue_utils.py`:

```python
from payments.payment_gateways.doctype.ccavenue_settings.ccavenue_utils import (
    encrypt, decrypt
)

# Outbound: encrypt payment params dict → encrypted_data string
encrypted_data = encrypt(params_string, encryption_key)

# Inbound: decrypt encResp string → plaintext param string
plaintext = decrypt(enc_resp, encryption_key)
```

The **encryption key** comes from the resolved `CCAvenue Merchant` record (or Settings fallback).

---

## 5. Payment Flows

### Standard ERPNext path (web checkout – deprecated for API mode)

```
get_payment_url(**kwargs)
  → create_request_log → Integration Request
  → /ccavenue_checkout?token={ir_name}
  → checkout page builds encrypted form → CCAvenue
  → CCAvenue POST encResp → verify_transaction
  → authorize_payment → on_payment_authorized
```

### External Frontend / Mobile API path

```
initiate_payment(**kwargs)
  → resolve merchant
  → create_request_log → Integration Request
  → create_encrypted_request_data()
  → {payment_url, encrypted_data, access_code, merchant_id, merchant_name,
     api_url, iframe_url, company, payment_token}

Frontend posts encrypted form / opens iframe to CCAvenue

CCAvenue POST encResp → verify_transaction?merchant={name}
  → decrypt encResp with merchant key
  → restore user session from merchant_param1.user
  → authorize_payment()
  → redirect_to + ?integration_id=...

S2S backup: order_status_echo?merchant={name}
  → same decrypt + authorize, duplicate-safe

Reconciliation (UPI delayed): reconciliation_status?merchant={name}
Refund: refund_status?merchant={name}
```

---

## 6. Webhook Endpoints

| Endpoint | URL Pattern | Trigger |
|---|---|---|
| `verify_transaction` | `.../verify_transaction?merchant={name}` | Browser redirect (`redirect_url`) |
| `order_status_echo` | `.../order_status_echo?merchant={name}` | S2S webhook (`notify_url`) |
| `reconciliation_status` | `.../reconciliation_status?merchant={name}` | CCAvenue server push for delayed payments |
| `refund_status` | `.../refund_status?merchant={name}` | CCAvenue refund webhook |

All four endpoints accept a `?merchant={merchant_name}` query parameter to select which merchant's encryption key to use. Without it, falls back to `get_merchant_for_company()` → Settings.

---

## 7. Integration Request Data Structure

```json
{
  "amount": 600.0,
  "currency": "INR",
  "reference_doctype": "Sales Invoice",
  "reference_docname": "SINV-0001",
  "custom_merchant_name": "Hostel-A",
  "company": "Hostel A Pvt Ltd",
  "merchant_param1": "{\"reference_doctype\":\"Sales Invoice\",\"reference_docname\":\"SINV-0001\",\"token\":\"order-id@INT-001\",\"user\":\"admin@example.com\"}"
}
```

After callback:
```json
{
  "order_status": "Success",
  "tracking_id": "TXN123456",
  "bank_ref_no": "BANK789",
  "payment_mode": "Net Banking"
}
```

---

## 8. Sales Invoice GL Account Resolution

```
service = "CCAvenue"
→ merchant_name = data.get("custom_merchant_name")
→ merchant_doc = CCAvenue Merchant by name or company
→ paid_from = merchant_doc.debtors_account + " - " + company_abbr  (e.g. "Debtors - HKP")
→ paid_to   = merchant_doc.bank_account    + " - " + company_abbr  (e.g. "CCAvenue - HKP")
→ reference_no = data.get("tracking_id") or integration_request.name
→ mode_of_payment = "CCAvenue"
```

---

## 9. Important Field Notes

- `enviroment` (typo – single 'n') is the fieldname in `CCAvenue Merchant` JSON. Access as `merchant_doc.enviroment`.
- `merchant_param1` carries JSON with `token = "{order_id}@{integration_request_name}"`. Parse the second part after `@` to get the Integration Request name.
- Duplicate prevention: `order_status_echo` and `reconciliation_status` check `integration_request.status` before processing.

---

## 10. Common Issues

| Issue | Cause | Fix |
|---|---|---|
| "Decryption failed" | Wrong encryption_key on merchant record | Verify against CCAvenue dashboard |
| "Merchant not found" | No merchant for company, no default | Create merchant record with `is_default=1` |
| Payment Entry not created | GL account `CCAvenue - {abbr}` missing | Create account or set `bank_account` on merchant |
| `verify_transaction` 500 | `merchant_param1` JSON malformed | Check `create_encrypted_request_data()` payload |
| Session not restored | `user` missing from `merchant_param1` | Ensure `frappe.session.user` is set before `initiate_payment` |
| Webhook duplicate | Both `verify_transaction` and `order_status_echo` fire | Normal – duplicate check in `order_status_echo` handles it |

---

## 11. Testing Checklist

- [ ] Create `CCAvenue Merchant` with sandbox credentials, `environment = Sandbox`, `is_default = 1`
- [ ] Create `Payment Gateway Config` → `preferred_gateway = CCAvenue`
- [ ] Call `initiate_payment` → verify `encrypted_data`, `access_code`, `merchant_id` returned
- [ ] Post encrypted form to CCAvenue sandbox
- [ ] CCAvenue calls `verify_transaction` → `Integration Request` → `Completed`
- [ ] `Payment Entry` created with mode `CCAvenue`, correct GL accounts
- [ ] Trigger S2S from CCAvenue dashboard → `order_status_echo` duplicate-safe
- [ ] Trigger refund → `refund_status` fires → `on_refund_status_update` called
