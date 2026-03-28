# Easebuzz Payment Gateway - Frontend Integration Guide

**For NextJS + TypeScript + Tailwind Applications using Atomic Design**

This guide provides everything your frontend team needs to integrate Easebuzz payment gateway with iframe support, following the same pattern as your existing CCAvenue implementation.

---

## Table of Contents

1. [Overview](#overview)
2. [API Endpoints](#api-endpoints)
3. [Integration Architecture](#integration-architecture)
4. [Implementation Steps](#implementation-steps)
5. [Code Examples](#code-examples)
6. [Payment Flow Diagram](#payment-flow-diagram)
7. [Error Handling](#error-handling)
8. [Testing](#testing)

---

## Overview

### Key Features

- ✅ **iFrame Integration** - Seamless embedded payment experience
- ✅ **Multi-Merchant Support** - Different merchants for different companies
- ✅ **Real-time Status Updates** - Check payment status via API
- ✅ **Secure Hash Verification** - All responses are hash-verified by backend
- ✅ **Mobile Responsive** - Works in WebView and mobile browsers
- ✅ **TypeScript Support** - Fully typed interfaces

### Differences from CCAvenue

| Feature | CCAvenue | Easebuzz |
|---------|----------|----------|
| **Payment URL** | Returns encrypted data to build form | Returns direct payment URL |
| **iframe Usage** | Load iframe_url directly | Load payment_url in iframe |
| **Hash Handling** | Backend only | Backend only (SHA-512) |
| **Callback** | Form POST | Form POST |
| **Status Check** | Same API | Same API |

---

## API Endpoints

**Base URL:** `http://livinnza.localhost:8000`

### 1. Initiate Payment

**Endpoint:** `/api/method/payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.initiate_payment`

**Method:** `POST`

**Authentication:** Optional (can use API token or session)

#### Request Body

```typescript
interface InitiatePaymentRequest {
  amount: number;                      // Required - Payment amount
  currency?: string;                   // Optional - Default: "INR"
  reference_doctype: string;           // Required - e.g., "Sales Invoice"
  reference_docname: string;           // Required - e.g., "SINV-2024-00001"
  company?: string;                    // Optional - Company name for merchant selection
  payer_email: string;                 // Required - Customer email
  payer_name: string;                  // Required - Customer ID/name
  description: string;                 // Required - Payment description
  phone?: string;                      // Optional - Customer phone (default: 9999999999)
  custom_merchant_name?: string;       // Optional - Specific merchant to use
  custom_pincode?: string;             // Optional - Customer pincode
  custom_state?: string;               // Optional - Customer state
}
```

#### Response

```typescript
interface InitiatePaymentResponse {
  success: boolean;
  payment_token: string;               // Integration request ID - save this!
  payment_url: string;                 // Direct Easebuzz payment URL
  txnid: string;                       // Transaction ID
  merchant_name?: string;              // Merchant used
  error?: string;                      // Error message if failed
}
```

#### Example Response (Success)

```json
{
  "success": true,
  "payment_token": "INT-REQ-2025-00123",
  "payment_url": "https://testpay.easebuzz.in/pay/abc123xyz456",
  "txnid": "ORDER-001@INT-REQ-2025-00123",
  "merchant_name": "IvyLiving Campus A"
}
```

---

### 2. Check Payment Status

**Endpoint:** `/api/method/payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.check_payment_status`

**Method:** `GET`

**Authentication:** Optional

#### Query Parameters

```typescript
interface CheckStatusRequest {
  integration_request_name: string;    // The payment_token from initiate_payment
}
```

#### Response

```typescript
interface CheckStatusResponse {
  success: boolean;
  status: string;                      // "Completed", "Failed", "Queued", etc.
  payment_status: string;              // "success", "failure", "pending"
  transaction_id?: string;             // Easebuzz transaction ID
  bank_ref_no?: string;                // Bank reference number
  payment_mode?: string;               // "Debit Card", "Net Banking", etc.
  error_message?: string;              // Error message if failed
  reference_doctype: string;           // Original doctype
  reference_docname: string;           // Original document name
  amount?: string;
  currency?: string;
  error?: string;                      // Error if request failed
}
```

#### Example Response (Success)

```json
{
  "success": true,
  "status": "Completed",
  "payment_status": "success",
  "transaction_id": "EZPAY123456",
  "bank_ref_no": "1234567890",
  "payment_mode": "Debit Card",
  "error_message": null,
  "reference_doctype": "Sales Invoice",
  "reference_docname": "SINV-2024-00001",
  "amount": "1000.00",
  "currency": "INR"
}
```

---

## Integration Architecture

### Component Structure (Atomic Design)

```
atoms/
  ├── PaymentButton/
  │   └── PaymentButton.tsx
  └── PaymentStatusBadge/
      └── PaymentStatusBadge.tsx

molecules/
  └── PaymentModal/
      └── PaymentModal.tsx

organisms/
  └── PaymentGateway/
      ├── EasebuzzPayment.tsx          # Main component
      └── PaymentIframe.tsx             # iframe wrapper

templates/
  └── PaymentPage/
      └── PaymentPage.tsx

services/
  ├── payment.service.ts               # API calls
  └── payment.types.ts                 # TypeScript types

hooks/
  └── usePayment.ts                    # Payment logic hook

utils/
  └── payment.utils.ts                 # Helper functions
```

---

## Implementation Steps

### Step 1: Create Type Definitions

Create `services/payment.types.ts`:

```typescript
// services/payment.types.ts

export interface InitiatePaymentRequest {
  amount: number;
  currency?: string;
  reference_doctype: string;
  reference_docname: string;
  company?: string;
  payer_email: string;
  payer_name: string;
  description: string;
  phone?: string;
  custom_merchant_name?: string;
  custom_pincode?: string;
  custom_state?: string;
}

export interface InitiatePaymentResponse {
  success: boolean;
  payment_token: string;
  payment_url: string;
  txnid: string;
  merchant_name?: string;
  error?: string;
}

export interface PaymentStatusResponse {
  success: boolean;
  status: string;
  payment_status: string;
  transaction_id?: string;
  bank_ref_no?: string;
  payment_mode?: string;
  error_message?: string;
  reference_doctype: string;
  reference_docname: string;
  amount?: string;
  currency?: string;
  error?: string;
}

export type PaymentStatus = 
  | 'idle'
  | 'initiating'
  | 'processing'
  | 'success'
  | 'failed'
  | 'error';

export interface PaymentState {
  status: PaymentStatus;
  paymentToken?: string;
  paymentUrl?: string;
  error?: string;
  transactionId?: string;
}
```

---

### Step 2: Create Payment Service

Create `services/payment.service.ts`:

```typescript
// services/payment.service.ts

import {
  InitiatePaymentRequest,
  InitiatePaymentResponse,
  PaymentStatusResponse,
} from './payment.types';

const ERPNEXT_BASE_URL = process.env.NEXT_PUBLIC_ERPNEXT_URL || '';

class PaymentService {
  private baseUrl: string;
  private apiKey?: string;
  private apiSecret?: string;

  constructor() {
    this.baseUrl = ERPNEXT_BASE_URL;
    this.apiKey = process.env.NEXT_PUBLIC_ERPNEXT_API_KEY;
    this.apiSecret = process.env.NEXT_PUBLIC_ERPNEXT_API_SECRET;
  }

  /**
   * Get authorization headers
   */
  private getHeaders(): HeadersInit {
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    };

    // Add API token if available
    if (this.apiKey && this.apiSecret) {
      headers['Authorization'] = `token ${this.apiKey}:${this.apiSecret}`;
    }

    return headers;
  }

  /**
   * Initiate Easebuzz payment
   */
  async initiatePayment(
    data: InitiatePaymentRequest
  ): Promise<InitiatePaymentResponse> {
    try {
      const response = await fetch(
        `${this.baseUrl}/api/method/payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.initiate_payment`,
        {
          method: 'POST',
          headers: this.getHeaders(),
          body: JSON.stringify(data),
          credentials: 'include', // Include cookies for session auth
        }
      );

      const result = await response.json();

      // ERPNext wraps response in 'message' field
      return result.message || result;
    } catch (error) {
      console.error('Payment initiation error:', error);
      throw new Error(
        error instanceof Error ? error.message : 'Failed to initiate payment'
      );
    }
  }

  /**
   * Check payment status
   */
  async checkPaymentStatus(
    paymentToken: string
  ): Promise<PaymentStatusResponse> {
    try {
      const response = await fetch(
        `${this.baseUrl}/api/method/payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.check_payment_status?integration_request_name=${paymentToken}`,
        {
          method: 'GET',
          headers: this.getHeaders(),
          credentials: 'include',
        }
      );

      const result = await response.json();
      return result.message || result;
    } catch (error) {
      console.error('Payment status check error:', error);
      throw new Error(
        error instanceof Error ? error.message : 'Failed to check payment status'
      );
    }
  }

  /**
   * Poll payment status until completion or timeout
   */
  async pollPaymentStatus(
    paymentToken: string,
    maxAttempts: number = 30,
    intervalMs: number = 2000
  ): Promise<PaymentStatusResponse> {
    let attempts = 0;

    return new Promise((resolve, reject) => {
      const interval = setInterval(async () => {
        attempts++;

        try {
          const status = await this.checkPaymentStatus(paymentToken);

          // If payment is completed or failed, stop polling
          if (
            status.status === 'Completed' ||
            status.status === 'Failed' ||
            status.payment_status === 'success' ||
            status.payment_status === 'failure'
          ) {
            clearInterval(interval);
            resolve(status);
            return;
          }

          // If max attempts reached, stop polling
          if (attempts >= maxAttempts) {
            clearInterval(interval);
            reject(new Error('Payment status check timeout'));
          }
        } catch (error) {
          clearInterval(interval);
          reject(error);
        }
      }, intervalMs);
    });
  }
}

export const paymentService = new PaymentService();
```

---

### Step 3: Create Payment Hook

Create `hooks/usePayment.ts`:

```typescript
// hooks/usePayment.ts

import { useState, useCallback } from 'react';
import { paymentService } from '@/services/payment.service';
import {
  InitiatePaymentRequest,
  PaymentState,
  PaymentStatusResponse,
} from '@/services/payment.types';

export const usePayment = () => {
  const [paymentState, setPaymentState] = useState<PaymentState>({
    status: 'idle',
  });

  /**
   * Initiate payment
   */
  const initiatePayment = useCallback(
    async (data: InitiatePaymentRequest) => {
      setPaymentState({ status: 'initiating' });

      try {
        const response = await paymentService.initiatePayment(data);

        if (!response.success) {
          throw new Error(response.error || 'Failed to initiate payment');
        }

        setPaymentState({
          status: 'processing',
          paymentToken: response.payment_token,
          paymentUrl: response.payment_url,
        });

        return response;
      } catch (error) {
        const errorMessage =
          error instanceof Error ? error.message : 'Payment initiation failed';

        setPaymentState({
          status: 'error',
          error: errorMessage,
        });

        throw error;
      }
    },
    []
  );

  /**
   * Check payment status
   */
  const checkPaymentStatus = useCallback(
    async (paymentToken: string): Promise<PaymentStatusResponse> => {
      try {
        const status = await paymentService.checkPaymentStatus(paymentToken);

        // Update state based on status
        if (status.payment_status === 'success' || status.status === 'Completed') {
          setPaymentState((prev) => ({
            ...prev,
            status: 'success',
            transactionId: status.transaction_id,
          }));
        } else if (status.payment_status === 'failure' || status.status === 'Failed') {
          setPaymentState((prev) => ({
            ...prev,
            status: 'failed',
            error: status.error_message || 'Payment failed',
          }));
        }

        return status;
      } catch (error) {
        const errorMessage =
          error instanceof Error ? error.message : 'Status check failed';

        setPaymentState((prev) => ({
          ...prev,
          status: 'error',
          error: errorMessage,
        }));

        throw error;
      }
    },
    []
  );

  /**
   * Reset payment state
   */
  const resetPayment = useCallback(() => {
    setPaymentState({ status: 'idle' });
  }, []);

  return {
    paymentState,
    initiatePayment,
    checkPaymentStatus,
    resetPayment,
  };
};
```

---

### Step 4: Create Payment iframe Component (Organism)

Create `organisms/PaymentGateway/PaymentIframe.tsx`:

```typescript
// organisms/PaymentGateway/PaymentIframe.tsx

'use client';

import { useEffect, useRef, useState } from 'react';

interface PaymentIframeProps {
  paymentUrl: string;
  onClose?: () => void;
  onPaymentComplete?: () => void;
  className?: string;
}

export const PaymentIframe: React.FC<PaymentIframeProps> = ({
  paymentUrl,
  onClose,
  onPaymentComplete,
  className = '',
}) => {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Listen for messages from iframe (if payment page posts messages)
    const handleMessage = (event: MessageEvent) => {
      // Validate origin for security
      if (!event.origin.includes('easebuzz.in')) {
        return;
      }

      // Handle payment completion message
      if (event.data?.status === 'success' || event.data?.status === 'completed') {
        onPaymentComplete?.();
      }
    };

    window.addEventListener('message', handleMessage);

    return () => {
      window.removeEventListener('message', handleMessage);
    };
  }, [onPaymentComplete]);

  const handleLoad = () => {
    setIsLoading(false);
  };

  return (
    <div className={`relative w-full h-full ${className}`}>
      {/* Loading spinner */}
      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-white">
          <div className="flex flex-col items-center space-y-4">
            <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
            <p className="text-sm text-gray-600">Loading payment gateway...</p>
          </div>
        </div>
      )}

      {/* Close button */}
      {onClose && (
        <button
          onClick={onClose}
          className="absolute top-4 right-4 z-10 p-2 bg-white rounded-full shadow-lg hover:bg-gray-100 transition-colors"
          aria-label="Close payment"
        >
          <svg
            className="w-6 h-6 text-gray-600"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>
      )}

      {/* Payment iframe */}
      <iframe
        ref={iframeRef}
        src={paymentUrl}
        className="w-full h-full border-0"
        title="Easebuzz Payment"
        onLoad={handleLoad}
        sandbox="allow-forms allow-scripts allow-same-origin allow-top-navigation allow-popups"
      />
    </div>
  );
};
```

---

### Step 5: Create Main Payment Component (Organism)

Create `organisms/PaymentGateway/EasebuzzPayment.tsx`:

```typescript
// organisms/PaymentGateway/EasebuzzPayment.tsx

'use client';

import { useState, useCallback, useEffect } from 'react';
import { usePayment } from '@/hooks/usePayment';
import { PaymentIframe } from './PaymentIframe';
import { InitiatePaymentRequest } from '@/services/payment.types';
import { paymentService } from '@/services/payment.service';

interface EasebuzzPaymentProps {
  amount: number;
  referenceDoctype: string;
  referenceDocname: string;
  payerEmail: string;
  payerName: string;
  description: string;
  company?: string;
  phone?: string;
  onSuccess?: (transactionId?: string) => void;
  onFailure?: (error: string) => void;
  onCancel?: () => void;
}

export const EasebuzzPayment: React.FC<EasebuzzPaymentProps> = ({
  amount,
  referenceDoctype,
  referenceDocname,
  payerEmail,
  payerName,
  description,
  company,
  phone,
  onSuccess,
  onFailure,
  onCancel,
}) => {
  const { paymentState, initiatePayment, checkPaymentStatus, resetPayment } =
    usePayment();
  const [showIframe, setShowIframe] = useState(false);
  const [isPolling, setIsPolling] = useState(false);

  /**
   * Start payment process
   */
  const handleStartPayment = async () => {
    const paymentData: InitiatePaymentRequest = {
      amount,
      reference_doctype: referenceDoctype,
      reference_docname: referenceDocname,
      payer_email: payerEmail,
      payer_name: payerName,
      description,
      company,
      phone,
      currency: 'INR',
    };

    try {
      const response = await initiatePayment(paymentData);

      if (response.success && response.payment_url) {
        setShowIframe(true);
      }
    } catch (error) {
      console.error('Payment initiation failed:', error);
      onFailure?.(
        error instanceof Error ? error.message : 'Payment initiation failed'
      );
    }
  };

  /**
   * Handle iframe close
   */
  const handleCloseIframe = () => {
    setShowIframe(false);
    
    // Start polling for payment status
    if (paymentState.paymentToken && !isPolling) {
      startPollingPaymentStatus();
    } else {
      onCancel?.();
    }
  };

  /**
   * Start polling payment status
   */
  const startPollingPaymentStatus = useCallback(async () => {
    if (!paymentState.paymentToken || isPolling) return;

    setIsPolling(true);

    try {
      // Poll for 60 seconds (30 attempts * 2s interval)
      const status = await paymentService.pollPaymentStatus(
        paymentState.paymentToken,
        30,
        2000
      );

      setIsPolling(false);

      if (status.payment_status === 'success' || status.status === 'Completed') {
        onSuccess?.(status.transaction_id);
      } else {
        onFailure?.(
          status.error_message || 'Payment failed or was cancelled'
        );
      }

      resetPayment();
    } catch (error) {
      setIsPolling(false);
      console.error('Payment status polling failed:', error);
      
      // Still try to check one last time
      if (paymentState.paymentToken) {
        try {
          const finalStatus = await checkPaymentStatus(
            paymentState.paymentToken
          );
          
          if (finalStatus.payment_status === 'success') {
            onSuccess?.(finalStatus.transaction_id);
          } else {
            onCancel?.();
          }
        } catch {
          onCancel?.();
        }
      } else {
        onCancel?.();
      }

      resetPayment();
    }
  }, [
    paymentState.paymentToken,
    isPolling,
    checkPaymentStatus,
    resetPayment,
    onSuccess,
    onFailure,
    onCancel,
  ]);

  /**
   * Handle payment complete from iframe
   */
  const handlePaymentComplete = () => {
    setShowIframe(false);
    startPollingPaymentStatus();
  };

  // Render payment button
  if (paymentState.status === 'idle') {
    return (
      <button
        onClick={handleStartPayment}
        className="px-6 py-3 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        Pay ₹{amount.toFixed(2)}
      </button>
    );
  }

  // Render loading state
  if (paymentState.status === 'initiating') {
    return (
      <div className="flex items-center space-x-3">
        <div className="w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
        <span className="text-gray-600">Initializing payment...</span>
      </div>
    );
  }

  // Render iframe modal
  if (showIframe && paymentState.paymentUrl) {
    return (
      <div className="fixed inset-0 z-50 bg-black bg-opacity-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-lg shadow-2xl w-full max-w-4xl h-[80vh] overflow-hidden">
          <PaymentIframe
            paymentUrl={paymentState.paymentUrl}
            onClose={handleCloseIframe}
            onPaymentComplete={handlePaymentComplete}
          />
        </div>
      </div>
    );
  }

  // Render polling state
  if (isPolling) {
    return (
      <div className="flex flex-col items-center space-y-4 p-6">
        <div className="w-12 h-12 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
        <p className="text-gray-600">Verifying payment status...</p>
        <p className="text-sm text-gray-500">Please wait, do not refresh the page</p>
      </div>
    );
  }

  // Render error state
  if (paymentState.status === 'error') {
    return (
      <div className="flex flex-col items-center space-y-4 p-6 bg-red-50 rounded-lg">
        <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center">
          <svg
            className="w-6 h-6 text-red-600"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </div>
        <p className="text-red-600 font-semibold">Payment Failed</p>
        <p className="text-sm text-gray-600 text-center">{paymentState.error}</p>
        <button
          onClick={() => {
            resetPayment();
            handleStartPayment();
          }}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          Try Again
        </button>
      </div>
    );
  }

  return null;
};
```

---

### Step 6: Create Payment Button (Atom)

Create `atoms/PaymentButton/PaymentButton.tsx`:

```typescript
// atoms/PaymentButton/PaymentButton.tsx

'use client';

interface PaymentButtonProps {
  amount: number;
  onClick: () => void;
  loading?: boolean;
  disabled?: boolean;
  className?: string;
}

export const PaymentButton: React.FC<PaymentButtonProps> = ({
  amount,
  onClick,
  loading = false,
  disabled = false,
  className = '',
}) => {
  return (
    <button
      onClick={onClick}
      disabled={disabled || loading}
      className={`
        relative px-8 py-4 bg-gradient-to-r from-blue-600 to-blue-700 
        text-white rounded-xl font-semibold text-lg shadow-lg
        hover:from-blue-700 hover:to-blue-800 
        active:scale-95 transition-all duration-200
        disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100
        ${className}
      `}
    >
      {loading ? (
        <span className="flex items-center justify-center space-x-3">
          <svg
            className="w-5 h-5 animate-spin"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
          <span>Processing...</span>
        </span>
      ) : (
        <span className="flex items-center justify-center space-x-2">
          <svg
            className="w-5 h-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z"
            />
          </svg>
          <span>Pay ₹{amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
        </span>
      )}
    </button>
  );
};
```

---

### Step 7: Usage Example (Page)

Create `app/payment/page.tsx`:

```typescript
// app/payment/page.tsx

'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { EasebuzzPayment } from '@/organisms/PaymentGateway/EasebuzzPayment';

export default function PaymentPage() {
  const router = useRouter();
  const [showPayment, setShowPayment] = useState(false);

  const handleSuccess = (transactionId?: string) => {
    console.log('Payment successful! Transaction ID:', transactionId);
    
    // Show success message
    alert('Payment completed successfully!');
    
    // Redirect to success page
    router.push(`/payment/success?txn=${transactionId}`);
  };

  const handleFailure = (error: string) => {
    console.error('Payment failed:', error);
    
    // Show error message
    alert(`Payment failed: ${error}`);
    
    // Optionally redirect to failure page
    // router.push('/payment/failure');
  };

  const handleCancel = () => {
    console.log('Payment cancelled by user');
    
    // Show cancellation message
    alert('Payment was cancelled');
    
    // Optionally redirect back
    // router.push('/dashboard');
  };

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-2xl mx-auto">
        <div className="bg-white rounded-2xl shadow-xl p-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-6">
            Complete Your Payment
          </h1>

          {/* Invoice Details */}
          <div className="mb-8 p-6 bg-gray-50 rounded-lg">
            <div className="flex justify-between items-center mb-3">
              <span className="text-gray-600">Invoice Number:</span>
              <span className="font-semibold">SINV-2024-00001</span>
            </div>
            <div className="flex justify-between items-center mb-3">
              <span className="text-gray-600">Customer:</span>
              <span className="font-semibold">John Doe</span>
            </div>
            <div className="flex justify-between items-center pt-3 border-t border-gray-200">
              <span className="text-lg font-semibold">Total Amount:</span>
              <span className="text-2xl font-bold text-blue-600">
                ₹1,000.00
              </span>
            </div>
          </div>

          {/* Payment Component */}
          <div className="flex justify-center">
            <EasebuzzPayment
              amount={1000.0}
              referenceDoctype="Sales Invoice"
              referenceDocname="SINV-2024-00001"
              payerEmail="customer@example.com"
              payerName="CUST-00001"
              description="Payment for Invoice SINV-2024-00001"
              company="IvyLiving Campus A"
              phone="9876543210"
              onSuccess={handleSuccess}
              onFailure={handleFailure}
              onCancel={handleCancel}
            />
          </div>

          {/* Security Info */}
          <div className="mt-8 p-4 bg-blue-50 rounded-lg">
            <div className="flex items-start space-x-3">
              <svg
                className="w-5 h-5 text-blue-600 mt-0.5 flex-shrink-0"
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path
                  fillRule="evenodd"
                  d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z"
                  clipRule="evenodd"
                />
              </svg>
              <div>
                <p className="text-sm font-semibold text-blue-900">
                  Secure Payment
                </p>
                <p className="text-xs text-blue-700">
                  Your payment information is encrypted and secure. We never
                  store your card details.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
```

---

## Payment Flow Diagram

```
User Action              Frontend                    Backend                  Easebuzz
    |                       |                           |                        |
    |-- Click Pay -------->|                           |                        |
    |                       |                           |                        |
    |                       |-- POST initiate_payment ->|                        |
    |                       |                           |                        |
    |                       |                           |-- Generate hash ------>|
    |                       |                           |                        |
    |                       |                           |<- Payment URL ---------|
    |                       |                           |                        |
    |                       |<-- payment_url, token ---|                        |
    |                       |                           |                        |
    |<-- Show iframe ------|                           |                        |
    |                       |                           |                        |
    |                       |   IFRAME OPENS            |                        |
    |                       |-------------------------->|----------------------->|
    |                       |                           |                        |
    |-- Make Payment ------|-------------------------->|----------------------->|
    |                       |                           |                        |
    |<- Payment Page ------|---------------------------|<-----------------------|
    |                       |                           |                        |
    |-- Confirm Payment -->|-------------------------->|----------------------->|
    |                       |                           |                        |
    |                       |                           |<-- Callback POST ------|
    |                       |                           |                        |
    |                       |                           |- Verify Hash           |
    |                       |                           |- Create Payment Entry  |
    |                       |                           |- Update Invoice        |
    |                       |                           |                        |
    |<- Redirect/Close ----|<-- Success/Failure -------|                        |
    |                       |                           |                        |
    |                       |-- GET check_status ------>|                        |
    |                       |                           |                        |
    |                       |<-- Status: Completed -----|                        |
    |                       |                           |                        |
    |<- Success Page ------|                           |                        |
```

---

## Error Handling

### Common Error Scenarios

```typescript
// utils/payment.utils.ts

export const handlePaymentError = (error: unknown): string => {
  if (error instanceof Error) {
    // Network errors
    if (error.message.includes('Failed to fetch')) {
      return 'Network error. Please check your internet connection.';
    }

    // Timeout errors
    if (error.message.includes('timeout')) {
      return 'Request timed out. Please try again.';
    }

    // API errors
    if (error.message.includes('Missing required parameter')) {
      return 'Invalid payment data. Please contact support.';
    }

    return error.message;
  }

  return 'An unexpected error occurred. Please try again.';
};

export const getPaymentStatusMessage = (status: string): {
  title: string;
  message: string;
  type: 'success' | 'error' | 'warning';
} => {
  switch (status) {
    case 'success':
    case 'Completed':
      return {
        title: 'Payment Successful',
        message: 'Your payment has been processed successfully.',
        type: 'success',
      };

    case 'failure':
    case 'Failed':
      return {
        title: 'Payment Failed',
        message: 'Your payment could not be processed. Please try again.',
        type: 'error',
      };

    case 'pending':
    case 'Queued':
      return {
        title: 'Payment Pending',
        message: 'Your payment is being processed. Please wait.',
        type: 'warning',
      };

    default:
      return {
        title: 'Unknown Status',
        message: 'Unable to determine payment status.',
        type: 'warning',
      };
  }
};
```

---

## Testing

### Environment Variables

Add to `.env.local`:

```bash
# ERPNext Backend
NEXT_PUBLIC_ERPNEXT_URL=https://your-erpnext-site.com
NEXT_PUBLIC_ERPNEXT_API_KEY=your_api_key
NEXT_PUBLIC_ERPNEXT_API_SECRET=your_api_secret

# For development
NEXT_PUBLIC_ENABLE_PAYMENT_LOGS=true
```

### Test Payment Credentials

**Test Environment:**
- Easebuzz provides test credentials
- Test cards are available in Easebuzz documentation
- Use `Environment: "Test"` in merchant configuration

### Test Cases

1. **Successful Payment**
   - Amount: ₹10 (minimum)
   - Use test card: As per Easebuzz docs
   - Verify payment entry created

2. **Failed Payment**
   - Use invalid/expired test card
   - Verify error handling

3. **Payment Cancellation**
   - Close iframe before completing
   - Verify cancellation handling

4. **Network Issues**
   - Test with slow 3G network
   - Verify loading states and timeouts

5. **Status Polling**
   - Complete payment
   - Close iframe immediately
   - Verify status is detected via polling

---

## Key Differences from CCAvenue

| Aspect | CCAvenue | Easebuzz |
|--------|----------|----------|
| **Initiate Response** | Returns encrypted data, access code, merchant ID | Returns direct payment URL |
| **iframe Source** | Build form with encrypted data, post to CCAvenue | Load payment_url directly |
| **Hash Generation** | Backend only | Backend only (SHA-512) |
| **Transaction ID** | Generated as `order_id@integration_id` | Generated as `order_id@integration_id` |
| **Callback Field** | Uses `merchant_param1` | Uses `udf1` field |
| **Status Field** | `order_status: "Success"` | `status: "success"` |

---

## Support & Troubleshooting

### Common Issues

**Issue 1: iframe not loading**
- Check CORS settings
- Verify payment URL is valid
- Check console for errors

**Issue 2: Payment status not updating**
- Ensure polling is working
- Check backend logs
- Verify webhook URL is accessible

**Issue 3: Hash verification failed**
- This is handled by backend
- Check merchant salt configuration
- Contact backend team

### Debug Mode

Enable debug logging:

```typescript
// In payment.service.ts
if (process.env.NEXT_PUBLIC_ENABLE_PAYMENT_LOGS === 'true') {
  console.log('[Payment] Initiating:', data);
  console.log('[Payment] Response:', result);
}
```

---

## Checklist for Frontend Team

- [ ] Install dependencies (`axios` or use `fetch`)
- [ ] Set up environment variables
- [ ] Create type definitions (`payment.types.ts`)
- [ ] Implement payment service (`payment.service.ts`)
- [ ] Create payment hook (`usePayment.ts`)
- [ ] Build iframe component (`PaymentIframe.tsx`)
- [ ] Build main payment component (`EasebuzzPayment.tsx`)
- [ ] Create payment button atom
- [ ] Test successful payment flow
- [ ] Test failed payment flow
- [ ] Test cancellation flow
- [ ] Test status polling
- [ ] Implement error handling
- [ ] Add loading states
- [ ] Test on mobile devices
- [ ] Review security (no sensitive data in frontend)

---

## Questions?

If you have any questions or need clarification, please:
1. Check backend API responses using Postman/cURL
2. Review backend logs for payment processing
3. Test with Easebuzz test credentials first
4. Contact the backend team for API issues

**Backend Endpoints:** All endpoints are in `easebuzz_settings.py`
**Payment Flow:** Similar to CCAvenue implementation you already have

Good luck with the integration! 🚀
