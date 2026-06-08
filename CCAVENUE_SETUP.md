# CCAvenue Payment Gateway – Administrator Setup Guide

> **Audience:** System Administrators and ERPNext Implementors  
> **Last updated:** June 2026

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Architecture Overview](#2-architecture-overview)
3. [Step 1 – Configure CCAvenue Settings (Global Fallback)](#3-step-1--configure-ccavenue-settings-global-fallback)
4. [Step 2 – Create CCAvenue Merchant Records](#4-step-2--create-ccavenue-merchant-records)
5. [Step 3 – ERPNext Accounts Setup](#5-step-3--erpnext-accounts-setup)
6. [Step 4 – Per-Hostel Gateway Selection](#6-step-4--per-hostel-gateway-selection)
7. [Step 5 – Configure CCAvenue Webhooks](#7-step-5--configure-ccavenue-webhooks)
8. [Step 6 – Test the Integration](#8-step-6--test-the-integration)
9. [Troubleshooting](#9-troubleshooting)
10. [FAQ](#10-faq)

---

## 1. Prerequisites

- ERPNext with the `payments` app installed and migrated
- A CCAvenue merchant account ([register at ccavenue.com](https://www.ccavenue.com))
- From the CCAvenue dashboard, collect:
  - **Merchant ID**
  - **Access Code**
  - **Working Key** (encryption key)
- Environment: Sandbox for testing, Production for live

---

## 2. Architecture Overview

```
Customer (Hostel)
      │ custom_hostel_name → Company
      ▼
Payment Gateway Config (one per company) → preferred_gateway = CCAvenue
      ▼
CCAvenue Merchant (one per company/hostel)
      │  merchant_id  +  access_code  +  encryption_key
      │  environment  +  company  +  bank_account  +  debtors_account
      ▼
CCAvenue Payment Gateway (AES-128-CBC encrypted payloads)
```

**Merchant resolution** (priority order):
1. Explicit `custom_merchant_name` in payment request
2. `CCAvenue Merchant` where `company` matches the paying hostel
3. `CCAvenue Merchant` with `Is Default Merchant` checked
4. Auto-create default if none found

---

## 3. Step 1 – Configure CCAvenue Settings (Global Fallback)

**Path:** ERPNext Desk → Payments → CCAvenue Settings

These are **fallback** credentials used only when no matching Merchant record is found. For production multi-hostel setups, configure Merchant records instead.

| Field | Description | Example |
|---|---|---|
| Merchant ID | Your CCAvenue Merchant ID | `1234567` |
| Access Code | From CCAvenue dashboard | `ABCD01234567890EFGH` |
| Encryption Key | Working Key from CCAvenue | `ABCDEF0123456789...` |
| Environment | `Sandbox` or `Production` | `Sandbox` |
| Redirect To | External frontend URL after payment | `https://app.example.com/payment` |
| Header Image | Optional branding image URL | |

> Click **Test Connection** after saving to validate credentials.

---

## 4. Step 2 – Create CCAvenue Merchant Records

**Path:** ERPNext Desk → Payments → CCAvenue Merchant → New

Create one record per hostel/company that uses CCAvenue.

| Field | Description | Required | Example |
|---|---|---|---|
| Merchant Name | Unique identifier for this merchant | ✓ | `Hostel-Koramangala` |
| Is Default Merchant | Used as fallback when no company match | | ☑ on one record only |
| Merchant ID | CCAvenue Merchant ID for this merchant | ✓ | `9876543` |
| Access Code | CCAvenue Access Code | ✓ | `XYZA09876543210MNOP` |
| Encryption Key | CCAvenue Working Key | ✓ | `...` |
| Environment | `Sandbox` or `Production` | ✓ | `Production` |
| Company | Link to ERPNext Company | | `Hostel Koramangala Pvt Ltd` |
| Bank Account | Prefix of GL bank account | | `CCAvenue` |
| Debtors Account | Prefix of GL receivable account | | `Debtors` |

### Notes

- Only **one** merchant can have `Is Default Merchant` checked.
- `Bank Account` and `Debtors Account` are **prefixes only** — the company abbreviation is appended automatically. E.g., `CCAvenue` → `CCAvenue - HKP`.
- If left blank, the system falls back to `CCAvenue - {abbr}` or `Debtors - {abbr}`.

---

## 5. Step 3 – ERPNext Accounts Setup

### 5.1 Bank (Transit) Account

**Path:** Accounting → Chart of Accounts → [Company] → Bank → New Account

For each merchant/hostel:
- **Account Name:** `CCAvenue - <Company Abbr>` (e.g. `CCAvenue - HKP`)
- **Account Type:** `Bank`
- **Currency:** INR (or your default)
- **Company:** The hostel company

Set the **Bank Account** field on the Merchant record to `CCAvenue` (the prefix without `- HKP`).

### 5.2 Mode of Payment

**Path:** Accounting → Mode of Payment → New

- **Mode of Payment:** `CCAvenue`
- **Type:** `Bank`

This mode is used on all Payment Entries created by CCAvenue payments.

---

## 6. Step 4 – Per-Hostel Gateway Selection

**Path:** ERPNext Desk → Payments → Payment Gateway Config → New

Create one record per company to set which gateway each hostel uses:

| Field | Value |
|---|---|
| Company | `Hostel Koramangala Pvt Ltd` |
| Preferred Payment Gateway | `CCAvenue` |
| Merchant Name (Override) | `Hostel-Koramangala` (optional; leave blank to auto-resolve by company) |

This drives `handle_cart_submit()` to automatically select the correct gateway when a student checks out.

---

## 7. Step 5 – Configure CCAvenue Webhooks

In the **CCAvenue Dashboard → Profile → Technical Parameters**, set:

| Parameter | Value |
|---|---|
| Merchant Redirect URL | `https://<your-site>/api/method/payments.payment_gateways.doctype.ccavenue_settings.ccavenue_settings.verify_transaction?merchant=<Merchant-Name>` |
| Merchant Notify URL (S2S) | `https://<your-site>/api/method/payments.payment_gateways.doctype.ccavenue_settings.ccavenue_settings.order_status_echo?merchant=<Merchant-Name>` |

> Replace `<Merchant-Name>` with the exact name from the `CCAvenue Merchant` record (e.g. `Hostel-Koramangala`).

### Additional webhooks (optional but recommended)

| Webhook | URL |
|---|---|
| Reconciliation / UPI delayed | `.../reconciliation_status?merchant=<Merchant-Name>` |
| Refund status | `.../refund_status?merchant=<Merchant-Name>` |

### How `?merchant=` works

The `?merchant=` query parameter tells the callback which merchant's encryption key to use for decrypting the CCAvenue response. Without it, the system falls back to the company-matched or default merchant.

---

## 8. Step 6 – Test the Integration

### 8.1 Test Connection

In CCAvenue Settings, click **Test Connection** to verify global credentials.  
In each CCAvenue Merchant record, the JS form button validates merchant-specific credentials.

### 8.2 End-to-End Test Payment

1. Create a test Sales Invoice for a student at a configured hostel
2. From the frontend, call `initiate_payment` with the invoice details
3. Post the encrypted form to CCAvenue Sandbox
4. Use a CCAvenue test card to complete payment
5. CCAvenue redirects to `verify_transaction` → Integration Request → `Completed`
6. Verify a `Payment Entry` is created with:
   - Mode of Payment: `CCAvenue`
   - Paid To: `CCAvenue - <Abbr>`
   - Reference No: CCAvenue Tracking ID

### 8.3 CCAvenue Sandbox Test Cards

| Card Type | Card Number |
|---|---|
| Visa | `4111 1111 1111 1111` |
| Mastercard | `5105 1051 0510 5100` |
| Net Banking | Select any test bank |

---

## 9. Troubleshooting

| Problem | Cause | Solution |
|---|---|---|
| "Merchant not found" error | No matching merchant for the company | Create a CCAvenue Merchant with the company linked, or set one as default |
| "Decryption failed" | Wrong encryption key | Verify the Working Key in CCAvenue dashboard matches the Merchant record |
| Payment Entry not created | GL account `CCAvenue - {abbr}` does not exist | Create the bank account (Step 5.1) or set `bank_account` prefix on merchant |
| Webhook returns 403 | CCAvenue IP not whitelisted | Not required; but ensure the webhook URL is accessible from the internet |
| Session not restored | User not found in `merchant_param1` | Ensure `payer_email` is a valid Frappe user, or pass `user` in payment kwargs |
| Duplicate Payment Entries | Both `verify_transaction` and `order_status_echo` fired | Expected; `order_status_echo` has duplicate-prevention guard |
| `encResp` decryption error on localhost | CCAvenue can't reach localhost | Use ngrok or deploy to a public server for testing |

---

## 10. FAQ

**Q: Can multiple hostels use different CCAvenue merchant IDs?**  
A: Yes. Create one `CCAvenue Merchant` record per hostel with its own merchant ID, access code, and encryption key. Link each to its company.

**Q: What happens if a company has no merchant record?**  
A: The system uses the `Is Default Merchant` record, or falls back to global CCAvenue Settings credentials.

**Q: Where do I see failed payments?**  
A: Check **Integration Requests** with status `Failed`. Each failed attempt is logged with the CCAvenue error response.

**Q: Are Payment Charges (surcharges) supported?**  
A: Yes. Create `Payment Charge` records with a charge percentage. These are applied to the payment amount before it is sent to CCAvenue.

**Q: What is the `redirect_to` field?**  
A: An external frontend URL (e.g. your React/Next.js app) where users are redirected after payment. The `integration_id` (Integration Request name) is appended as a query parameter so the frontend can fetch the final status.
