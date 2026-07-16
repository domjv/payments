# Razorpay Payment Gateway – Setup & Configuration Guide

> **Last updated:** June 2026  
> **Branch:** `pleasantbiz-payment-gateways`  
> **Scope:** Multi-merchant Razorpay for Ivy Living / ERPNext Hostel Management

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Prerequisites](#2-prerequisites)
3. [Installation](#3-installation)
4. [Configuring Razorpay Settings (Global Fallback)](#4-configuring-razorpay-settings-global-fallback)
5. [Creating Razorpay Merchant Records](#5-creating-razorpay-merchant-records)
6. [Per-Hostel Gateway Selection](#6-per-hostel-gateway-selection)
7. [ERPNext Accounts Setup](#7-erpnext-accounts-setup)
8. [Webhook Configuration](#8-webhook-configuration)
9. [Migration from Legacy Single-Settings Setup](#9-migration-from-legacy-single-settings-setup)
10. [Testing](#10-testing)
11. [Scheduler & Auto-Capture](#11-scheduler--auto-capture)

---

## 1. Architecture Overview

```
ERPNext Company/Hostel
        │
        ▼
Payment Gateway Config (one per company)
        │  preferred_gateway = "Razorpay"
        │  merchant_name = "Hostel-A-RP"  (optional explicit override)
        ▼
Razorpay Merchant (one per company/hostel)
        │  api_key / api_secret
        │  environment = Test | Production
        │  company, bank_account, debtors_account
        ▼
Razorpay Settings (global fallback only)
        │  Used when no Merchant record matches
        ▼
Razorpay API (https://api.razorpay.com)
```

**Resolution chain for credentials:**
1. Explicit `custom_merchant_name` in payment kwargs
2. Merchant where `company` matches the payment company
3. Merchant with `is_default = 1`
4. Global `Razorpay Settings` (fallback)

---

## 2. Prerequisites

- Frappe/ERPNext bench with the `payments` app installed
- Razorpay account (Test or Production)
- API Key and API Secret from the Razorpay Dashboard
- `razorpay` pip package (bundled with the app)

---

## 3. Installation

```bash
# Run after pulling the new code
bench --site <your-site> migrate
```

The migration patch `payments.patches.v1_0.razorpay_merchant_migration` runs automatically and:
- Seeds a default `Razorpay Merchant` from existing `Razorpay Settings` if none exist
- Captures any lingering `Authorized` Integration Requests

---

## 4. Configuring Razorpay Settings (Global Fallback)

**Path:** ERPNext Desk → Payments → Razorpay Settings

| Field | Description |
|---|---|
| API Key (Global Fallback) | Used only when no matching Merchant record exists |
| API Secret (Global Fallback) | Same |
| Environment (Global Fallback) | `Test` or `Production` |
| Redirect To (Global Fallback) | External frontend URL; `integration_id` is appended as query param |

> **Tip:** For production installs with multiple hostels, leave these blank and manage everything via Merchant records.

---

## 5. Creating Razorpay Merchant Records

**Path:** ERPNext Desk → Payments → Razorpay Merchant → New

| Field | Description | Example |
|---|---|---|
| Merchant Name | Unique identifier for this merchant | `Hostel-Koramangala` |
| Is Default Merchant | Fallback when no company match | ☑ on one record only |
| API Key | Razorpay API Key for this merchant | `rzp_live_xxxxx` |
| API Secret | Razorpay API Secret | (hidden) |
| Environment | `Test` or `Production` | `Production` |
| Company | Link to ERPNext Company | `Hostel Koramangala Pvt Ltd` |
| Bank Account | Prefix for GL account (e.g. `Razorpay`) | `Razorpay` |
| Debtors Account | Prefix for receivable account | `Debtors` |
| Redirect To | Optional per-merchant redirect URL | `https://app.example.com/payment` |

### Test Connection

After saving a merchant, click **Test Connection** to verify credentials.

---

## 6. Per-Hostel Gateway Selection

**Path:** ERPNext Desk → Payments → Payment Gateway Config → New

Create one record per Company:

| Field | Description |
|---|---|
| Company | Link to ERPNext Company / hostel |
| Preferred Payment Gateway | `CCAvenue`, `Easebuzz`, or `Razorpay` |
| Merchant Name (Override) | Optional explicit merchant record name |

This drives `handle_cart_submit()` and `initiate_payment()` to use the right gateway per hostel without any code changes.

---

## 7. ERPNext Accounts Setup

Each Razorpay Merchant record needs:

### Bank (Transit) Account

Create a Bank account in ERPNext for each merchant:

**Accounts → Chart of Accounts → Bank → New Account**
- Account Name: `Razorpay - <Company Abbr>` (e.g. `Razorpay - HKP`)
- Account Type: `Bank`
- Company: matching company

Set the **Bank Account** prefix on the Merchant record to `Razorpay`.

### Mode of Payment

**Accounts → Mode of Payment → New**
- Mode of Payment: `Razorpay`
- Type: `Bank`

---

## 8. Webhook Configuration

### Configure in Razorpay Dashboard

**Razorpay Dashboard → Settings → Webhooks → Add New Webhook**

| Webhook Event | URL |
|---|---|
| `payment.authorized` | (handled automatically by Checkout.js callback) |
| `refund.created` | `https://<your-site>/api/method/payments.payment_gateways.doctype.razorpay_settings.razorpay_settings.refund_status` |
| `refund.processed` | Same as above |
| `refund.failed` | Same as above |
| Subscriptions | `https://<your-site>/api/method/payments.payment_gateways.doctype.razorpay_settings.razorpay_settings.razorpay_subscription_callback` |

> **Note:** Unlike CCAvenue/Easebuzz, Razorpay does not have a browser-redirect `verify_transaction` URL. Payment verification is done by the frontend calling `verify_payment` after the Checkout.js modal succeeds.

---

## 9. Migration from Legacy Single-Settings Setup

If you previously used Razorpay with only `Razorpay Settings` (no merchant records):

1. **Run `bench migrate`** – the migration patch auto-creates a default Merchant record
2. **Verify** the created record at `Razorpay Merchant → Default`
3. **Update** the record: set `company`, `bank_account`, `debtors_account`, `environment`
4. **Link** via `Payment Gateway Config` if needed

No existing Integration Requests or Payment Entries are modified.

---

## 10. Testing

### Test Payment (Sandbox)

Use Razorpay test credentials:
- API Key: `rzp_test_xxxxx`
- API Secret: test secret
- Set `environment = Test` on the Merchant record

Test card: `4111 1111 1111 1111`, any future expiry, any CVV.

### Verify the Flow

1. Call `initiate_payment` → get `order_id` and `api_key`
2. Open Razorpay Checkout.js modal with returned params
3. Complete test payment
4. Call `verify_payment` with `razorpay_payment_id`, `razorpay_order_id`, `razorpay_signature`, `token`
5. Check `Integration Request` status → should be `Completed`
6. Check `Payment Entry` was created

---

## 11. Scheduler & Auto-Capture

New Razorpay orders are created with `payment_capture=1`, meaning Razorpay auto-captures the payment. Integration Requests reach `Completed` immediately after `verify_payment` is called.

The `capture_payment` scheduler job (`hooks.py → scheduler_events.all`) handles **only legacy `Authorized` records** from before this migration. Once all pre-migration records are resolved, you can safely remove that scheduler entry from `hooks.py`.
