# Easebuzz Split Payments – Agent / Skill Guide

> **Last updated:** 2025-04-01  
> **Branch:** `copilot/add-easebuzz-split-payments`  
> **Scope:** Easebuzz Easy Split integration inside the `payments` Frappe app

---

## 1. What is Easebuzz Easy Split?

Easebuzz Easy Split allows a single payment transaction to be automatically
split across multiple sub-merchants (labels).  A primary merchant receives a
payment and Easebuzz internally distributes the funds to the configured
sub-merchants.

Official product page: <https://easebuzz.in/slices/>

---

## 2. How It Works (high level)

```
Payer ──► Easebuzz Payment Page ──► Easebuzz settles funds
                                        │
                              ┌─────────┴──────────┐
                              │  split_payments     │
                              │  [{label, amount},  │
                              │   {label, amount}]  │
                              └─────────┬──────────┘
                            Sub-merchant A   Sub-merchant B
```

1. The primary merchant calls the **Initiate Payment API** and includes a
   `split_payments` JSON array in the POST body.
2. Each element specifies a **label** (sub-merchant identifier provided by
   Easebuzz) and a **split_amount** (in INR, as a string).
3. Easebuzz processes the payment and distributes the amounts accordingly.
4. The hash is computed **after** `split_payments` is added to the data dict so
   the field is covered by the signature.

---

## 3. Relevant Files

| File | Purpose |
|------|---------|
| `payments/payment_gateways/doctype/easebuzz_split_payment/` | New child DocType – stores per-row split rules |
| `payments/payment_gateways/doctype/easebuzz_merchant/easebuzz_merchant.json` | Updated to include `split_payments` child table |
| `payments/payment_gateways/doctype/easebuzz_settings/easebuzz_utils.py` | `compute_split_payments()`, updated `initiate_payment_api()`, corrected `verify_response_hash()` |
| `payments/payment_gateways/doctype/easebuzz_settings/easebuzz_settings.py` | `create_payment_request_data()` now returns `split_payments`; `initiate_payment()` passes it to the API |
| `payments/templates/pages/easebuzz_checkout.py` | Passes `split_payments` from `request_data` to `initiate_payment_api()` |

---

## 4. DocType: Easebuzz Split Payment (child table)

**Parent:** `Easebuzz Merchant`  
**Table field:** `split_payments`

| Field | Type | Description |
|-------|------|-------------|
| `label` | Data (required) | Sub-merchant label from Easebuzz Easy Split dashboard |
| `split_type` | Select | `Percentage` or `Fixed` |
| `split_value` | Float | % of total amount, or fixed INR amount |

### Example merchant configuration

```
Merchant: IvyLiving Campus A
Split Payment Rules:
  Row 1: label=CAMPUS_A_MGMT  split_type=Percentage  split_value=80
  Row 2: label=CAMPUS_A_OPS   split_type=Percentage  split_value=20
```

For a ₹1 000 transaction this sends:
```json
[
  {"label": "CAMPUS_A_MGMT", "split_amount": "800.0"},
  {"label": "CAMPUS_A_OPS",  "split_amount": "200.0"}
]
```

---

## 5. Key Function: `compute_split_payments`

```python
from payments.payment_gateways.doctype.easebuzz_settings.easebuzz_utils import compute_split_payments

split_list = compute_split_payments(merchant_doc, total_amount)
# Returns None if no split rules are configured, or a list of dicts:
# [{"label": "...", "split_amount": "..."}]
```

Rules:
- `Percentage` rows → `round(total_amount * split_value / 100, 2)`
- `Fixed` rows → value used directly
- Rows with a blank `label` are skipped
- Returns `None` (not an empty list) when no rules exist, so callers can check
  truthiness simply with `if split_list:`

---

## 6. Key Function: `initiate_payment_api` (updated signature)

```python
initiate_payment_api(
    payment_data,   # dict
    merchant_key,   # str
    salt,           # str
    environment,    # 'Test' | 'Production'
    split_payments=None,  # list | None  ← NEW
)
```

When `split_payments` is provided, it is JSON-serialised and added to
`payment_data['split_payments']` **before** the hash is generated so it is
covered by the SHA-512 signature.

---

## 7. Per-Request Override

Callers of `initiate_payment` can supply an explicit `split_payments` list in
`kwargs` to override the merchant-level configuration for a single transaction:

```python
# Via the whitelisted API endpoint
frappe.call(
    "payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.initiate_payment",
    amount=1000,
    payer_email="customer@example.com",
    payer_name="CUST-001",
    reference_doctype="Sales Invoice",
    reference_docname="SINV-0001",
    split_payments=[
        {"label": "LABEL_A", "split_amount": "800.00"},
        {"label": "LABEL_B", "split_amount": "200.00"},
    ],
)
```

---

## 8. Response Hash Verification

The reverse hash sequence (per Easebuzz docs) is:

```
salt|status|udf10|udf9|udf8|udf7|udf6|udf5|udf4|udf3|udf2|udf1|email|firstname|productinfo|amount|txnid|key
```

The `verify_response_hash()` function in `easebuzz_utils.py` now explicitly
names every field (including udf6–udf10) so the sequence is clear and
maintainable.

---

## 9. Testing on UAT

1. Configure an Easebuzz Merchant with:
   - `environment = Test`
   - Credentials from the Easebuzz UAT dashboard
   - One or more split payment rows with labels provided by the Easebuzz team
2. Initiate a payment via the API or checkout page.
3. Easebuzz UAT payment page URL: `https://testpay.easebuzz.in/pay/<access-key>`
4. After payment, verify the webhook/callback and check that
   `verify_response_hash` returns `True`.

---

## 10. Keeping This Guide Updated

Whenever a change is made to the Easebuzz split payment flow, update:

1. This file (`.github/agents/easebuzz-split-payments.md`)
2. `EASEBUZZ_SPLIT_PAYMENTS_IMPLEMENTATION.md` (detailed rationale doc)
3. The relevant docstrings in `easebuzz_utils.py` and `easebuzz_settings.py`
