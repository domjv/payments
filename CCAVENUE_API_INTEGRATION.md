# CCAvenue API Integration Guide

Complete guide for integrating CCAvenue payment gateway with NextJS (Web) and React Native (Mobile) applications.

## Table of Contents

1. [Overview](#overview)
2. [Multi-Merchant Configuration](#multi-merchant-configuration)
3. [API Endpoints](#api-endpoints)
4. [NextJS Integration](#nextjs-integration)
5. [React Native Integration](#react-native-integration)
6. [Payment Flow](#payment-flow)
7. [Error Handling](#error-handling)
8. [Testing](#testing)

---

## Overview

The CCAvenue integration has been redesigned to work with external frontend applications (NextJS/React Native) instead of ERPNext webforms. The system now supports:

- **Multi-merchant configuration**: Configure multiple CCAvenue merchants for different companies
- **Default merchant fallback**: Automatic fallback to parent company merchant
- **API-based integration**: RESTful API endpoints for payment initiation and verification
- **WebView support**: Mobile apps can load CCAvenue payment page in WebView
- **Webhook callbacks**: Real-time payment status updates

---

## Multi-Merchant Configuration

### Creating Merchants

1. Navigate to **Payment Gateways > CCAvenue Merchant** in ERPNext
2. Click **New** to create a merchant

#### Merchant Fields

| Field | Description | Required |
|-------|-------------|----------|
| **Merchant Name** | Unique identifier for the merchant (use company name) | Yes |
| **Is Default Merchant** | Mark as default/parent company merchant | No |
| **Merchant ID** | CCAvenue Merchant ID | Yes |
| **Access Code** | CCAvenue Access Code | Yes |
| **Encryption Key** | CCAvenue Encryption Key | Yes |
| **Environment** | Sandbox or Production | Yes |
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
- Merchant ID: 12345
- Access Code: ABCD1234
- Environment: Production

Merchant 2:
- Merchant Name: "IvyLiving Campus B"
- Is Default: No
- Company: IvyLiving Campus B
- Merchant ID: 67890
- Access Code: EFGH5678
- Environment: Production
```

When a payment is initiated:
- For Campus B transactions → Uses Merchant 2
- For Campus A transactions → Uses Merchant 1
- For other transactions → Uses Merchant 1 (default)

---

## API Endpoints

All endpoints are available at: `https://your-erpnext-site.com/api/method/payments.payment_gateways.doctype.ccavenue_settings.ccavenue_settings.<method_name>`

### 1. Initiate Payment

**Endpoint:** `initiate_payment`

**Method:** POST (whitelisted, allows guest)

**Purpose:** Create a payment request and get encrypted data for CCAvenue

#### Request Parameters

```json
{
  "amount": 1000.00,
  "currency": "INR",
  "reference_doctype": "Sales Order",
  "reference_docname": "SO-2025-00001",
  "company": "IvyLiving Campus A",
  "payer_email": "student@example.com",
  "payer_name": "CUST-00001",
  "description": "Payment for hostel fees",
  "custom_merchant_name": "IvyLiving Campus A",  // Optional
  "custom_pincode": "560001",  // Optional
  "custom_state": "Karnataka"  // Optional
}
```

#### Response

```json
{
  "success": true,
  "payment_token": "INT-REQ-2025-00001",
  "encrypted_data": "abc123...xyz789",
  "access_code": "ABCD1234",
  "merchant_id": "12345",
  "merchant_name": "IvyLiving Campus A",
  "api_url": "https://secure.ccavenue.com/transaction/transaction.do?command=initiateTransaction",
  "order_id": "INT-REQ-2025-00001",
  "iframe_url": "https://secure.ccavenue.com/transaction/transaction.do?command=initiateTransaction&merchant_id=12345&encRequest=abc123...&access_code=ABCD1234"
}
```

#### Example cURL

```bash
curl -X POST 'https://your-site.com/api/method/payments.payment_gateways.doctype.ccavenue_settings.ccavenue_settings.initiate_payment' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: token YOUR_API_KEY:YOUR_API_SECRET' \
  -d '{
    "amount": 1000.00,
    "currency": "INR",
    "reference_doctype": "Sales Order",
    "reference_docname": "SO-2025-00001",
    "company": "IvyLiving Campus A",
    "payer_email": "student@example.com",
    "payer_name": "CUST-00001",
    "description": "Payment for hostel fees"
  }'
```

---

### 2. Check Payment Status

**Endpoint:** `check_payment_status`

**Method:** POST/GET (whitelisted, allows guest)

**Purpose:** Check the current status of a payment

#### Request Parameters

```json
{
  "integration_request_name": "INT-REQ-2025-00001"
}
```

#### Response

```json
{
  "success": true,
  "status": "Completed",
  "order_status": "Success",
  "tracking_id": "310007123456",
  "bank_ref_no": "1234567890",
  "payment_mode": "Net Banking",
  "failure_message": null,
  "reference_doctype": "Sales Order",
  "reference_docname": "SO-2025-00001",
  "amount": 1000.00,
  "currency": "INR"
}
```

#### Status Values

| Status | Description |
|--------|-------------|
| `Queued` | Payment initiated, awaiting user action |
| `Authorized` | Payment authorized but not captured |
| `Completed` | Payment successfully completed |
| `Failed` | Payment failed |
| `Cancelled` | Payment cancelled |

---

### 3. Webhook Callback

**Endpoint:** `webhook_callback`

**Method:** POST (whitelisted, allows guest)

**Purpose:** Handle CCAvenue payment callbacks (JSON response)

This endpoint is called by CCAvenue after payment completion. It returns JSON instead of redirecting.

#### Response

```json
{
  "success": true,
  "status": "Completed",
  "tracking_id": "310007123456",
  "order_status": "Success",
  "reference_doctype": "Sales Order",
  "reference_docname": "SO-2025-00001",
  "redirect_to": "/app/sales-order/SO-2025-00001"
}
```

---

### 4. Verify Transaction (Legacy + API Mode)

**Endpoint:** `verify_transaction`

**Method:** POST (whitelisted, allows guest)

**Purpose:** Handle CCAvenue callbacks with redirect or JSON response

#### Request Parameters

```json
{
  "return_json": true  // Optional: Set to true for JSON response
}
```

This endpoint supports both redirect (legacy) and JSON response modes.

---

## NextJS Integration

### Installation

```bash
npm install axios
```

### Step 1: Create Payment Service

Create `services/payment.service.ts`:

```typescript
import axios from 'axios';

const ERPNEXT_API_URL = process.env.NEXT_PUBLIC_ERPNEXT_URL;
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;
const API_SECRET = process.env.NEXT_PUBLIC_API_SECRET;

interface PaymentInitRequest {
  amount: number;
  currency?: string;
  reference_doctype: string;
  reference_docname: string;
  company?: string;
  payer_email: string;
  payer_name: string;
  description: string;
  custom_merchant_name?: string;
}

interface PaymentInitResponse {
  success: boolean;
  payment_token: string;
  iframe_url: string;
  encrypted_data: string;
  access_code: string;
  merchant_id: string;
  api_url: string;
  order_id: string;
}

interface PaymentStatusResponse {
  success: boolean;
  status: string;
  order_status: string;
  tracking_id?: string;
  bank_ref_no?: string;
  payment_mode?: string;
  failure_message?: string;
}

export class PaymentService {
  private axiosInstance;

  constructor() {
    this.axiosInstance = axios.create({
      baseURL: ERPNEXT_API_URL,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `token ${API_KEY}:${API_SECRET}`
      }
    });
  }

  async initiatePayment(data: PaymentInitRequest): Promise<PaymentInitResponse> {
    const response = await this.axiosInstance.post(
      '/api/method/payments.payment_gateways.doctype.ccavenue_settings.ccavenue_settings.initiate_payment',
      data
    );
    return response.data.message;
  }

  async checkPaymentStatus(paymentToken: string): Promise<PaymentStatusResponse> {
    const response = await this.axiosInstance.post(
      '/api/method/payments.payment_gateways.doctype.ccavenue_settings.ccavenue_settings.check_payment_status',
      { integration_request_name: paymentToken }
    );
    return response.data.message;
  }
}

export const paymentService = new PaymentService();
```

### Step 2: Create Payment Component

Create `components/PaymentGateway.tsx`:

```typescript
'use client';

import React, { useState, useEffect } from 'react';
import { paymentService } from '@/services/payment.service';

interface PaymentGatewayProps {
  amount: number;
  orderId: string;
  orderType: string;
  customerEmail: string;
  customerId: string;
  company?: string;
  onSuccess: (data: any) => void;
  onError: (error: any) => void;
}

export const PaymentGateway: React.FC<PaymentGatewayProps> = ({
  amount,
  orderId,
  orderType,
  customerEmail,
  customerId,
  company,
  onSuccess,
  onError
}) => {
  const [iframeUrl, setIframeUrl] = useState<string | null>(null);
  const [paymentToken, setPaymentToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const initiatePayment = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await paymentService.initiatePayment({
        amount: amount,
        currency: 'INR',
        reference_doctype: orderType,
        reference_docname: orderId,
        company: company,
        payer_email: customerEmail,
        payer_name: customerId,
        description: `Payment for ${orderType} ${orderId}`
      });

      if (response.success) {
        setIframeUrl(response.iframe_url);
        setPaymentToken(response.payment_token);
        // Start polling for payment status
        startStatusPolling(response.payment_token);
      } else {
        throw new Error('Failed to initiate payment');
      }
    } catch (err: any) {
      setError(err.message);
      onError(err);
    } finally {
      setIsLoading(false);
    }
  };

  const startStatusPolling = (token: string) => {
    const pollInterval = setInterval(async () => {
      try {
        const status = await paymentService.checkPaymentStatus(token);
        
        if (status.status === 'Completed') {
          clearInterval(pollInterval);
          onSuccess(status);
        } else if (status.status === 'Failed') {
          clearInterval(pollInterval);
          onError(new Error(status.failure_message || 'Payment failed'));
        }
      } catch (err) {
        console.error('Error checking payment status:', err);
      }
    }, 3000); // Poll every 3 seconds

    // Stop polling after 10 minutes
    setTimeout(() => clearInterval(pollInterval), 600000);
  };

  useEffect(() => {
    initiatePayment();
  }, []);

  if (isLoading) {
    return (
      <div className="flex justify-center items-center h-screen">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex justify-center items-center h-screen">
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
          <p className="font-bold">Payment Error</p>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full h-screen">
      {iframeUrl && (
        <iframe
          src={iframeUrl}
          className="w-full h-full border-0"
          title="CCAvenue Payment Gateway"
          sandbox="allow-forms allow-scripts allow-same-origin allow-top-navigation"
        />
      )}
    </div>
  );
};
```

### Step 3: Create Payment Page

Create `app/payment/page.tsx`:

```typescript
'use client';

import { useSearchParams } from 'next/navigation';
import { PaymentGateway } from '@/components/PaymentGateway';

export default function PaymentPage() {
  const searchParams = useSearchParams();
  
  const amount = parseFloat(searchParams.get('amount') || '0');
  const orderId = searchParams.get('order_id') || '';
  const orderType = searchParams.get('order_type') || 'Sales Order';
  const customerEmail = searchParams.get('email') || '';
  const customerId = searchParams.get('customer') || '';
  const company = searchParams.get('company') || undefined;

  const handleSuccess = (data: any) => {
    console.log('Payment successful:', data);
    // Redirect to success page
    window.location.href = `/payment-success?tracking_id=${data.tracking_id}`;
  };

  const handleError = (error: any) => {
    console.error('Payment error:', error);
    // Redirect to failure page
    window.location.href = '/payment-failed';
  };

  return (
    <PaymentGateway
      amount={amount}
      orderId={orderId}
      orderType={orderType}
      customerEmail={customerEmail}
      customerId={customerId}
      company={company}
      onSuccess={handleSuccess}
      onError={handleError}
    />
  );
}
```

### Step 4: Usage

```typescript
// In your cart or checkout component
const handleCheckout = () => {
  const paymentUrl = `/payment?` + new URLSearchParams({
    amount: totalAmount.toString(),
    order_id: orderId,
    order_type: 'Sales Order',
    email: userEmail,
    customer: customerId,
    company: selectedCompany
  }).toString();
  
  router.push(paymentUrl);
};
```

---

## React Native Integration

### Installation

```bash
npm install axios react-native-webview @react-navigation/native
```

### Step 1: Create Payment Service

Create `services/PaymentService.ts`:

```typescript
import axios from 'axios';

const ERPNEXT_API_URL = 'https://your-erpnext-site.com';
const API_KEY = 'your_api_key';
const API_SECRET = 'your_api_secret';

interface PaymentInitRequest {
  amount: number;
  currency?: string;
  reference_doctype: string;
  reference_docname: string;
  company?: string;
  payer_email: string;
  payer_name: string;
  description: string;
}

export class PaymentService {
  private axiosInstance;

  constructor() {
    this.axiosInstance = axios.create({
      baseURL: ERPNEXT_API_URL,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `token ${API_KEY}:${API_SECRET}`
      }
    });
  }

  async initiatePayment(data: PaymentInitRequest) {
    try {
      const response = await this.axiosInstance.post(
        '/api/method/payments.payment_gateways.doctype.ccavenue_settings.ccavenue_settings.initiate_payment',
        data
      );
      return response.data.message;
    } catch (error) {
      throw error;
    }
  }

  async checkPaymentStatus(paymentToken: string) {
    try {
      const response = await this.axiosInstance.post(
        '/api/method/payments.payment_gateways.doctype.ccavenue_settings.ccavenue_settings.check_payment_status',
        { integration_request_name: paymentToken }
      );
      return response.data.message;
    } catch (error) {
      throw error;
    }
  }
}

export default new PaymentService();
```

### Step 2: Create Payment Screen

Create `screens/PaymentScreen.tsx`:

```typescript
import React, { useState, useEffect, useRef } from 'react';
import { View, ActivityIndicator, StyleSheet, Alert } from 'react-native';
import { WebView } from 'react-native-webview';
import PaymentService from '../services/PaymentService';

interface PaymentScreenProps {
  route: {
    params: {
      amount: number;
      orderId: string;
      orderType: string;
      customerEmail: string;
      customerId: string;
      company?: string;
    };
  };
  navigation: any;
}

const PaymentScreen: React.FC<PaymentScreenProps> = ({ route, navigation }) => {
  const { amount, orderId, orderType, customerEmail, customerId, company } = route.params;
  
  const [iframeUrl, setIframeUrl] = useState<string | null>(null);
  const [paymentToken, setPaymentToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    initiatePayment();
    
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
    };
  }, []);

  const initiatePayment = async () => {
    try {
      const response = await PaymentService.initiatePayment({
        amount,
        currency: 'INR',
        reference_doctype: orderType,
        reference_docname: orderId,
        company,
        payer_email: customerEmail,
        payer_name: customerId,
        description: `Payment for ${orderType} ${orderId}`
      });

      if (response.success) {
        setIframeUrl(response.iframe_url);
        setPaymentToken(response.payment_token);
        setIsLoading(false);
        startStatusPolling(response.payment_token);
      }
    } catch (error) {
      Alert.alert('Error', 'Failed to initiate payment');
      navigation.goBack();
    }
  };

  const startStatusPolling = (token: string) => {
    pollingIntervalRef.current = setInterval(async () => {
      try {
        const status = await PaymentService.checkPaymentStatus(token);
        
        if (status.status === 'Completed') {
          if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current);
          }
          navigation.replace('PaymentSuccess', { 
            trackingId: status.tracking_id,
            orderId: orderId 
          });
        } else if (status.status === 'Failed') {
          if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current);
          }
          navigation.replace('PaymentFailed', { 
            message: status.failure_message 
          });
        }
      } catch (error) {
        console.error('Error checking payment status:', error);
      }
    }, 3000);

    // Stop polling after 10 minutes
    setTimeout(() => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
    }, 600000);
  };

  const handleWebViewNavigationStateChange = (navState: any) => {
    // Handle any URL changes if needed
    console.log('Navigation state changed:', navState.url);
  };

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#0000ff" />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {iframeUrl && (
        <WebView
          source={{ uri: iframeUrl }}
          style={styles.webview}
          onNavigationStateChange={handleWebViewNavigationStateChange}
          javaScriptEnabled={true}
          domStorageEnabled={true}
          startInLoadingState={true}
          renderLoading={() => (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="large" color="#0000ff" />
            </View>
          )}
        />
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  webview: {
    flex: 1,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
});

export default PaymentScreen;
```

### Step 3: Navigate to Payment Screen

```typescript
// In your cart or checkout screen
import { useNavigation } from '@react-navigation/native';

const navigation = useNavigation();

const handleCheckout = () => {
  navigation.navigate('Payment', {
    amount: totalAmount,
    orderId: orderId,
    orderType: 'Sales Order',
    customerEmail: userEmail,
    customerId: customerId,
    company: selectedCompany
  });
};
```

---

## Payment Flow

### Complete Payment Flow Diagram

```
┌─────────────┐
│   Frontend  │
│  (NextJS /  │
│   React     │
│   Native)   │
└──────┬──────┘
       │
       │ 1. Call initiate_payment API
       │    with payment details
       │
       v
┌─────────────────────────────┐
│  ERPNext Backend            │
│  - Create Integration Req   │
│  - Select Merchant          │
│  - Calculate Charges        │
│  - Encrypt Payment Data     │
└──────┬──────────────────────┘
       │
       │ 2. Return iframe_url
       │    and payment_token
       │
       v
┌─────────────┐
│   Frontend  │
│   Display   │
│   CCAvenue  │
│   in iFrame │
│   /WebView  │
└──────┬──────┘
       │
       │ 3. User completes payment
       │
       v
┌─────────────────┐
│   CCAvenue      │
│   Payment Page  │
└──────┬──────────┘
       │
       │ 4. Redirect to callback URL
       │    with encrypted response
       │
       v
┌─────────────────────────────┐
│  ERPNext Backend            │
│  verify_transaction /       │
│  webhook_callback           │
│  - Decrypt response         │
│  - Update Integration Req   │
│  - Trigger on_payment_      │
│    authorized hook          │
└──────┬──────────────────────┘
       │
       │ 5. Redirect/Return JSON
       │
       v
┌─────────────┐
│   Frontend  │
│   Poll for  │
│   status    │
│   using     │
│   check_    │
│   payment_  │
│   status    │
└──────┬──────┘
       │
       │ 6. Display success/failure
       │
       v
┌─────────────┐
│   Success/  │
│   Failure   │
│   Page      │
└─────────────┘
```

### Detailed Steps

1. **Payment Initiation**
   - Frontend calls `initiate_payment` API
   - Backend creates Integration Request
   - Selects appropriate merchant (company-specific or default)
   - Calculates payment charges
   - Encrypts payment data using merchant's encryption key
   - Returns iframe URL and payment token

2. **Payment Page Display**
   - Frontend loads CCAvenue payment page in iframe (NextJS) or WebView (React Native)
   - User enters payment details
   - User completes payment on CCAvenue

3. **Payment Callback**
   - CCAvenue redirects to `verify_transaction` or `webhook_callback`
   - Backend decrypts CCAvenue response
   - Updates Integration Request with payment status
   - Triggers `on_payment_authorized` hook on reference document

4. **Status Polling**
   - Frontend polls `check_payment_status` every 3 seconds
   - Stops when status is `Completed` or `Failed`
   - Maximum polling duration: 10 minutes

5. **Success/Failure Handling**
   - Frontend receives final status
   - Redirects to appropriate success/failure page
   - Displays payment details (tracking ID, amount, etc.)

---

## Error Handling

### Common Error Scenarios

#### 1. Payment Initiation Errors

```typescript
try {
  const response = await paymentService.initiatePayment(data);
} catch (error) {
  if (error.response?.status === 401) {
    // Authentication error
    console.error('Invalid API credentials');
  } else if (error.response?.status === 404) {
    // Merchant not found
    console.error('No merchant configuration found');
  } else if (error.response?.data?.message) {
    // Backend error
    console.error(error.response.data.message);
  } else {
    // Network error
    console.error('Network error');
  }
}
```

#### 2. Payment Status Errors

```typescript
const status = await paymentService.checkPaymentStatus(token);

if (!status.success) {
  // Payment request not found or error
  console.error(status.error);
}

if (status.status === 'Failed') {
  // Payment failed
  console.error('Payment failed:', status.failure_message);
}
```

#### 3. Timeout Handling

```typescript
const checkPaymentWithTimeout = async (token: string, timeoutMs: number = 600000) => {
  return Promise.race([
    paymentService.checkPaymentStatus(token),
    new Promise((_, reject) => 
      setTimeout(() => reject(new Error('Payment check timeout')), timeoutMs)
    )
  ]);
};
```

### Error Response Format

All API endpoints return errors in this format:

```json
{
  "success": false,
  "error": "Error message description"
}
```

---

## Testing

### Test Credentials

For Sandbox environment, use CCAvenue's test credentials:

```
Merchant ID: Test_Merchant_ID
Access Code: Test_Access_Code
Encryption Key: Test_Encryption_Key
Environment: Sandbox
```

### Test Cards (CCAvenue Sandbox)

| Card Number | CVV | Expiry | Result |
|-------------|-----|--------|--------|
| 4111111111111111 | 123 | Any future date | Success |
| 4111111111111112 | 123 | Any future date | Failure |

### Manual Testing Checklist

- [ ] Create CCAvenue Merchant with test credentials
- [ ] Mark one merchant as default
- [ ] Create payment request via `initiate_payment` API
- [ ] Verify iframe URL is returned
- [ ] Load iframe in browser/WebView
- [ ] Complete test payment
- [ ] Verify callback is received
- [ ] Check Integration Request status in ERPNext
- [ ] Poll `check_payment_status` API
- [ ] Verify success/failure handling

### Automated Testing

Create test file `__tests__/payment.test.ts`:

```typescript
import { paymentService } from '@/services/payment.service';

describe('Payment Service', () => {
  it('should initiate payment successfully', async () => {
    const response = await paymentService.initiatePayment({
      amount: 100,
      currency: 'INR',
      reference_doctype: 'Sales Order',
      reference_docname: 'SO-TEST-001',
      payer_email: 'test@example.com',
      payer_name: 'CUST-001',
      description: 'Test payment'
    });

    expect(response.success).toBe(true);
    expect(response.payment_token).toBeDefined();
    expect(response.iframe_url).toBeDefined();
  });

  it('should check payment status', async () => {
    const token = 'INT-REQ-2025-00001';
    const status = await paymentService.checkPaymentStatus(token);

    expect(status.success).toBe(true);
    expect(status.status).toBeDefined();
  });
});
```

---

## Troubleshooting

### Issue: "No merchant configuration found"

**Solution:** 
1. Check if at least one CCAvenue Merchant exists
2. Verify one merchant is marked as default
3. Check company field matches the company in payment request

### Issue: Payment iframe not loading

**Solution:**
1. Verify iframe_url is valid
2. Check CORS settings on ERPNext
3. Ensure encryption key is correct
4. Check browser console for errors

### Issue: Payment callback not received

**Solution:**
1. Verify redirect_url is accessible
2. Check CCAvenue merchant configuration
3. Review ERPNext error logs
4. Ensure webhook_callback endpoint is whitelisted

### Issue: Status polling shows "Queued" indefinitely

**Solution:**
1. Check if CCAvenue callback was received
2. Review Integration Request in ERPNext
3. Manually trigger callback for testing
4. Check for network/firewall issues

---

## Security Best Practices

1. **API Keys**: Store API keys in environment variables, never in code
2. **HTTPS**: Always use HTTPS for production
3. **Token Validation**: Validate payment tokens on backend before processing
4. **Amount Verification**: Verify payment amount on backend, don't trust frontend
5. **Session Management**: Implement proper session handling for authenticated users
6. **Rate Limiting**: Implement rate limiting on API endpoints
7. **Error Messages**: Don't expose sensitive information in error messages

---

## Support

For issues or questions:
- Review ERPNext error logs: Desk > Error Log
- Check Integration Request: Payment Gateways > Integration Request
- Review CCAvenue Merchant configuration
- Check CCAvenue dashboard for transaction logs

---

## Changelog

### Version 1.1.0 (2025-12-30)
- Added multi-merchant support
- Added API endpoints for frontend/mobile integration
- Deprecated ERPNext webform checkout
- Added comprehensive documentation
- Fixed customer reference handling
- Added automatic merchant selection

---

## License

MIT License - See license.txt
