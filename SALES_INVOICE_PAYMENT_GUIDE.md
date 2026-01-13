# Sales Invoice Payment Integration Guide

This guide shows how to implement CCAvenue payment for Sales Invoices in your NextJS/React Native app.

## Overview

The implementation automatically:
- ✅ Creates Integration Request when payment is initiated
- ✅ Selects appropriate merchant based on company
- ✅ Creates Payment Entry when payment succeeds
- ✅ Links Payment Entry to Sales Invoice
- ✅ Updates Sales Invoice outstanding amount

## Backend Setup (Already Done!)

The following files have been created:

1. **`payments/overrides/sales_invoice.py`** - Sales Invoice override with `on_payment_authorized` method
2. **`payments/hooks.py`** - Updated to register the Sales Invoice override

### How It Works

```python
Sales Invoice.on_payment_authorized("Completed")
    ↓
Get Integration Request (payment details)
    ↓
Get Merchant Configuration (bank accounts)
    ↓
Create Payment Entry
    ↓
Link to Sales Invoice
    ↓
Submit Payment Entry
    ↓
Sales Invoice outstanding updated automatically
```

## Frontend Implementation

### Option 1: NextJS Implementation

#### Step 1: Create Payment Hook

Create `hooks/usePayment.ts`:

```typescript
import { useState } from 'react';
import axios from 'axios';

const ERPNEXT_URL = process.env.NEXT_PUBLIC_ERPNEXT_URL;
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;
const API_SECRET = process.env.NEXT_PUBLIC_API_SECRET;

export interface SalesInvoice {
  name: string;
  customer: string;
  customer_name: string;
  company: string;
  outstanding_amount: number;
  currency: string;
  contact_email?: string;
  custom_pincode?: string;
  custom_state?: string;
}

export const usePayment = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const initiatePayment = async (salesInvoice: SalesInvoice) => {
    setLoading(true);
    setError(null);

    try {
      // Step 1: Initiate payment with CCAvenue
      const response = await axios.post(
        `${ERPNEXT_URL}/api/method/payments.payment_gateways.doctype.ccavenue_settings.ccavenue_settings.initiate_payment`,
        {
          amount: salesInvoice.outstanding_amount,
          currency: salesInvoice.currency,
          reference_doctype: 'Sales Invoice',
          reference_docname: salesInvoice.name,
          company: salesInvoice.company,
          payer_email: salesInvoice.contact_email || '',
          payer_name: salesInvoice.customer,
          description: `Payment for Invoice ${salesInvoice.name}`
        },
        {
          headers: {
            'Authorization': `token ${API_KEY}:${API_SECRET}`,
            'Content-Type': 'application/json'
          }
        }
      );

      const data = response.data.message;

      if (!data.success) {
        throw new Error(data.error || 'Failed to initiate payment');
      }

      return {
        success: true,
        paymentToken: data.payment_token,
        iframeUrl: data.iframe_url
      };

    } catch (err: any) {
      const errorMessage = err.response?.data?.message || err.message || 'Unknown error';
      setError(errorMessage);
      return {
        success: false,
        error: errorMessage
      };
    } finally {
      setLoading(false);
    }
  };

  const checkPaymentStatus = async (paymentToken: string) => {
    try {
      const response = await axios.post(
        `${ERPNEXT_URL}/api/method/payments.payment_gateways.doctype.ccavenue_settings.ccavenue_settings.check_payment_status`,
        { integration_request_name: paymentToken },
        {
          headers: {
            'Authorization': `token ${API_KEY}:${API_SECRET}`,
            'Content-Type': 'application/json'
          }
        }
      );

      return response.data.message;
    } catch (err) {
      console.error('Error checking payment status:', err);
      return null;
    }
  };

  return {
    initiatePayment,
    checkPaymentStatus,
    loading,
    error
  };
};
```

#### Step 2: Create Payment Component

Create `components/InvoicePayment.tsx`:

```typescript
'use client';

import React, { useState, useEffect } from 'react';
import { usePayment, SalesInvoice } from '@/hooks/usePayment';

interface InvoicePaymentProps {
  invoice: SalesInvoice;
  onSuccess: (trackingId: string) => void;
  onError: (error: string) => void;
}

export const InvoicePayment: React.FC<InvoicePaymentProps> = ({
  invoice,
  onSuccess,
  onError
}) => {
  const { initiatePayment, checkPaymentStatus, loading, error } = usePayment();
  const [iframeUrl, setIframeUrl] = useState<string | null>(null);
  const [paymentToken, setPaymentToken] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);

  useEffect(() => {
    startPayment();
  }, []);

  const startPayment = async () => {
    const result = await initiatePayment(invoice);

    if (result.success && result.iframeUrl && result.paymentToken) {
      setIframeUrl(result.iframeUrl);
      setPaymentToken(result.paymentToken);
      startPolling(result.paymentToken);
    } else {
      onError(result.error || 'Failed to initiate payment');
    }
  };

  const startPolling = (token: string) => {
    setPolling(true);

    const pollInterval = setInterval(async () => {
      const status = await checkPaymentStatus(token);

      if (status?.status === 'Completed') {
        clearInterval(pollInterval);
        setPolling(false);
        onSuccess(status.tracking_id);
      } else if (status?.status === 'Failed') {
        clearInterval(pollInterval);
        setPolling(false);
        onError(status.failure_message || 'Payment failed');
      }
    }, 3000); // Poll every 3 seconds

    // Stop polling after 10 minutes
    setTimeout(() => {
      clearInterval(pollInterval);
      setPolling(false);
    }, 600000);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Initiating payment...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 max-w-md">
          <h3 className="text-red-800 font-semibold text-lg mb-2">Payment Error</h3>
          <p className="text-red-600">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full h-screen flex flex-col">
      <div className="bg-blue-600 text-white p-4">
        <h2 className="text-xl font-semibold">
          Payment for Invoice {invoice.name}
        </h2>
        <p className="text-sm mt-1">
          Amount: {invoice.currency} {invoice.outstanding_amount.toFixed(2)}
        </p>
      </div>
      
      {iframeUrl && (
        <iframe
          src={iframeUrl}
          className="flex-1 w-full border-0"
          title="CCAvenue Payment Gateway"
          sandbox="allow-forms allow-scripts allow-same-origin allow-top-navigation"
        />
      )}
      
      {polling && (
        <div className="bg-yellow-50 border-t border-yellow-200 p-2 text-center">
          <p className="text-sm text-yellow-800">
            Processing payment... Please wait
          </p>
        </div>
      )}
    </div>
  );
};
```

#### Step 3: Create Payment Page

Create `app/invoice/[id]/pay/page.tsx`:

```typescript
'use client';

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { InvoicePayment } from '@/components/InvoicePayment';
import axios from 'axios';

const ERPNEXT_URL = process.env.NEXT_PUBLIC_ERPNEXT_URL;
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;
const API_SECRET = process.env.NEXT_PUBLIC_API_SECRET;

export default function InvoicePaymentPage() {
  const router = useRouter();
  const params = useParams();
  const invoiceId = params.id as string;
  
  const [invoice, setInvoice] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchInvoice();
  }, [invoiceId]);

  const fetchInvoice = async () => {
    try {
      const response = await axios.get(
        `${ERPNEXT_URL}/api/resource/Sales Invoice/${invoiceId}`,
        {
          headers: {
            'Authorization': `token ${API_KEY}:${API_SECRET}`
          }
        }
      );

      const data = response.data.data;
      
      if (data.outstanding_amount <= 0) {
        setError('This invoice has no outstanding amount');
        return;
      }

      setInvoice(data);
    } catch (err) {
      setError('Failed to load invoice');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handlePaymentSuccess = (trackingId: string) => {
    router.push(`/invoice/${invoiceId}/payment-success?tracking_id=${trackingId}`);
  };

  const handlePaymentError = (error: string) => {
    router.push(`/invoice/${invoiceId}/payment-failed?error=${encodeURIComponent(error)}`);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (error || !invoice) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="bg-red-50 border border-red-200 rounded-lg p-6">
          <p className="text-red-600">{error || 'Invoice not found'}</p>
        </div>
      </div>
    );
  }

  return (
    <InvoicePayment
      invoice={invoice}
      onSuccess={handlePaymentSuccess}
      onError={handlePaymentError}
    />
  );
}
```

#### Step 4: Usage

```typescript
// In your invoice list or detail page
import Link from 'next/link';

const InvoiceCard = ({ invoice }) => {
  return (
    <div className="border rounded-lg p-4">
      <h3>{invoice.name}</h3>
      <p>Outstanding: {invoice.currency} {invoice.outstanding_amount}</p>
      
      {invoice.outstanding_amount > 0 && (
        <Link 
          href={`/invoice/${invoice.name}/pay`}
          className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
        >
          Pay Now
        </Link>
      )}
    </div>
  );
};
```

---

## React Native Implementation

Create `screens/InvoicePaymentScreen.tsx`:

```typescript
import React, { useState, useEffect, useRef } from 'react';
import { View, ActivityIndicator, StyleSheet, Alert } from 'react-native';
import { WebView } from 'react-native-webview';
import axios from 'axios';

const ERPNEXT_URL = 'https://your-erpnext-site.com';
const API_KEY = 'your_api_key';
const API_SECRET = 'your_api_secret';

const InvoicePaymentScreen = ({ route, navigation }) => {
  const { invoice } = route.params;
  
  const [iframeUrl, setIframeUrl] = useState(null);
  const [loading, setLoading] = useState(true);
  const [paymentToken, setPaymentToken] = useState(null);
  const pollingInterval = useRef(null);

  useEffect(() => {
    initiatePayment();
    
    return () => {
      if (pollingInterval.current) {
        clearInterval(pollingInterval.current);
      }
    };
  }, []);

  const initiatePayment = async () => {
    try {
      const response = await axios.post(
        `${ERPNEXT_URL}/api/method/payments.payment_gateways.doctype.ccavenue_settings.ccavenue_settings.initiate_payment`,
        {
          amount: invoice.outstanding_amount,
          currency: invoice.currency,
          reference_doctype: 'Sales Invoice',
          reference_docname: invoice.name,
          company: invoice.company,
          payer_email: invoice.contact_email || '',
          payer_name: invoice.customer,
          description: `Payment for Invoice ${invoice.name}`
        },
        {
          headers: {
            'Authorization': `token ${API_KEY}:${API_SECRET}`,
            'Content-Type': 'application/json'
          }
        }
      );

      const data = response.data.message;

      if (data.success) {
        setIframeUrl(data.iframe_url);
        setPaymentToken(data.payment_token);
        setLoading(false);
        startPolling(data.payment_token);
      } else {
        Alert.alert('Error', data.error || 'Failed to initiate payment');
        navigation.goBack();
      }
    } catch (error) {
      Alert.alert('Error', 'Failed to initiate payment');
      navigation.goBack();
    }
  };

  const startPolling = (token) => {
    pollingInterval.current = setInterval(async () => {
      try {
        const response = await axios.post(
          `${ERPNEXT_URL}/api/method/payments.payment_gateways.doctype.ccavenue_settings.ccavenue_settings.check_payment_status`,
          { integration_request_name: token },
          {
            headers: {
              'Authorization': `token ${API_KEY}:${API_SECRET}`,
              'Content-Type': 'application/json'
            }
          }
        );

        const status = response.data.message;

        if (status.status === 'Completed') {
          clearInterval(pollingInterval.current);
          navigation.replace('PaymentSuccess', {
            trackingId: status.tracking_id,
            invoice: invoice
          });
        } else if (status.status === 'Failed') {
          clearInterval(pollingInterval.current);
          navigation.replace('PaymentFailed', {
            error: status.failure_message
          });
        }
      } catch (error) {
        console.error('Error checking payment status:', error);
      }
    }, 3000);

    // Stop polling after 10 minutes
    setTimeout(() => {
      if (pollingInterval.current) {
        clearInterval(pollingInterval.current);
      }
    }, 600000);
  };

  if (loading) {
    return (
      <View style={styles.loading}>
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
          javaScriptEnabled={true}
          domStorageEnabled={true}
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
  loading: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
});

export default InvoicePaymentScreen;
```

---

## What Happens After Payment

When payment is successful:

1. ✅ CCAvenue calls `verify_transaction` endpoint
2. ✅ Integration Request status updated to "Completed"
3. ✅ `sales_invoice.on_payment_authorized("Completed")` is called
4. ✅ Payment Entry is created automatically with:
   - Reference to Sales Invoice
   - Tracking ID from CCAvenue
   - Correct merchant bank accounts
   - Proper debtors account
5. ✅ Payment Entry is submitted
6. ✅ Sales Invoice outstanding amount is updated

The **Payment Entry is created and linked automatically** - no manual intervention needed!

---

## Testing

1. Create a Sales Invoice in ERPNext
2. Note the invoice name and outstanding amount
3. From your app, navigate to the payment page
4. Complete payment on CCAvenue (use test cards)
5. Verify:
   - ✅ Integration Request status is "Completed"
   - ✅ Payment Entry is created and submitted
   - ✅ Payment Entry is linked to Sales Invoice
   - ✅ Sales Invoice outstanding is reduced/zero

---

## Troubleshooting

### Payment Entry not created

1. Check Error Log in ERPNext for "CCAvenue Payment Entry Creation Error"
2. Verify accounts exist (bank account, debtors account)
3. Check if user has permissions to create Payment Entry

### Wrong accounts used

1. Verify CCAvenue Merchant configuration
2. Check if `bank_account` and `debtors_account` fields are set
3. Ensure accounts exist with company abbreviation

### Payment shows completed but entry not created

1. Check if `on_payment_authorized` method was called (check logs)
2. Verify Sales Invoice override is registered in hooks
3. Restart ERPNext: `bench restart`

---

## Summary

✅ **No Payment Request needed** - Direct Sales Invoice payment  
✅ **Automatic Payment Entry** - Created when payment succeeds  
✅ **Multi-merchant support** - Different accounts per company  
✅ **Clean integration** - Just call `initiate_payment` API  
✅ **Complete tracking** - Integration Request + Payment Entry linked  

You're all set! 🎉
