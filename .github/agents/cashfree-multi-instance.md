# Cashfree Multi-Instance – Agent / Skill Guide

> **Last updated:** June 2026  
> **Scope:** Cashfree multi-instance integration for Ivy Living / ERPNext Hostel Management

---

## 1. Architecture Overview

Cashfree uses a **different** pattern from CCAvenue/Easebuzz/Razorpay:
- Multiple `Cashfree Settings` **records** (not a Single doctype) — one per company/hostel
- No separate "Merchant" doctype — the Settings record itself is the merchant
- Each record registers its own `Payment Gateway` entry: `Cashfree-{gateway_name}`

```
Company/Hostel
        │
        ▼
Cashfree Settings (many records)
        │  gateway_name (unique), company, is_default
        │  environment (Sandbox | Production)
        │  client_id, client_secret (Password)
        │  webhook_url (auto-generated), redirect_url
        ▼
Payment Gateway: "Cashfree-{gateway_name}"
        │
        ▼
Cashfree API (https://api.cashfree.com / sandbox.cashfree.com)
```

### Resolution Priority

`CashfreeSettings.get_cashfree_settings_by_company(company=None)`:
1. Record where `company` matches
2. Record with `is_default = 1`
3. First available record
4. Throws `frappe.ValidationError`

---

## 2. File Map

| File | Role |
|---|---|
| `payments/payment_gateways/doctype/cashfree_settings/cashfree_settings.py` | Main controller, webhooks, whitelisted APIs |
| `payments/payment_gateways/doctype/cashfree_settings/cashfree_client.py` | REST client: `create_order`, `fetch_order`, `create_payment_link`, `check_credentials` |
| `payments/templates/pages/cashfree_checkout.py` | Checkout page + `make_payment` whitelisted function |
| `payments/payment_gateways/doctype/cashfree_settings/README.md` | Detailed setup and API reference |

---

## 3. Key Classes and Functions

### `CashfreeSettings` (Document – **non-single**, one record per company)

```python
# Class methods
get_cashfree_settings_by_company(company=None) → CashfreeSettings  # classmethod
get_payment_url(**kwargs) → str         # Standard ERPNext path → /cashfree_checkout
create_order(**kwargs) → dict           # Cashfree order via cashfree_client.create_order()
authorize_payment(order_data) → dict    # Update IR, call on_payment_authorized
```

### Module-level whitelisted APIs

| Function | Guest? | Method | Purpose |
|---|---|---|---|
| `test_cashfree_connection(settings_name)` | No | POST | Validate credentials for a settings record |
| `create_test_payment_link(settings_name, amount, customer_email, customer_name, customer_phone, description)` | No | POST | Create a test payment link |
| `cashfree_webhook()` | Yes | POST | Receive Cashfree webhook events |

### Checkout Page API (`cashfree_checkout.py`)

| Function | Guest? | Returns |
|---|---|---|
| `make_payment(order_id, payment_session_id, reference_doctype, reference_docname, token)` | Yes | `{redirect_to, status}` |

---

## 4. Payment Flow

```
get_payment_url(**kwargs)
  → get_cashfree_settings_by_company(company)
  → create_order() via cashfree_client
  → create_request_log → Integration Request
  → /cashfree_checkout?token={ir_name}&order_id={order_id}

Cashfree checkout page:
  → loads Cashfree JS SDK with payment_session_id
  → user pays in-page

Cashfree SDK success → make_payment(order_id, payment_session_id, ...)
  → fetch_order() → status = PAID
  → authorize_payment()
  → on_payment_authorized → redirect_url

Cashfree webhook (async) → cashfree_webhook()
  → verify X-Webhook-Signature + X-Webhook-Timestamp
  → PAYMENT_SUCCESS_WEBHOOK → IR status = Completed
  → PAYMENT_FAILED_WEBHOOK → IR status = Failed
```

---

## 5. Webhook

### Webhook URL per record

Auto-generated on save:
```
{site}/api/method/payments.payment_gateways.doctype.cashfree_settings.cashfree_settings.cashfree_webhook
```

### Webhook signature verification

```
X-Webhook-Signature  header → HMAC-SHA256 of payload using client_secret
X-Webhook-Timestamp  header → request timestamp
```

### Handled events

| Event type | Action |
|---|---|
| `PAYMENT_SUCCESS_WEBHOOK` (`order_status = PAID`) | IR → `Completed` → `on_payment_authorized` |
| `PAYMENT_FAILED_WEBHOOK` | IR → `Failed` |

### Webhook resolution

1. Extract `order_id` from webhook payload
2. Find Integration Request by `order_id`
3. Read `company` from Integration Request data
4. `get_cashfree_settings_by_company(company)` → correct client_secret for verification

---

## 6. Integration Request Data Structure

```json
{
  "amount": 600.0,
  "currency": "INR",
  "reference_doctype": "Sales Invoice",
  "reference_docname": "SINV-0001",
  "company": "Hostel A Pvt Ltd",
  "cashfree_order_id": "CF-ORDER-001",
  "payment_session_id": "session_xxx"
}
```

---

## 7. Sandbox vs Production

| Setting | Sandbox | Production |
|---|---|---|
| `environment` field | `Sandbox` | `Production` |
| API base URL | `https://sandbox.cashfree.com/pg` | `https://api.cashfree.com/pg` |
| JS SDK | `sandbox.cashfree.com/v3` | `api.cashfree.com/v3` |
| Credentials | Sandbox dashboard | Production dashboard |

---

## 8. Key Differences from CCAvenue/Easebuzz/Razorpay

| Aspect | CCAvenue/Easebuzz/Razorpay | Cashfree |
|---|---|---|
| Settings doctype | Single | Multiple records (one per company) |
| Merchant doctype | `* Merchant` child records | None – Settings IS the merchant |
| Payment Gateway name | `CCAvenue`, `Easebuzz`, `Razorpay` | `Cashfree-{gateway_name}` |
| Checkout UX | Redirect / Modal | In-page JS SDK |
| `initiate_payment` API | ✓ | Not implemented (use `get_payment_url`) |
| `check_payment_status` API | ✓ | Not implemented |
| External frontend API | Full suite | Minimal (`make_payment` only) |
| Refund webhooks | ✓ | Not implemented |

---

## 9. Common Issues

| Issue | Cause | Fix |
|---|---|---|
| `ValidationError: No Cashfree Settings found` | No record for company, no default | Create a Cashfree Settings with `is_default=1` |
| Webhook signature fails | Wrong `client_secret` resolved | Ensure company is stored in Integration Request data |
| `order_status` not PAID | Order not completed on Cashfree | Check Cashfree dashboard for payment status |
| `payment_session_id` expired | 20-minute session limit | Re-create order |
| Multiple `is_default` records | Misconfiguration | `handle_default_setting()` auto-clears others on save |

---

## 10. Testing Checklist

- [ ] Create `Cashfree Settings` with sandbox `client_id` / `client_secret`, `environment = Sandbox`
- [ ] Set `company` to a hostel company, `is_default = 1`
- [ ] Click **Test Connection** → success
- [ ] Call `create_test_payment_link` to verify payment link creation
- [ ] Complete test payment via checkout page
- [ ] `make_payment` called → `Integration Request` → `Completed`
- [ ] Cashfree webhook fires → `cashfree_webhook` → duplicate-safe handling
- [ ] Multi-company: create second Settings for a second hostel, verify routing
