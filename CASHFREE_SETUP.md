# Cashfree Payment Gateway – Administrator Setup Guide

> **Audience:** System Administrators and ERPNext Implementors  
> **Last updated:** June 2026  
> **Supersedes:** previous CASHFREE_SETUP.md

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Architecture Overview](#2-architecture-overview)
3. [Step 1 – Install Cashfree SDK](#3-step-1--install-cashfree-sdk)
4. [Step 2 – Create Cashfree Settings Records](#4-step-2--create-cashfree-settings-records)
5. [Step 3 – ERPNext Accounts Setup](#5-step-3--erpnext-accounts-setup)
6. [Step 4 – Per-Hostel Configuration](#6-step-4--per-hostel-configuration)
7. [Step 5 – Configure Cashfree Webhooks](#7-step-5--configure-cashfree-webhooks)
8. [Step 6 – Test the Integration](#8-step-6--test-the-integration)
9. [Troubleshooting](#9-troubleshooting)
10. [Differences from CCAvenue / Easebuzz / Razorpay](#10-differences-from-ccavenue--easebuzz--razorpay)
11. [FAQ](#11-faq)

---

## 1. Prerequisites

- ERPNext with the `payments` app installed and migrated
- A Cashfree merchant account ([register at cashfree.com](https://www.cashfree.com))
- From the Cashfree dashboard, collect:
  - **App ID** (Client ID)
  - **Secret Key** (Client Secret)
- Python SDK: `cashfree_pg` (installed separately)

---

## 2. Architecture Overview

Cashfree uses a **different architecture** from the other gateways:

```
Company/Hostel A          Company/Hostel B
      │                         │
      ▼                         ▼
Cashfree Settings #1      Cashfree Settings #2
  gateway_name = HsA        gateway_name = HsB
  company = Hostel A         company = Hostel B
  client_id / secret         client_id / secret
  environment                environment
      │                         │
      ▼                         ▼
Payment Gateway:          Payment Gateway:
  "Cashfree-HsA"            "Cashfree-HsB"
```

**Key difference:** There is **no separate "Merchant" doctype**. Each `Cashfree Settings` record *is* the merchant configuration. You create one record per company/hostel.

**Resolution Priority:**
1. Record where `company` field matches the paying hostel
2. Record with `is_default = 1`
3. First available record
4. Throws `ValidationError` if none found

---

## 3. Step 1 – Install Cashfree SDK

```bash
cd /path/to/frappe-bench
bench pip install cashfree_pg
```

Verify installation:
```bash
bench execute "import cashfree_pg; print(cashfree_pg.__version__)"
```

---

## 4. Step 2 – Create Cashfree Settings Records

**Path:** ERPNext Desk → Payments → Cashfree Settings → New

Create **one record per hostel/company**.

| Field | Description | Required | Example |
|---|---|---|---|
| Gateway Name | Unique identifier for this instance | ✓ | `Hostel-Koramangala` |
| Company | ERPNext Company this instance belongs to | | `Hostel Koramangala Pvt Ltd` |
| Is Default | Use as fallback when no company match | | ☑ on one record only |
| Environment | `Sandbox` or `Production` | ✓ | `Production` |
| Client ID | Cashfree App ID | ✓ | `CF123456TEST` |
| Client Secret | Cashfree Secret Key | ✓ | `cfsk_...` |
| Redirect URL | URL to redirect after payment | | `https://app.example.com/payment` |
| Webhook URL | Auto-generated on save (read-only) | — | `https://<site>/api/method/...cashfree_webhook` |

### Notes

- `Gateway Name` becomes the Payment Gateway record: `Cashfree-{gateway_name}`.
- Only one record can have `Is Default` checked — saving automatically clears others.
- `Webhook URL` is auto-generated and shown read-only — copy it to the Cashfree dashboard.

### Test Connection

After saving, click **Test Connection** to verify credentials against Cashfree API.

---

## 5. Step 3 – ERPNext Accounts Setup

### 5.1 Bank (Transit) Account

**Path:** Accounting → Chart of Accounts → [Company] → Bank → New Account

- **Account Name:** `Cashfree - <Company Abbr>` (e.g. `Cashfree - HKP`)
- **Account Type:** `Bank`
- **Company:** The hostel company

### 5.2 Mode of Payment

**Path:** Accounting → Mode of Payment → New

- **Mode of Payment:** `Cashfree`
- **Type:** `Bank`

---

## 6. Step 4 – Per-Hostel Configuration

Since Cashfree Settings records are keyed by `company`, the gateway is automatically resolved per hostel without needing a `Payment Gateway Config` record. However, if a hostel switches between Cashfree and another gateway, use:

**Path:** ERPNext Desk → Payments → Payment Gateway Config → New

| Field | Value |
|---|---|
| Company | `Hostel Koramangala Pvt Ltd` |
| Preferred Payment Gateway | `Cashfree` |
| Merchant Name (Override) | `Hostel-Koramangala` (the Cashfree Settings `gateway_name`) |

---

## 7. Step 5 – Configure Cashfree Webhooks

### 7.1 Find the Webhook URL

Open the Cashfree Settings record → copy the **Webhook URL** field. It looks like:
```
https://<your-site>/api/method/payments.payment_gateways.doctype.cashfree_settings.cashfree_settings.cashfree_webhook
```

> **Note:** Unlike CCAvenue/Easebuzz, the Cashfree webhook URL does **not** include a `?merchant=` parameter. The handler resolves the settings by `order_id` → Integration Request → `company`.

### 7.2 Configure in Cashfree Dashboard

**Cashfree Dashboard → Developers → Webhooks → Add Endpoint**

| Setting | Value |
|---|---|
| Endpoint URL | The webhook URL from Step 7.1 |
| Events | ✓ `PAYMENT_SUCCESS_WEBHOOK` ✓ `PAYMENT_FAILED_WEBHOOK` |
| Version | `2023-08-01` (or latest) |

### 7.3 Handled webhook events

| Event | Action |
|---|---|
| `PAYMENT_SUCCESS_WEBHOOK` (order_status = PAID) | Integration Request → `Completed` → `on_payment_authorized` |
| `PAYMENT_FAILED_WEBHOOK` | Integration Request → `Failed` |

---

## 8. Step 6 – Test the Integration

### 8.1 Test Connection

In the Cashfree Settings record, click **Test Connection**.

### 8.2 Create a Test Payment Link

Click **Create Test Payment Link** (available on saved records) to generate a test link and verify the API is working.

### 8.3 Sandbox test credentials

Use credentials from the [Cashfree Sandbox Dashboard](https://test.cashfree.com):
- Set `environment = Sandbox` on the Settings record

### 8.4 Test payment methods (sandbox)

| Method | Details |
|---|---|
| UPI | `success@cashfree` |
| Card | Use Cashfree sandbox test cards |
| Net Banking | Select any bank in sandbox mode |

### 8.5 End-to-End Flow

1. Payment request created → `get_payment_url()` → `/cashfree_checkout` page
2. User pays via Cashfree JS SDK
3. SDK success → `make_payment(order_id, payment_session_id, ...)` called
4. Server fetches order status from Cashfree API → `PAID`
5. Integration Request → `Completed`
6. `on_payment_authorized` → Payment Entry created

---

## 9. Troubleshooting

| Problem | Cause | Solution |
|---|---|---|
| `No Cashfree Settings found` | No record for company, no default | Create a record with `company` linked or `is_default=1` |
| Webhook signature fails | Wrong record resolved | Check `company` stored in Integration Request |
| `payment_session_id` expired | 20-minute limit | Re-create order |
| Test Connection fails | Wrong App ID or Secret | Verify in Cashfree Sandbox/Production dashboard |
| Multiple `is_default` records | Misconfiguration | Save any Settings record — system auto-clears others |
| Payment not confirmed | Order status not PAID | Check Cashfree dashboard for order status |

---

## 10. Differences from CCAvenue / Easebuzz / Razorpay

| Feature | CCAvenue | Easebuzz | Razorpay | Cashfree |
|---|---|---|---|---|
| Settings doctype | Single | Single | Single | Multiple records |
| Merchant doctype | `CCAvenue Merchant` | `Easebuzz Merchant` | `Razorpay Merchant` | None |
| Multi-company pattern | Merchant records | Merchant records | Merchant records | Multiple Settings |
| Checkout UX | Redirect / form post | Redirect to hosted page | In-page modal | In-page JS SDK |
| `initiate_payment` API | ✓ | ✓ | ✓ | Not implemented |
| `check_payment_status` API | ✓ | ✓ | ✓ | Not implemented |
| Refund webhook | ✓ | ✓ | ✓ | Not implemented |
| Payment Charges | ✓ | ✓ | ✓ | Not implemented |
| Subscriptions | No | No | ✓ | No |
| Currencies | Limited | INR only | 100+ | Multiple |

---

## 11. FAQ

**Q: Can I use Cashfree for some hostels and CCAvenue for others?**  
A: Yes. Create `Payment Gateway Config` records per company to set the preferred gateway.

**Q: Does Cashfree support split payments?**  
A: Not currently implemented in this integration. Contact Cashfree for their split payment (Cashfree Route) product.

**Q: Where do I see payment logs?**  
A: In ERPNext → Integration Requests. Filter by `integration_request_service = Cashfree`.

**Q: What is the `redirect_url` field?**  
A: An optional URL to redirect the user to after payment completion on the checkout page.

**Q: How does the webhook determine which Settings record to use?**  
A: The webhook looks up the Integration Request by `order_id`, reads the `company` from its data, then calls `get_cashfree_settings_by_company(company)` to find the right Settings record and client secret for signature verification.
