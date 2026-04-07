# Easebuzz Easy Split – Implementation Details

> **Branch:** `copilot/add-easebuzz-split-payments`  
> **Date:** 2025-04-01  
> **Scope:** Easebuzz Easy Split payment routing inside the `payments` Frappe app

---

## Table of Contents

1. [Background and Goal](#1-background-and-goal)
2. [How Easebuzz Easy Split Works](#2-how-easebuzz-easy-split-works)
3. [What Was Changed and Why](#3-what-was-changed-and-why)
   - 3.1 [New DocType – Easebuzz Split Payment (child table)](#31-new-doctype--easebuzz-split-payment-child-table)
   - 3.2 [Updated Easebuzz Merchant DocType](#32-updated-easebuzz-merchant-doctype)
   - 3.3 [compute_split_payments helper](#33-compute_split_payments-helper)
   - 3.4 [Updated initiate_payment_api](#34-updated-initiate_payment_api)
   - 3.5 [Updated verify_response_hash](#35-updated-verify_response_hash)
   - 3.6 [Updated create_payment_request_data](#36-updated-create_payment_request_data)
   - 3.7 [Updated initiate_payment endpoint](#37-updated-initiate_payment-endpoint)
   - 3.8 [Updated easebuzz_checkout.py](#38-updated-easebuzz_checkoutpy)
4. [Data Flow Diagram](#4-data-flow-diagram)
5. [Hash Computation with split_payments](#5-hash-computation-with-split_payments)
6. [Configuration Guide (for Admins)](#6-configuration-guide-for-admins)
7. [API Usage (for Developers)](#7-api-usage-for-developers)
8. [UAT / Testing Instructions](#8-uat--testing-instructions)
9. [Webhook and Response Verification](#9-webhook-and-response-verification)
10. [Design Decisions and Trade-offs](#10-design-decisions-and-trade-offs)

---

## 1. Background and Goal

The goal of this implementation is to integrate **Easebuzz Easy Split**
(https://easebuzz.in/slices/) into the existing Easebuzz payment gateway
implementation inside this Frappe `payments` app.

Easy Split allows a single payer transaction to be automatically routed to
multiple sub-merchant accounts.  Each sub-merchant is identified by a **label**
assigned by the Easebuzz dashboard.  The split amounts are passed as part of
the Initiate Payment API request.

Relevant Easebuzz documentation:
- Initiate Payment API: https://docs.easebuzz.in/docs/payment-gateway/8ec545c331e6f-initiate-payment-api
- Webhooks: https://docs.easebuzz.in/docs/payment-gateway/587zy3v064so6-what-are-webhooks
- Transaction Status v2.1: https://docs.easebuzz.in/docs/payment-gateway/6il9ej80xoydr-transaction-api-v2-1

---

## 2. How Easebuzz Easy Split Works

1. The merchant (or integrating application) calls the **Initiate Payment API**
   at `https://testpay.easebuzz.in/payment/initiateLink` (UAT) or
   `https://pay.easebuzz.in/payment/initiateLink` (Production) with the usual
   payment parameters **plus** a `split_payments` field.

2. `split_payments` is a **JSON-serialised array** of objects:

   ```json
   [
     {"label": "SUB_MERCHANT_LABEL_1", "split_amount": "800.00"},
     {"label": "SUB_MERCHANT_LABEL_2", "split_amount": "200.00"}
   ]
   ```

3. Easebuzz returns an `access_key` on success.  The payer is redirected to:
   - UAT: `https://testpay.easebuzz.in/pay/<access_key>`
   - Production: `https://pay.easebuzz.in/pay/<access_key>`

4. After payment, Easebuzz posts back to the `surl` / `furl` (and/or the
   configured webhook URL) with the result, including a response hash that must
   be verified.

### Hash rules

**Request hash** (SHA-512):
```
key|txnid|amount|productinfo|firstname|email|udf1|udf2|udf3|udf4|udf5||||||salt
```

**Response/reverse hash** (SHA-512):
```
salt|status|udf10|udf9|udf8|udf7|udf6|udf5|udf4|udf3|udf2|udf1|email|firstname|productinfo|amount|txnid|key
```

> **Important:** `split_payments` is NOT part of the hash string.  It is an
> additional POST parameter that rides alongside the standard signed fields.
> However, in our implementation `split_payments` is added to `payment_data`
> **before** `generate_hash()` is called.  Because the hash function reads only
> the specific fields listed above (by name), the presence of the extra key
> does not alter the computed hash – the behaviour is identical to adding it
> after hashing.  We chose to add it before for clarity and to reflect that
> `split_payments` will be present in the final POST body.

---

## 3. What Was Changed and Why

### 3.1 New DocType – Easebuzz Split Payment (child table)

**File:** `payments/payment_gateways/doctype/easebuzz_split_payment/`

A new Frappe child DocType was created to store split payment configuration rows
against an Easebuzz Merchant.

| Field | Type | Notes |
|-------|------|-------|
| `label` | Data (reqd) | Sub-merchant label from Easebuzz Easy Split |
| `split_type` | Select | `Percentage` or `Fixed` |
| `split_value` | Float | % of transaction amount, or fixed INR value |

**Why a child table?**  
Different merchant accounts may have different split rules.  Storing them in a
child table on the merchant document keeps the data tightly coupled to its
parent, supports multiple rows per merchant, and leverages standard Frappe
CRUD/UI for free.

### 3.2 Updated Easebuzz Merchant DocType

**File:** `payments/payment_gateways/doctype/easebuzz_merchant/easebuzz_merchant.json`

Added:
- Section break `split_payments_section` (collapsible)
- Table field `split_payments` pointing to `Easebuzz Split Payment`

This means every `Easebuzz Merchant` document now has a child table where
administrators configure how payments are split.  Leave it empty to disable
split payments for that merchant.

### 3.3 `compute_split_payments` helper

**File:** `payments/payment_gateways/doctype/easebuzz_settings/easebuzz_utils.py`

```python
def compute_split_payments(merchant_doc, total_amount) -> list | None
```

This function reads the `split_payments` child table rows from a merchant
document and converts them to the Easebuzz-expected format:

```python
[{"label": "...", "split_amount": "..."}]
```

Logic:
- `Percentage` rows → `round(total_amount * split_value / 100, 2)`
- `Fixed` rows → `round(split_value, 2)` used directly as the split amount
- Rows with a blank `label` are skipped silently
- Returns `None` (not `[]`) when there are no rows, allowing callers to test
  with `if split_payments:`

**Why a standalone helper?**  
It can be unit-tested independently and reused wherever split computation is
needed (checkout page, API endpoint, future mobile SDK endpoints).

### 3.4 Updated `initiate_payment_api`

**File:** `payments/payment_gateways/doctype/easebuzz_settings/easebuzz_utils.py`

Added `split_payments=None` parameter.  When provided, the list is
JSON-serialised and stored in `payment_data['split_payments']` **before** the
SHA-512 hash is generated.

```python
if split_payments:
    payment_data['split_payments'] = json.dumps(split_payments)

payment_data['hash'] = generate_hash(payment_data, salt)
```

This ensures the final POST body sent to Easebuzz contains both `split_payments`
and the correct `hash`.

### 3.5 Updated `verify_response_hash`

**File:** `payments/payment_gateways/doctype/easebuzz_settings/easebuzz_utils.py`

The old implementation had a comment referring to 5 anonymous empty fields.
These are now explicitly named `udf6` through `udf10` to match the documented
reverse hash sequence exactly:

```
salt|status|udf10|udf9|udf8|udf7|udf6|udf5|udf4|udf3|udf2|udf1|email|firstname|productinfo|amount|txnid|key
```

This change is backwards-compatible because udf6–udf10 are never set in our
transactions (they default to `''` from `response_data.get('udf10', '')`), so
the computed hash remains the same.  The benefit is that the code now correctly
handles responses where Easebuzz does populate those fields.

### 3.6 Updated `create_payment_request_data`

**File:** `payments/payment_gateways/doctype/easebuzz_settings/easebuzz_settings.py`

After building `payment_data`, the method now:

1. Calls `compute_split_payments(merchant_doc, final_amount)` to derive the
   split list from the merchant's configured rules.
2. Allows a per-request override via `kwargs.get('split_payments')` (takes
   precedence over the merchant-level config).
3. Returns `split_payments` in the result dict alongside `payment_data`,
   `merchant_key`, `salt`, etc.

```python
split_payments = kwargs.get('split_payments') or compute_split_payments(merchant_doc, final_amount)
return {
    ...
    "split_payments": split_payments,
}
```

**Priority order:**  
`kwargs['split_payments']` (per-request) → merchant config rows → `None` (no split)

### 3.7 Updated `initiate_payment` endpoint

**File:** `payments/payment_gateways/doctype/easebuzz_settings/easebuzz_settings.py`

The `initiate_payment_api(...)` call now passes `split_payments` from the
result of `create_payment_request_data`:

```python
result = initiate_payment_api(
    payment_request_data['payment_data'],
    payment_request_data['merchant_key'],
    payment_request_data['salt'],
    payment_request_data['environment'],
    split_payments=payment_request_data.get('split_payments'),
)
```

### 3.8 Updated `easebuzz_checkout.py`

**File:** `payments/templates/pages/easebuzz_checkout.py`

The same pattern as the endpoint: the `initiate_payment_api` call now receives
`split_payments=request_data.get("split_payments")`.

---

## 4. Data Flow Diagram

```
Admin configures Easebuzz Merchant
  └─► split_payments child table (label + split_type + split_value)

User initiates payment
  │
  ├─► initiate_payment() endpoint  (or easebuzz_checkout.py for iFrame flow)
  │       │
  │       ├─► create_payment_request_data()
  │       │       ├─► get merchant doc
  │       │       ├─► build payment_data dict
  │       │       └─► compute_split_payments(merchant_doc, final_amount)
  │       │               └─► [{label, split_amount}, ...]  OR  None
  │       │
  │       └─► initiate_payment_api(payment_data, key, salt, env, split_payments)
  │               ├─► payment_data['split_payments'] = json.dumps(split_payments)
  │               ├─► payment_data['hash'] = generate_hash(payment_data, salt)
  │               └─► POST to https://testpay.easebuzz.in/payment/initiateLink
  │                       └─► {"status": 1, "data": "<access_key>"}
  │
  └─► Return payment URL: https://testpay.easebuzz.in/pay/<access_key>

User pays on Easebuzz page
  └─► POST to surl/furl  →  verify_transaction()
          ├─► verify_response_hash(response_data, salt)
          │       (uses udf6–udf10 explicitly)
          └─► authorize_payment() → on_payment_authorized
```

---

## 5. Hash Computation with `split_payments`

**Request hash sequence** (unchanged):
```
key|txnid|amount|productinfo|firstname|email|udf1|udf2|udf3|udf4|udf5||||||salt
```

`split_payments` is NOT in this sequence.  The existing `generate_hash()`
function reads only the fields listed above, so adding `split_payments` to the
`payment_data` dict before calling `generate_hash()` has no effect on the
computed hash value.  The POST body sent to Easebuzz then contains both the
`hash` and `split_payments` fields, which is what the API expects.

---

## 6. Configuration Guide (for Admins)

1. Navigate to **Payment Gateways → Easebuzz Merchant** in ERPNext.
2. Open the merchant you want to configure for split payments.
3. Expand the **Easy Split Payments** section.
4. Add one row per sub-merchant:
   - **Label**: The label provided by the Easebuzz team for the sub-merchant
     (e.g. `CAMPUS_A_OWNER`).
   - **Split Type**: `Percentage` (most common) or `Fixed`.
   - **Split Value**: e.g. `80` for 80 %, or `500` for ₹500.
5. Save the document.
6. Test with a small amount in the UAT environment before going live.

> **Leave the table empty** to disable split payments for that merchant.  The
> payment will proceed as a normal single-destination transaction.

---

## 7. API Usage (for Developers)

### Merchant-level split (automatic)

Configure the split rules on the merchant document (see §6).  All payments
through that merchant will automatically use the configured split.

### Per-request override

Pass a `split_payments` list when calling the `initiate_payment` endpoint:

```python
frappe.call(
    "payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.initiate_payment",
    amount=1000,
    currency="INR",
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

The per-request value takes precedence over the merchant configuration.

---

## 8. UAT / Testing Instructions

### Prerequisites

- Easebuzz UAT (test) credentials: merchant key, salt, and sub-merchant labels
  provided by the Easebuzz technical team.
- ERPNext / Frappe bench with the `payments` app installed (after `bench migrate`
  to create the new DocTypes).

### Steps

1. Create an **Easebuzz Merchant** with:
   - Environment: `Test`
   - Merchant Key / Salt: UAT credentials
   - Split payment rows: labels from Easebuzz UAT
2. Initiate a payment (via API or UI) for a small test amount (e.g. ₹10).
3. You will receive a `payment_url` like:
   `https://testpay.easebuzz.in/pay/<access_key>`
4. Open the URL in a browser and complete a test payment using Easebuzz's
   sandbox card/UPI details.
5. After payment, the `surl` callback fires.  Verify:
   - The Integration Request status changes to `Completed`.
   - `verify_response_hash` returns `True` (no "Hash verification failed" in
     the error log).
   - The split amounts appear in the Easebuzz UAT dashboard for each
     sub-merchant.

---

## 9. Webhook and Response Verification

The `verify_response_hash` function implements the documented reverse hash
sequence:

```
salt|status|udf10|udf9|udf8|udf7|udf6|udf5|udf4|udf3|udf2|udf1|email|firstname|productinfo|amount|txnid|key
```

Steps performed automatically:
1. Build the hash string using exact values from the Easebuzz response.
2. SHA-512 encode the string.
3. Compare with the `hash` field in the response.
4. Return `True` only if they match.

If verification fails, an error is logged (`"Easebuzz Hash Verification Error"`)
but the payment flow is not blocked (logged-only, not thrown) to avoid locking
out legitimate payments in edge cases.  The log can be reviewed in the Frappe
Error Log.

---

## 10. Design Decisions and Trade-offs

| Decision | Reason |
|----------|--------|
| Child table on Easebuzz Merchant (not a separate DocType) | Keeps split rules coupled to the merchant; standard Frappe UI; no extra navigation |
| `split_payments=None` default in `initiate_payment_api` | Fully backwards-compatible – existing call sites work without modification |
| JSON string in the POST body (`json.dumps(...)`) | Easebuzz API expects a JSON-serialised string, not a nested form field |
| `split_payments` added before `generate_hash()` | Explicit ordering; the hash function only reads named fields so there is no risk of hash mismatch |
| Per-request override (`kwargs['split_payments']`) takes precedence | Enables ad-hoc splits for specific invoices without changing merchant config |
| `Fixed` split type | Useful when sub-merchants receive a fixed fee regardless of invoice value |
| `Percentage` split type | Most common; easy to reason about; survives amount changes |
| No validation that split amounts sum to transaction total | Easebuzz handles this server-side; adding client-side validation would require exact floating-point matching, which is fragile |
