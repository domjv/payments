# Easebuzz Payment Gateway - Quick Setup Guide

## Overview
This integration provides Easebuzz payment gateway support for ERPNext with multi-merchant configuration, similar to the CCAvenue integration.

## Features
- ✅ Multi-merchant support with company-based routing
- ✅ Default merchant fallback
- ✅ API-based integration for NextJS/React Native
- ✅ iFrame/WebView support
- ✅ Hash verification (SHA-512)
- ✅ Webhook callbacks
- ✅ Payment status tracking

## Quick Setup

### 1. Install Dependencies
The integration uses Python's `requests` library which should already be available in Frappe.

### 2. Run Migrations
```bash
cd /path/to/frappe-bench
bench migrate
```

This will create the following DocTypes:
- Easebuzz Settings
- Easebuzz Merchant

### 3. Configure Easebuzz Settings

Navigate to: **Payment Gateways > Easebuzz Settings**

Configure:
- **Merchant Key**: Your default merchant key from Easebuzz
- **Salt**: Your default salt from Easebuzz
- **Environment**: Select "Test" or "Production"
- **Redirect To** (Optional): External frontend URL for payment callbacks
- **Header Image** (Optional): Logo URL for checkout page

Click **Save**.

### 4. Create Merchant Configuration

Navigate to: **Payment Gateways > Easebuzz Merchant**

Click **New** and fill:
- **Merchant Name**: e.g., "Default Merchant" or "Campus A"
- **Is Default Merchant**: Check this for your primary merchant
- **Merchant Key**: From Easebuzz dashboard
- **Salt**: From Easebuzz dashboard
- **Environment**: Test or Production
- **Company** (Optional): Link to specific company
- **Bank Account** (Optional): Bank account prefix
- **Debtors Account** (Optional): Debtors account prefix

Click **Save**.

### 5. Test Connection

In the Easebuzz Merchant form, click **Test Connection** button to verify credentials.

## Usage

### API Integration (for NextJS/React Native Frontends)

#### Initiate Payment
```javascript
const response = await fetch('/api/method/payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.initiate_payment', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    amount: 1000.00,
    reference_doctype: 'Sales Invoice',
    reference_docname: 'SINV-001',
    payer_email: 'customer@example.com',
    payer_name: 'CUST-001',
    description: 'Payment for Invoice',
    phone: '9876543210'
  })
});

const data = await response.json();
if (data.message.success) {
  window.location.href = data.message.payment_url;
}
```

#### Check Payment Status
```javascript
const response = await fetch(
  '/api/method/payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.check_payment_status' +
  '?integration_request_name=' + integrationId
);

const data = await response.json();
console.log(data.message.status); // 'Completed' or 'Failed'
```

## Multi-Merchant Configuration

### Scenario: Multiple Companies

If you have multiple companies (e.g., Campus A, Campus B):

1. **Create Default Merchant**:
   - Merchant Name: "Default Merchant"
   - Is Default: ✓ (checked)
   - No company link (works for all)

2. **Create Company-Specific Merchants**:
   - Merchant Name: "Campus A Merchant"
   - Is Default: ✗ (unchecked)
   - Company: Campus A
   
   - Merchant Name: "Campus B Merchant"
   - Is Default: ✗ (unchecked)
   - Company: Campus B

The system will automatically route payments to the correct merchant based on the company field in the payment request.

## Webhook Configuration (Optional)

Configure these webhooks in your Easebuzz dashboard:

1. **Success URL**:
   ```
   https://your-site.com/api/method/payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.verify_transaction?merchant={merchant_name}
   ```

2. **Failure URL**:
   ```
   https://your-site.com/api/method/payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.verify_transaction?merchant={merchant_name}
   ```

Replace `{merchant_name}` with your actual merchant name.

## Testing

### Test Mode
1. Set Environment to "Test" in Easebuzz Merchant
2. Use test credentials from Easebuzz
3. Test payments will not process real money

### Test Payment
```bash
# Via bench console
bench console

# In console
import frappe
from payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings import initiate_payment

result = initiate_payment(
    amount=10.00,
    reference_doctype='Sales Invoice',
    reference_docname='SINV-TEST-001',
    payer_email='test@example.com',
    payer_name='Test Customer',
    phone='9999999999'
)

print(result)
```

## Troubleshooting

### Payment initiation fails
- **Check**: Merchant credentials are correct
- **Check**: Environment setting matches your Easebuzz account (Test/Production)
- **Check**: Error Log doctype for detailed errors

### Hash verification fails
- **Check**: Salt is correctly configured and matches Easebuzz
- **Check**: No extra spaces in merchant key or salt

### Payment not updating in ERPNext
- **Check**: Integration Request document for payment details
- **Check**: `on_payment_authorized` method exists in reference doctype
- **Check**: Error logs for callback processing errors

### Multi-merchant not working
- **Check**: Company field is set in payment request
- **Check**: Merchant has correct company linked
- **Check**: At least one merchant is marked as default

## File Structure

```
payments/
├── payment_gateways/
│   └── doctype/
│       ├── easebuzz_settings/
│       │   ├── __init__.py
│       │   ├── easebuzz_settings.json
│       │   ├── easebuzz_settings.py      # Main controller
│       │   ├── easebuzz_settings.js      # Form script
│       │   └── easebuzz_utils.py         # Utility functions
│       └── easebuzz_merchant/
│           ├── __init__.py
│           ├── easebuzz_merchant.json
│           ├── easebuzz_merchant.py      # Merchant controller
│           └── easebuzz_merchant.js      # Form script
├── templates/
│   └── pages/
│       ├── easebuzz_checkout.html        # Checkout page template
│       └── easebuzz_checkout.py          # Checkout controller
└── public/
    └── js/
        └── easebuzz.js                   # Frontend helper
```

## API Reference

See [EASEBUZZ_INTEGRATION.md](EASEBUZZ_INTEGRATION.md) for complete API documentation.

## Support

- **Easebuzz Docs**: https://docs.easebuzz.in/
- **ERPNext Forum**: https://discuss.erpnext.com/
- **GitHub Issues**: [Your repo URL]

## License

MIT License - See LICENSE file

---

**Created**: 2025-01-27  
**Version**: 1.0.0  
**Compatibility**: ERPNext v14+, Frappe v14+
└── payment_gateways/
    └── doctype/
        ├── easebuzz_settings/
        │   ├── __init__.py
        │   ├── easebuzz_settings.json
        │   ├── easebuzz_settings.py      # Main controller with API endpoints
        │   ├── easebuzz_settings.js      # Form script
        │   └── easebuzz_utils.py         # Utility functions
        └── easebuzz_merchant/
            ├── __init__.py
            ├── easebuzz_merchant.json
            ├── easebuzz_merchant.py      # Merchant controller
            └── easebuzz_merchant.js      # Form script