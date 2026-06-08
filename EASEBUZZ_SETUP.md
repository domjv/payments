# Easebuzz Payment Gateway – Administrator Setup Guide

> **Audience:** System Administrators and ERPNext Implementors  
> **Last updated:** June 2026  
> **Supersedes:** previous EASEBUZZ_SETUP.md

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Architecture Overview](#2-architecture-overview)
3. [Step 1 – Configure Easebuzz Settings (Global Fallback)](#3-step-1--configure-easebuzz-settings-global-fallback)
4. [Step 2 – Create Easebuzz Merchant Records](#4-step-2--create-easebuzz-merchant-records)
5. [Step 3 – ERPNext Accounts Setup](#5-step-3--erpnext-accounts-setup)
6. [Step 4 – Per-Hostel Gateway Selection](#6-step-4--per-hostel-gateway-selection)
7. [Step 5 – Configure Easebuzz Webhooks](#7-step-5--configure-easebuzz-webhooks)
8. [Step 6 – Split Payments (Easy Split)](#8-step-6--split-payments-easy-split)
9. [Step 7 – Test the Integration](#9-step-7--test-the-integration)
10. [Troubleshooting](#10-troubleshooting)
11. [FAQ](#11-faq)

---

## 1. Prerequisites

- ERPNext with the `payments` app installed and migrated
- An Easebuzz merchant account ([register at easebuzz.in](https://easebuzz.in))
- From the Easebuzz dashboard, collect:
  - **Merchant Key** (API key)
  - **Salt** (secret for hash generation)
- Environment: Test for testing, Production for live

---

## 2. Architecture Overview

```
Customer (Hostel)
      │ custom_hostel_name → Company
      ▼
Payment Gateway Config (one per company) → preferred_gateway = Easebuzz
      ▼
Easebuzz Merchant (one per company/hostel)
      │  merchant_key  +  salt
      │  environment  +  company  +  bank_account  +  debtors_account
      │  split_payments (child table – Easy Split)
      ▼
Easebuzz Payment Gateway (SHA-512 hash verification)
```

**Merchant resolution** (priority):
1. Explicit `custom_merchant_name` in payment request
2. `Easebuzz Merchant` where `company` matches
3. `Easebuzz Merchant` with `Is Default Merchant`
4. Throws if none found

---

## 3. Step 1 – Configure Easebuzz Settings (Global Fallback)

**Path:** ERPNext Desk → Payments → Easebuzz Settings

| Field | Description | Example |
|---|---|---|
| Merchant Key | Global fallback API key | `abc123merchant` |
| Salt | Global fallback salt | `mysecretsal` |
| Environment | `Test` or `Production` | `Test` |
| Redirect To | External frontend URL after payment | `https://app.example.com/payment` |
| Header Image | Optional branding image (Data URL) | |

> Click **Test Connection** after saving.  
> **Tip:** For multi-hostel setups, leave these blank and manage everything via Merchant records.

---

## 4. Step 2 – Create Easebuzz Merchant Records

**Path:** ERPNext Desk → Payments → Easebuzz Merchant → New

| Field | Description | Required | Example |
|---|---|---|---|
| Merchant Name | Unique identifier | ✓ | `Hostel-Koramangala` |
| Is Default Merchant | Fallback when no company match | | ☑ on one record only |
| Merchant Key | Easebuzz API key | ✓ | `eb_live_xxxx` |
| Salt | Easebuzz salt | ✓ | `my_salt_value` |
| Environment | `Test` or `Production` | ✓ | `Production` |
| Company | Link to ERPNext Company | | `Hostel Koramangala Pvt Ltd` |
| Bank Account | Prefix of GL bank account | | `Easebuzz` |
| Debtors Account | Prefix of GL receivable account | | `Debtors` |

### Notes

- `Bank Account` and `Debtors Account` are prefixes — company abbreviation is appended automatically (e.g. `Easebuzz` → `Easebuzz - HKP`).
- Merchant credentials (key + salt) take priority over global Settings credentials.

---

## 5. Step 3 – ERPNext Accounts Setup

### 5.1 Bank (Transit) Account

**Path:** Accounting → Chart of Accounts → [Company] → Bank → New Account

- **Account Name:** `Easebuzz - <Company Abbr>` (e.g. `Easebuzz - HKP`)
- **Account Type:** `Bank`
- **Company:** The hostel company

Set the **Bank Account** prefix on the Merchant record to `Easebuzz`.

### 5.2 Mode of Payment

**Path:** Accounting → Mode of Payment → New

- **Mode of Payment:** `Easebuzz`
- **Type:** `Bank`

---

## 6. Step 4 – Per-Hostel Gateway Selection

**Path:** ERPNext Desk → Payments → Payment Gateway Config → New

| Field | Value |
|---|---|
| Company | `Hostel Koramangala Pvt Ltd` |
| Preferred Payment Gateway | `Easebuzz` |
| Merchant Name (Override) | `Hostel-Koramangala` (optional) |

---

## 7. Step 5 – Configure Easebuzz Webhooks

In the **Easebuzz Dashboard → Account → API Details**, set:

| Parameter | Value |
|---|---|
| Success URL (surl) | `https://<site>/api/method/payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.verify_transaction?merchant=<Merchant-Name>` |
| Failure URL (furl) | Same as surl (the handler checks the status field) |
| Webhook URL | `https://<site>/api/method/payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.webhook_callback?merchant=<Merchant-Name>` |

> Replace `<Merchant-Name>` with the exact name from the `Easebuzz Merchant` record (e.g. `Hostel-Koramangala`).

### Optional: Refund webhook

| Webhook | URL |
|---|---|
| Refund status | `.../refund_status?merchant=<Merchant-Name>` |

### How `?merchant=` works

The `?merchant=` query parameter selects which merchant's salt to use for hash verification. Without it, the system falls back to the company-matched or default merchant.

---

## 8. Step 6 – Split Payments (Easy Split)

Easy Split allows a single payment to be split across multiple sub-merchants automatically.

### 8.1 Obtain Easy Split labels

Contact Easebuzz support to get sub-merchant labels for your account.

### 8.2 Configure on Merchant record

In the **Easebuzz Merchant** record → **Easy Split Payments** section:

| Field | Description | Example |
|---|---|---|
| Label | Easebuzz sub-merchant label | `label_hostel_a` |
| Split Percent | Percentage of payment to route | `70` (= 70%) |

Add one row per sub-merchant. The percentages should total 100%.

### 8.3 How it works

The system computes absolute amounts from percentages and includes them in the payment POST body. Easebuzz internally distributes the funds.

---

## 9. Step 7 – Test the Integration

### 9.1 Test Connection

From any Easebuzz Merchant record, click **Test Connection**.

### 9.2 Test card details (Easebuzz sandbox)

| Type | Details |
|---|---|
| Card number | `4111 1111 1111 1111` |
| Expiry | Any future date |
| CVV | Any 3 digits |
| OTP | `123456` |

### 9.3 End-to-End Test

1. Call `initiate_payment` with a Sales Invoice reference
2. Redirect browser to returned `payment_url`
3. Complete sandbox payment
4. Easebuzz POSTs to `verify_transaction?merchant=<name>`
5. Verify Integration Request → `Completed`
6. Verify Payment Entry created with:
   - Mode of Payment: `Easebuzz`
   - Paid To: `Easebuzz - <Abbr>`
   - Reference No: `easepayid` from Easebuzz

---

## 10. Troubleshooting

| Problem | Cause | Solution |
|---|---|---|
| Hash mismatch in `verify_transaction` | Wrong salt on merchant record | Verify salt matches Easebuzz dashboard exactly |
| `initiate_payment` fails | Easebuzz API rejected request | Check Error Log → `easebuzz_utils.initiate_payment_api` |
| Payment Entry not created | GL account `Easebuzz - {abbr}` missing | Create bank account (Step 5.1) |
| UDF values truncated | Special chars or long docnames | `_udf_sanitize()` limits to 300 chars and replaces invalid chars |
| Split payment amounts wrong | Percentages don't add up | Ensure split_payments totals 100% |
| `webhook_callback` not called | URL not configured in Easebuzz dashboard | Set Webhook URL in Easebuzz → API Details |

---

## 11. FAQ

**Q: Can a hostel use both a merchant key AND the global Settings key?**  
A: Yes. If a Merchant record has a key/salt, those take priority. If they're blank, the global Settings key/salt are used.

**Q: What is the difference between `verify_transaction` and `webhook_callback`?**  
A: `verify_transaction` is the browser redirect (surl/furl) — the user's browser POSTs to it after payment. `webhook_callback` is a server-to-server JSON webhook called by Easebuzz independently. Both are duplicate-safe; whichever fires first processes the payment.

**Q: Are Payment Charges (surcharges) applied?**  
A: Yes. Active `Payment Charge` records are applied in `create_payment_request_data()` before the Easebuzz API call.

**Q: What currencies does Easebuzz support?**  
A: INR only.

**Q: What is `redirect_to` in the Merchant record?**  
A: An external frontend URL. After payment is verified, the user is redirected to this URL with `?integration_id=<name>` appended. The frontend can then call `check_payment_status` to get the full result.
