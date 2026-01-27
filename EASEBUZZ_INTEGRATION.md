# Easebuzz Payment Gateway Integration Guide

Complete guide for integrating Easebuzz payment gateway with ERPNext and external frontend applications (NextJS/React Native).

## Table of Contents

1. [Overview](#overview)
2. [Multi-Merchant Configuration](#multi-merchant-configuration)
3. [API Endpoints](#api-endpoints)
4. [NextJS/Web Integration](#nextjs-integration)
5. [React Native/Mobile Integration](#react-native-integration)
6. [Payment Flow](#payment-flow)
7. [Error Handling](#error-handling)
8. [Testing](#testing)

---

## Overview

The Easebuzz integration follows the same architecture as CCAvenue and supports:

- **Multi-merchant configuration**: Configure multiple Easebuzz merchants for different companies
- **Default merchant fallback**: Automatic fallback to parent company merchant
- **API-based integration**: RESTful API endpoints for payment initiation and verification
- **WebView/iFrame support**: Mobile apps can load Easebuzz payment page in WebView
- **Webhook callbacks**: Real-time payment status updates
- **Hash verification**: Secure payment validation using SHA-512 hashing

---

## Multi-Merchant Configuration

### Creating Merchants

1. Navigate to **Payment Gateways > Easebuzz Merchant** in ERPNext
2. Click **New** to create a merchant

#### Merchant Fields

| Field | Description | Required |
|-------|-------------|----------|
| **Merchant Name** | Unique identifier for the merchant (use company name) | Yes |
| **Is Default Merchant** | Mark as default/parent company merchant | No |
| **Merchant Key** | Easebuzz Merchant Key | Yes |
| **Salt** | Easebuzz Salt Key | Yes |
| **Environment** | Test or Production | Yes |
| **Company** | Link to ERPNext Company (optional for default merchant) | No |
| **Bank Account** | Bank account prefix for payment entries | No |
| **Debtors Account** | Debtors account prefix | No |

### Default Merchant Strategy

The system automatically selects the appropriate merchant using this priority:

1. **Explicit merchant** specified in API call (`custom_merchant_name`)
2. **Company-specific merchant** if company is provided
3. **Default merchant** (marked with `is_default = 1`)
4. **Auto-created default** if no merchant exists

### Example Configuration

```
Merchant 1:
- Merchant Name: "IvyLiving Campus A"
- Is Default: Yes (✓)
- Company: IvyLiving Campus A
- Merchant Key: 2PBP7IABZ2
- Salt: Y6PH5SDK1P
- Environment: Production

Merchant 2:
- Merchant Name: "IvyLiving Campus B"
- Is Default: No
- Company: IvyLiving Campus B
- Merchant Key: ABC123XYZ
- Salt: DEF456UVW
- Environment: Production
```

When a payment is initiated:
- For Campus B transactions → Uses Merchant 2
- For Campus A transactions → Uses Merchant 1
- For other transactions → Uses Merchant 1 (default)

---

## API Endpoints

All endpoints are available at: `https://your-erpnext-site.com/api/method/payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.<method_name>`

### 1. Initiate Payment

**Endpoint:** `initiate_payment`

**Method:** POST (whitelisted, allows guest)

**Purpose:** Create a payment request and get Easebuzz payment URL

#### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `amount` | float | Yes | Payment amount |
| `currency` | string | No | Currency code (default: INR) |
| `reference_doctype` | string | Yes | Document type (e.g., "Sales Invoice") |
| `reference_docname` | string | Yes | Document name |
| `company` | string | No | Company name for merchant selection |
| `payer_email` | string | Yes | Customer email |
| `payer_name` | string | Yes | Customer ID or name |
| `description` | string | No | Payment description |
| `phone` | string | No | Customer phone number |
| `custom_merchant_name` | string | No | Specific merchant to use |
| `custom_pincode` | string | No | Customer pincode |
| `custom_state` | string | No | Customer state |

#### Response

```json
{
  "success": true,
  "payment_token": "integration-request-id",
  "payment_url": "https://testpay.easebuzz.in/pay/...",
  "txnid": "unique-transaction-id",
  "merchant_name": "IvyLiving Campus A"
}
```

#### Example Usage (JavaScript)

```javascript
// NextJS/React Example
async function initiatePayment() {
  const response = await fetch('/api/method/payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.initiate_payment', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      amount: 1000.00,
      reference_doctype: 'Sales Invoice',
      reference_docname: 'SINV-2024-00001',
      payer_email: 'customer@example.com',
      payer_name: 'CUST-00001',
      description: 'Payment for Invoice SINV-2024-00001',
      phone: '9876543210',
      company: 'IvyLiving Campus A'
    })
  });
  
  const data = await response.json();
  
  if (data.message.success) {
    // Open payment URL in iframe or redirect
    window.location.href = data.message.payment_url;
  }
}
```

---

### 2. Check Payment Status

**Endpoint:** `check_payment_status`

**Method:** GET

**Purpose:** Check the current status of a payment

#### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `integration_request_name` | string | Yes | Integration request ID from initiate_payment |

#### Response

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

#### Example Usage

```javascript
async function checkPaymentStatus(integrationId) {
  const response = await fetch(`/api/method/payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.check_payment_status?integration_request_name=${integrationId}`);
  
  const data = await response.json();
  
  if (data.message.success && data.message.status === 'Completed') {
    console.log('Payment successful!');
  }
}
```

---

### 3. Verify Transaction (Callback)

**Endpoint:** `verify_transaction`

**Method:** POST (whitelisted, allows guest)

**Purpose:** Handle Easebuzz's callback after payment completion

This endpoint is automatically called by Easebuzz after payment. It processes the payment response and updates the system.

**Callback URL Format:**
```
https://your-site.com/api/method/payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.verify_transaction?merchant={merchant_name}
```

---

### 4. Webhook Callback (For Mobile Apps)

**Endpoint:** `webhook_callback`

**Method:** POST (whitelisted, allows guest)

**Purpose:** Alternative callback endpoint that returns JSON instead of redirect

Useful for mobile apps that need to handle the payment response programmatically.

---

## NextJS Integration

### Step 1: Create Payment API Route

```typescript
// app/api/payment/initiate/route.ts
import { NextRequest, NextResponse } from 'next/server';

export async function POST(request: NextRequest) {
  const body = await request.json();
  
  const response = await fetch(
    `${process.env.ERPNEXT_URL}/api/method/payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.initiate_payment`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `token ${process.env.ERPNEXT_API_KEY}:${process.env.ERPNEXT_API_SECRET}`
      },
      body: JSON.stringify(body)
    }
  );
  
  const data = await response.json();
  return NextResponse.json(data.message);
}
```

### Step 2: Create Payment Component

```typescript
// components/EasebuzzPayment.tsx
'use client';

import { useState } from 'react';

interface PaymentProps {
  amount: number;
  invoiceId: string;
  customerEmail: string;
  customerId: string;
  onSuccess?: (data: any) => void;
  onFailure?: (data: any) => void;
}

export default function EasebuzzPayment({
  amount,
  invoiceId,
  customerEmail,
  customerId,
  onSuccess,
  onFailure
}: PaymentProps) {
  const [loading, setLoading] = useState(false);
  
  const initiatePayment = async () => {
    setLoading(true);
    
    try {
      const response = await fetch('/api/payment/initiate', {
        method: 'POST',
        body: JSON.stringify({
          amount,
          reference_doctype: 'Sales Invoice',
          reference_docname: invoiceId,
          payer_email: customerEmail,
          payer_name: customerId,
          description: `Payment for Invoice ${invoiceId}`
        })
      });
      
      const data = await response.json();
      
      if (data.success) {
        // Open payment URL in new window or iframe
        window.location.href = data.payment_url;
      } else {
        alert('Payment initiation failed: ' + data.error);
      }
    } catch (error) {
      console.error('Payment error:', error);
      alert('An error occurred');
    } finally {
      setLoading(false);
    }
  };
  
  return (
    <button 
      onClick={initiatePayment}
      disabled={loading}
      className="bg-blue-500 text-white px-6 py-3 rounded-lg"
    >
      {loading ? 'Processing...' : 'Pay Now'}
    </button>
  );
}
```

### Step 3: Handle Payment Callback

```typescript
// app/payment/callback/page.tsx
'use client';

import { useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';

export default function PaymentCallback() {
  const searchParams = useSearchParams();
  const integrationId = searchParams.get('integration_id');
  const [status, setStatus] = useState<any>(null);
  
  useEffect(() => {
    if (integrationId) {
      checkStatus();
    }
  }, [integrationId]);
  
  const checkStatus = async () => {
    const response = await fetch(
      `/api/payment/status?integration_id=${integrationId}`
    );
    const data = await response.json();
    setStatus(data);
  };
  
  if (!status) {
    return <div>Checking payment status...</div>;
  }
  
  return (
    <div className="container mx-auto p-8">
      {status.status === 'Completed' ? (
        <div className="bg-green-100 p-6 rounded-lg">
          <h1 className="text-2xl font-bold text-green-800">Payment Successful!</h1>
          <p>Transaction ID: {status.transaction_id}</p>
          <p>Amount: ₹{status.amount}</p>
        </div>
      ) : (
        <div className="bg-red-100 p-6 rounded-lg">
          <h1 className="text-2xl font-bold text-red-800">Payment Failed</h1>
          <p>{status.error_message}</p>
        </div>
      )}
    </div>
  );
}
```

---

## React Native Integration

### Step 1: Create Payment Service

```typescript
// services/paymentService.ts
import { Linking } from 'react-native';

export interface PaymentData {
  amount: number;
  reference_doctype: string;
  reference_docname: string;
  payer_email: string;
  payer_name: string;
  description?: string;
  phone?: string;
}

export class EasebuzzPaymentService {
  private baseUrl: string;
  
  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }
  
  async initiatePayment(paymentData: PaymentData) {
    const response = await fetch(
      `${this.baseUrl}/api/method/payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.initiate_payment`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(paymentData)
      }
    );
    
    const data = await response.json();
    return data.message;
  }
  
  async checkPaymentStatus(integrationId: string) {
    const response = await fetch(
      `${this.baseUrl}/api/method/payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.check_payment_status?integration_request_name=${integrationId}`
    );
    
    const data = await response.json();
    return data.message;
  }
}
```

### Step 2: Create Payment WebView Component

```typescript
// components/PaymentWebView.tsx
import React, { useState } from 'react';
import { View, Modal, ActivityIndicator } from 'react-native';
import { WebView } from 'react-native-webview';

interface Props {
  visible: boolean;
  paymentUrl: string;
  onSuccess: (data: any) => void;
  onFailure: (data: any) => void;
  onClose: () => void;
}

export const PaymentWebView: React.FC<Props> = ({
  visible,
  paymentUrl,
  onSuccess,
  onFailure,
  onClose
}) => {
  const [loading, setLoading] = useState(true);
  
  const handleNavigationStateChange = (navState: any) => {
    const { url } = navState;
    
    // Check if callback URL
    if (url.includes('verify_transaction') || url.includes('payment-success') || url.includes('payment-failed')) {
      setLoading(false);
      
      // Extract integration_id from URL
      const urlParams = new URLSearchParams(url.split('?')[1]);
      const integrationId = urlParams.get('integration_id');
      
      if (integrationId) {
        // Check payment status
        checkPaymentStatus(integrationId);
      }
    }
  };
  
  const checkPaymentStatus = async (integrationId: string) => {
    // Call your payment service to check status
    // Then call onSuccess or onFailure
  };
  
  return (
    <Modal visible={visible} animationType="slide">
      <View style={{ flex: 1 }}>
        {loading && (
          <View style={{ position: 'absolute', top: '50%', left: '50%' }}>
            <ActivityIndicator size="large" />
          </View>
        )}
        <WebView
          source={{ uri: paymentUrl }}
          onNavigationStateChange={handleNavigationStateChange}
          onLoadStart={() => setLoading(true)}
          onLoadEnd={() => setLoading(false)}
        />
      </View>
    </Modal>
  );
};
```

### Step 3: Use Payment Component

```typescript
// screens/PaymentScreen.tsx
import React, { useState } from 'react';
import { View, Button, Text } from 'react-native';
import { PaymentWebView } from '../components/PaymentWebView';
import { EasebuzzPaymentService } from '../services/paymentService';

export const PaymentScreen = ({ route, navigation }) => {
  const { invoice } = route.params;
  const [paymentUrl, setPaymentUrl] = useState('');
  const [showWebView, setShowWebView] = useState(false);
  
  const paymentService = new EasebuzzPaymentService('https://your-erpnext-site.com');
  
  const initiatePayment = async () => {
    try {
      const result = await paymentService.initiatePayment({
        amount: invoice.outstanding_amount,
        reference_doctype: 'Sales Invoice',
        reference_docname: invoice.name,
        payer_email: invoice.customer_email,
        payer_name: invoice.customer,
        description: `Payment for ${invoice.name}`,
        phone: invoice.customer_phone
      });
      
      if (result.success) {
        setPaymentUrl(result.payment_url);
        setShowWebView(true);
      }
    } catch (error) {
      console.error('Payment initiation failed:', error);
    }
  };
  
  const handlePaymentSuccess = (data: any) => {
    setShowWebView(false);
    navigation.navigate('PaymentSuccess', { data });
  };
  
  const handlePaymentFailure = (data: any) => {
    setShowWebView(false);
    navigation.navigate('PaymentFailure', { data });
  };
  
  return (
    <View>
      <Text>Amount: ₹{invoice.outstanding_amount}</Text>
      <Button title="Pay Now" onPress={initiatePayment} />
      
      <PaymentWebView
        visible={showWebView}
        paymentUrl={paymentUrl}
        onSuccess={handlePaymentSuccess}
        onFailure={handlePaymentFailure}
        onClose={() => setShowWebView(false)}
      />
    </View>
  );
};
```

---

## Payment Flow

### Standard Payment Flow

```
1. User initiates payment
   ↓
2. Frontend calls initiate_payment API
   ↓
3. Backend creates Integration Request
   ↓
4. Backend calls Easebuzz API to generate payment link
   ↓
5. Frontend receives payment URL
   ↓
6. User is redirected/shown payment page (iframe/WebView)
   ↓
7. User completes payment on Easebuzz
   ↓
8. Easebuzz calls verify_transaction callback
   ↓
9. Backend processes payment response
   ↓
10. Backend calls on_payment_authorized on reference document
    ↓
11. User is redirected to success/failure page
```

### Hash Verification

Easebuzz uses SHA-512 hash to verify request and response integrity:

**Request Hash:**
```
key|txnid|amount|productinfo|firstname|email|udf1|udf2|udf3|udf4|udf5||||||salt
```

**Response Hash:**
```
salt|status|||||||udf5|udf4|udf3|udf2|udf1|email|firstname|productinfo|amount|txnid|key
```

---

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| Hash mismatch | Invalid salt or data tampering | Verify merchant salt configuration |
| Payment initiation failed | Invalid merchant credentials | Check merchant key and salt |
| Integration request not found | Invalid token | Use correct integration_request_name |
| Missing required parameter | Incomplete payment data | Provide all required fields |

### Error Response Format

```json
{
  "success": false,
  "error": "Error description"
}
```

---

## Testing

### Test Mode Configuration

1. Set Environment to "Test" in Easebuzz Merchant
2. Use test credentials provided by Easebuzz
3. Test URL: `https://testpay.easebuzz.in`

### Test Cards

Easebuzz provides test cards for different scenarios. Refer to Easebuzz documentation for current test card numbers.

### Testing Checklist

- [ ] Payment initiation with valid data
- [ ] Payment initiation with invalid data
- [ ] Successful payment completion
- [ ] Failed payment handling
- [ ] Payment cancellation
- [ ] Hash verification
- [ ] Multi-merchant routing
- [ ] Mobile WebView integration
- [ ] Callback handling
- [ ] Status checking

---

## Configuration in Easebuzz Settings

1. Navigate to **Payment Gateways > Easebuzz Settings**
2. Configure:
   - Merchant Key (default merchant key)
   - Salt (default salt)
   - Environment (Test/Production)
   - Redirect To (external frontend URL for callbacks)
   - Header Image (optional logo for checkout page)

---

## Support

For issues or questions:
- Check error logs in ERPNext (Error Log doctype)
- Review Integration Request documents for payment details
- Contact Easebuzz support for gateway-specific issues
- Refer to Easebuzz API documentation: https://docs.easebuzz.in/

---

## Security Notes

1. **Never expose** merchant key or salt in frontend code
2. Always use **HTTPS** for all API calls
3. **Verify hash** on all responses
4. Store sensitive data in **server-side environment variables**
5. Implement **rate limiting** on payment initiation endpoints
6. Use **signed URLs** with expiration for additional security

---

## Changelog

### Version 1.0.0 (2025-01-27)
- Initial Easebuzz integration
- Multi-merchant support
- API endpoints for initiation and verification
- NextJS/React Native examples
- Hash verification
- WebView/iframe support
