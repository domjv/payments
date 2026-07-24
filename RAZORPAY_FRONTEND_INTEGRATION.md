# Razorpay Payment Gateway – Frontend Integration Guide

**For NextJS + TypeScript + Tailwind Applications**

This guide covers the Razorpay multi-merchant API, mirroring the same contract as CCAvenue and Easebuzz so the frontend can swap gateways with minimal code changes.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Differences from CCAvenue / Easebuzz](#2-differences-from-ccavenue--easebuzz)
3. [API Endpoints](#3-api-endpoints)
4. [Payment Flow](#4-payment-flow)
5. [TypeScript Interfaces](#5-typescript-interfaces)
6. [Implementation Example](#6-implementation-example)
7. [Error Handling](#7-error-handling)
8. [Testing](#8-testing)
9. [Multi-Gateway Routing](#9-multi-gateway-routing)
10. [payment.captured Webhook Fallback](#10-paymentcaptured-webhook-fallback)

---

## 1. Overview

Razorpay uses an **in-page JavaScript modal** (Checkout.js) instead of redirecting to an external hosted page. The backend API contract is identical to CCAvenue/Easebuzz:

| Step | CCAvenue / Easebuzz | Razorpay |
|---|---|---|
| 1. Initiate | `initiate_payment` → returns redirect URL | `initiate_payment` → returns `order_id` + `api_key` |
| 2. User pays | Browser navigates to hosted page | Checkout.js modal opens in-page |
| 3. Callback | Browser POSTs to `verify_transaction` | Frontend calls `verify_payment` with payment details |
| 4. Status | `check_payment_status` | `check_payment_status` (same API) |

---

## 2. Differences from CCAvenue / Easebuzz

| Feature | CCAvenue | Easebuzz | Razorpay |
|---|---|---|---|
| Payment UX | iFrame / redirect | Redirect to hosted page | In-page Checkout.js modal |
| `initiate_payment` response | `payment_url`, `encrypted_data` | `payment_url` | `order_id`, `api_key`, `amount` |
| Callback direction | Server POST to `verify_transaction` | Server POST to `verify_transaction` | Frontend calls `verify_payment` |
| Session restore | Automatic in `verify_transaction` | Automatic in `verify_transaction` | Automatic in `verify_payment` |
| `redirect_to` | On success, redirects with `integration_id` | Same | Same |

---

## 3. API Endpoints

**Base URL:** `https://<your-erpnext-site>`

### 3.1 Initiate Payment

```
POST /api/method/payments.payment_gateways.doctype.razorpay_settings.razorpay_settings.initiate_payment
```

**Request body (form-encoded or JSON):**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `amount` | float | ✓ | Payment amount in INR (Payment Charges are added server-side) |
| `reference_doctype` | string | ✓ | ERPNext doctype (e.g. `Sales Invoice`) |
| `reference_docname` | string | ✓ | ERPNext document name (e.g. `SINV-0001`) |
| `payer_email` | string | ✓ | Customer email |
| `payer_name` | string | ✓ | Customer ID / name |
| `currency` | string | | ISO currency code (default: `INR`) |
| `company` | string | | Company name (drives merchant selection) |
| `custom_merchant_name` | string | | Explicit Razorpay Merchant record name |
| `description` | string | | Payment description |
| `phone` | string | | Customer phone (prefill for Checkout.js) |

**Success Response:**

```json
{
  "success": true,
  "payment_token": "INT-00123",
  "order_id": "order_NxxxxxxxxxXXXXX",
  "api_key": "rzp_live_xxxxxxxxxxxxxxx",
  "amount": 60000,
  "currency": "INR",
  "merchant_name": "Hostel-Koramangala",
  "company": "Hostel Koramangala Pvt Ltd",
  "environment": "Production",
  "prefill": {
    "name": "CUST-00042",
    "email": "student@example.com",
    "contact": "9999999999"
  }
}
```

> **Note:** `amount` is in **paise** (100 = ₹1). Pass this directly to Checkout.js.

**Error Response:**

```json
{
  "success": false,
  "error": "Missing required parameter: payer_email"
}
```

---

### 3.2 Verify Payment

Called by the frontend **after** Checkout.js fires `payment.success`.

```
POST /api/method/payments.payment_gateways.doctype.razorpay_settings.razorpay_settings.verify_payment
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `razorpay_payment_id` | string | ✓ | From Checkout.js `payment.success` handler |
| `razorpay_order_id` | string | ✓ | From Checkout.js `payment.success` handler |
| `razorpay_signature` | string | ✓ | From Checkout.js `payment.success` handler |
| `token` | string | ✓ | `payment_token` from `initiate_payment` response |

**Success Response:**

```json
{
  "success": true,
  "status": "Completed",
  "payment_id": "pay_NxxxxxxxxxXXXXX",
  "redirect_to": "https://app.example.com/payment?integration_id=INT-00123",
  "reference_doctype": "Sales Invoice",
  "reference_docname": "SINV-0001"
}
```

---

### 3.3 Check Payment Status

```
GET /api/method/payments.payment_gateways.doctype.razorpay_settings.razorpay_settings.check_payment_status?integration_request_name=INT-00123
```

**Response:**

```json
{
  "success": true,
  "status": "Completed",
  "payment_id": "pay_NxxxxxxxxxXXXXX",
  "order_id": "order_NxxxxxxxxxXXXXX",
  "amount": 60000.0,
  "currency": "INR",
  "reference_doctype": "Sales Invoice",
  "reference_docname": "SINV-0001",
  "company": "Hostel Koramangala Pvt Ltd",
  "merchant_name": "Hostel-Koramangala"
}
```

**Status values:** `Queued` | `Authorized` | `Completed` | `Failed`

---

### 3.4 Refund Webhook (Server-to-Server)

Configure in Razorpay Dashboard. Not called by the frontend.

```
POST /api/method/payments.payment_gateways.doctype.razorpay_settings.razorpay_settings.refund_status
```

---

### 3.5 Payment Captured Webhook (Server-to-Server Fallback)

Configure in Razorpay Dashboard under **Settings → Webhooks**. Subscribe to the **`payment.captured`** event. Not called by the frontend.

```
POST /api/method/payments.payment_gateways.doctype.razorpay_settings.razorpay_settings.payment_captured
```

This is a **fallback** for when the preferred `verify_payment` callback fails (timeout, closed app, network drop — common with UPI). See [§10](#10-paymentcaptured-webhook-fallback).

---

## 4. Payment Flow

```
Frontend                    Backend (ERPNext)           Razorpay
   │                               │                        │
   │── POST initiate_payment ──────►                        │
   │                               │── POST /v1/orders ────►│
   │                               │◄── order_id ───────────│
   │◄── {order_id, api_key, ...} ──│                        │
   │                               │                        │
   │── Checkout.js modal opens ────────────────────────────►│
   │                               │                        │
   │◄─── payment.success ──────────────────────────────────│
   │   {razorpay_payment_id,        │                        │
   │    razorpay_order_id,          │                        │
   │    razorpay_signature}         │                        │
   │                               │                        │
   │── POST verify_payment ────────►                        │
   │                               │── verify HMAC          │
   │                               │── GET /v1/payments/id ►│
   │                               │◄── {status: captured}──│
   │                               │── create Payment Entry │
   │                               │── on_payment_authorized│
   │◄── {redirect_to: ...} ────────│                        │
   │                               │                        │
   │── redirect user ──────────────►                        │
```

---

## 5. TypeScript Interfaces

```typescript
// Request
interface InitiatePaymentRequest {
  amount: number;
  reference_doctype: string;
  reference_docname: string;
  payer_email: string;
  payer_name: string;
  currency?: string;
  company?: string;
  custom_merchant_name?: string;
  description?: string;
  phone?: string;
}

// Response
interface InitiatePaymentResponse {
  success: boolean;
  payment_token?: string;
  order_id?: string;
  api_key?: string;
  amount?: number;        // in paise
  currency?: string;
  merchant_name?: string;
  company?: string;
  environment?: "Test" | "Production";
  prefill?: {
    name: string;
    email: string;
    contact: string;
  };
  error?: string;
}

interface VerifyPaymentRequest {
  razorpay_payment_id: string;
  razorpay_order_id: string;
  razorpay_signature: string;
  token: string;
}

interface VerifyPaymentResponse {
  success: boolean;
  status?: string;
  payment_id?: string;
  redirect_to?: string;
  reference_doctype?: string;
  reference_docname?: string;
  error?: string;
}

interface PaymentStatusResponse {
  success: boolean;
  status?: "Queued" | "Authorized" | "Completed" | "Failed";
  payment_id?: string;
  order_id?: string;
  amount?: number;
  currency?: string;
  reference_doctype?: string;
  reference_docname?: string;
  company?: string;
  merchant_name?: string;
  error?: string;
}
```

---

## 6. Implementation Example

```tsx
"use client";
import { useState } from "react";

// Load Razorpay Checkout.js (add to _document.tsx or next.config.js)
// <Script src="https://checkout.razorpay.com/v1/checkout.js" />

const ERPNEXT_BASE = process.env.NEXT_PUBLIC_ERPNEXT_URL!;

async function initiatePayment(params: InitiatePaymentRequest): Promise<InitiatePaymentResponse> {
  const res = await fetch(
    `${ERPNEXT_BASE}/api/method/payments.payment_gateways.doctype.razorpay_settings.razorpay_settings.initiate_payment`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    }
  );
  const json = await res.json();
  return json.message ?? json;
}

async function verifyPayment(params: VerifyPaymentRequest): Promise<VerifyPaymentResponse> {
  const res = await fetch(
    `${ERPNEXT_BASE}/api/method/payments.payment_gateways.doctype.razorpay_settings.razorpay_settings.verify_payment`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    }
  );
  const json = await res.json();
  return json.message ?? json;
}

export function PayButton({
  amount,
  referenceDoctype,
  referenceDocname,
  company,
  payerEmail,
  payerName,
}: {
  amount: number;
  referenceDoctype: string;
  referenceDocname: string;
  company: string;
  payerEmail: string;
  payerName: string;
}) {
  const [loading, setLoading] = useState(false);

  const handlePay = async () => {
    setLoading(true);
    try {
      // Step 1: Create Razorpay order on ERPNext
      const init = await initiatePayment({
        amount,
        reference_doctype: referenceDoctype,
        reference_docname: referenceDocname,
        payer_email: payerEmail,
        payer_name: payerName,
        company,
        currency: "INR",
      });

      if (!init.success || !init.order_id) {
        alert(init.error ?? "Failed to initiate payment");
        return;
      }

      // Step 2: Open Razorpay Checkout.js modal
      const rzp = new (window as any).Razorpay({
        key: init.api_key,
        amount: init.amount,              // already in paise
        currency: init.currency ?? "INR",
        order_id: init.order_id,
        name: "Ivy Living",
        description: `Payment for ${referenceDocname}`,
        prefill: init.prefill,
        theme: { color: "#6366F1" },
        handler: async (response: {
          razorpay_payment_id: string;
          razorpay_order_id: string;
          razorpay_signature: string;
        }) => {
          // Step 3: Verify payment on ERPNext
          const result = await verifyPayment({
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_order_id: response.razorpay_order_id,
            razorpay_signature: response.razorpay_signature,
            token: init.payment_token!,
          });

          if (result.success && result.redirect_to) {
            window.location.href = result.redirect_to;
          } else {
            alert(result.error ?? "Payment verification failed");
          }
        },
        modal: {
          ondismiss: () => setLoading(false),
        },
      });

      rzp.open();
    } catch (err) {
      console.error(err);
      alert("Payment error. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      onClick={handlePay}
      disabled={loading}
      className="px-6 py-3 bg-indigo-600 text-white rounded-lg disabled:opacity-50"
    >
      {loading ? "Processing..." : `Pay ₹${amount}`}
    </button>
  );
}
```

---

## 7. Error Handling

| Scenario | `initiate_payment` response | Frontend action |
|---|---|---|
| Missing required field | `{success: false, error: "Missing required parameter: ..."}` | Show error message |
| No merchant configured | `{success: false, error: "No Razorpay Merchant configuration found"}` | Contact admin |
| Razorpay API down | `{success: false, error: "Could not create Razorpay order. Please try again."}` | Retry |
| Signature mismatch in verify | `{success: false, error: "Signature verification failed"}` | Log + alert |
| Already processed | `{success: true, message: "Payment already processed", status: "Completed"}` | Redirect to success |

---

## 8. Testing

### Sandbox credentials

Use credentials from the Razorpay Test Dashboard:
```
API Key:    rzp_test_xxxxxxxxxxxxx
API Secret: (from dashboard)
```

Set `environment = Test` on the Razorpay Merchant record.

### Test cards

| Card | Details |
|---|---|
| Visa (success) | `4111 1111 1111 1111`, any future expiry, any CVV |
| International | `4012 0010 3714 1112` |
| UPI (success) | `success@razorpay` |

### Simulating failures

Use test VPA `failure@razorpay` or use the Razorpay Test Dashboard to trigger specific error codes.

---

## 9. Multi-Gateway Routing

If different hostels use different gateways, the backend resolves the gateway automatically via `Payment Gateway Config`. The frontend can call the same `initiate_payment` endpoint for all gateways but must handle the response differently:

| Gateway | `initiate_payment` returns | Frontend action |
|---|---|---|
| CCAvenue | `encrypted_data`, `api_url` | Post encrypted form / open iframe |
| Easebuzz | `payment_url` | Redirect browser or open iframe |
| Razorpay | `order_id`, `api_key`, `amount` | Open Checkout.js modal |

To know which gateway was resolved, call `handle_cart_submit` (returns `gateway` field) or use the `Payment Gateway Config` API.

> **Tip:** The `handle_cart_submit` endpoint now returns `gateway` in the response alongside `payment_url`, so the frontend can branch on the gateway type without an extra API call.

---

## 10. payment.captured Webhook Fallback

The preferred completion path is still the frontend `verify_payment` callback. The Razorpay `payment.captured` webhook is a **safety net** for stuck `Queued` Integration Requests (common when the UPI app returns but the browser/app never calls `verify_payment`).

### How it works

1. Razorpay POSTs `payment.captured` to the webhook URL.
2. Backend verifies `X-Razorpay-Signature` against each merchant’s `webhook_secret` (falls back to Razorpay Settings).
3. If the Integration Request is already `Completed` / `Authorized` → ACK and stop (callback won).
4. Otherwise the captured payload is **stashed** on the IR (`webhook_capture_pending=1`) and ACK’d immediately.
5. A scheduler job (~every 2 minutes) waits for a **3-minute grace period**, then:
   - Skips if the callback completed the IR in the meantime.
   - Otherwise marks the IR `Completed`, creates the Payment Entry (`reference_no` = Razorpay Payment ID), updates the Sales Invoice, and adds webhook-completion comments.

### Dashboard setup

| Setting | Value |
|---|---|
| Webhook URL | `https://<your-erpnext-site>/api/method/payments.payment_gateways.doctype.razorpay_settings.razorpay_settings.payment_captured` |
| Events | `payment.captured` |
| Secret | Paste into **Razorpay Merchant → Webhook Secret** (or Razorpay Settings global fallback) |

### Frontend impact

No frontend change is required. Keep polling `check_payment_status` after Checkout.js success / on the pending-payment screen. If the webhook fallback completes the payment, status will flip to `Completed` and the user can be redirected to success.

### Audit trail

- Existing “Razorpay Payment Processed” comments on the reference document are unchanged.
- When the webhook does the work, an extra comment is added on the Sales Invoice / Payment Request / Customer **and** on the Payment Entry: **“Payment completed by Razorpay webhook”** (includes Payment ID, Order ID, and UPI RRN when available).
- UPI RRN/UTR is stored in Payment Entry remarks (and comments); `reference_no` remains the Razorpay Payment ID for duplicate prevention.
