# Cashfree Settings

Cashfree Payment Gateway integration for ERPNext.

## Features

- ✅ Multiple Cashfree accounts per site (one per company/hostel)
- ✅ Default account fallback
- ✅ Sandbox and Production environments
- ✅ Invoice payments
- ✅ Shopping cart checkout
- ✅ Payment links via email
- ✅ Webhook support for real-time status updates
- ✅ Guest payments (onboarding flow)

## Setup Instructions

### 1. Install Cashfree SDK

The Cashfree SDK is automatically installed when you install/update the payments app:

```bash
bench install-app payments
# or
bench update
```

To install manually for testing:
```bash
bench pip install cashfree_pg
```

### 2. Create Cashfree Settings

1. Go to **Payment Gateways > Cashfree Settings**
2. Create a new record
3. Fill in the required fields:
   - **Payment Gateway Name**: Unique name (e.g., "Cashfree-Hostel1")
   - **Company**: Select the company/hostel this account belongs to
   - **Is Default**: Check if this should be the site-wide default
   - **Environment**: Select "Sandbox" for testing or "Production" for live
   - **Client ID**: Your Cashfree App ID
   - **Client Secret**: Your Cashfree Secret Key
4. Save

The system will:
- Validate your credentials
- Create a Payment Gateway record
- Generate a webhook URL

### 3. Configure Webhooks in Cashfree Dashboard

1. Login to your [Cashfree Dashboard](https://merchant.cashfree.com/)
2. Go to **Developers > Webhooks**
3. Copy the **Webhook URL** from your Cashfree Settings
4. Add this URL in Cashfree Dashboard
5. Subscribe to these events:
   - `PAYMENT_SUCCESS_WEBHOOK`
   - `PAYMENT_FAILED_WEBHOOK`

### 4. Test the Integration

**Test in Sandbox:**
1. Create a test Sales Invoice
2. Click "Get Payment" or use Payment Request
3. Complete payment using Cashfree test credentials
4. Check that payment status is updated

**Test Payment Links:**
```python
# In server script or console
from payments.payment_gateways.doctype.cashfree_settings.cashfree_settings import CashfreeSettings

settings = CashfreeSettings.get_cashfree_settings_by_company("Hostel 1")
link = settings.create_payment_link(
    amount=5000,
    currency="INR",
    payer_name="John Doe",
    payer_email="john@example.com",
    payer_phone="9999999999",
    title="Admission Fee",
    description="Hostel admission fee for 2025",
    send_email=True
)
print(link["link_url"])
```

## Company-Specific Accounts

The system automatically selects the correct Cashfree account:

1. **If company is specified**: Uses that company's Cashfree Settings
2. **If no company match**: Uses the default Cashfree Settings (is_default = 1)
3. **If no default**: Uses the first available Cashfree Settings

Example:
```python
# Payment for Hostel 1 uses Hostel 1's Cashfree account
payment_details = {
    "amount": 10000,
    "currency": "INR",
    "company": "Hostel 1",  # ← This determines which account to use
    "reference_doctype": "Sales Invoice",
    "reference_docname": "INV-001",
    ...
}
```

## Supported Currencies

- INR (Indian Rupee)
- USD (US Dollar)
- GBP (British Pound)
- EUR (Euro)
- CAD (Canadian Dollar)
- AUD (Australian Dollar)
- SGD (Singapore Dollar)
- AED (UAE Dirham)
- MYR (Malaysian Ringgit)

## Usage in Code

### Invoice Payment
```python
# In your Sales Invoice doctype
def on_payment_authorized(self, status):
    """Called when payment is authorized"""
    if status == "Completed":
        # Create Payment Entry
        self.create_payment_entry()
        self.save()
```

### Shopping Cart
The payment gateway integrates automatically with ERPNext Shopping Cart.

### Payment Links (Email)
```python
# Create and send payment link
settings = CashfreeSettings.get_cashfree_settings_by_company(company)
link = settings.create_payment_link(
    amount=amount,
    currency="INR",
    payer_name=customer_name,
    payer_email=customer_email,
    payer_phone=customer_phone,
    title=title,
    description=description,
    send_email=True,  # Cashfree will send email
    send_sms=False
)
```

## Troubleshooting

### Webhook Not Received
1. Check webhook URL in Cashfree Dashboard matches Cashfree Settings
2. Ensure your site is accessible from internet (not localhost)
3. Check Error Log in ERPNext for webhook errors
4. Use ngrok for local testing:
   ```bash
   ngrok http 8000
   # Use the ngrok URL in Cashfree Dashboard
   ```

### Payment Not Processing
1. Check Integration Request status
2. Verify credentials (Client ID and Secret)
3. Check environment setting (Sandbox vs Production)
4. Review Error Log for detailed errors

### Credentials Invalid
1. Double-check Client ID and Secret from Cashfree Dashboard
2. Ensure environment matches (Sandbox credentials don't work in Production)
3. Check if API keys are active

## API Reference

### CashfreeSettings Methods

- `validate_transaction_currency(currency)` - Check if currency is supported
- `get_payment_url(**kwargs)` - Generate payment URL for checkout
- `create_order(**kwargs)` - Create Cashfree order
- `create_payment_link(**kwargs)` - Create payment link for email
- `get_cashfree_settings_by_company(company)` - Get settings for specific company

### Webhook Endpoint

- **URL**: `/api/method/payments.payment_gateways.doctype.cashfree_settings.cashfree_settings.cashfree_webhook`
- **Method**: POST
- **Headers Required**:
  - `x-webhook-signature`
  - `x-webhook-timestamp`

## Security

- Client Secret stored as encrypted Password field
- Webhook signatures verified using Cashfree SDK
- All payment requests logged in Integration Request
- Guest payments validated with tokens

## Support

For issues specific to this integration, check:
1. ERPNext Error Log
2. Integration Request logs
3. Cashfree Dashboard logs

For Cashfree API issues:
- [Cashfree Documentation](https://docs.cashfree.com/)
- [Cashfree Support](https://www.cashfree.com/contact-us/)
