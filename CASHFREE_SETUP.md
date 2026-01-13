# Cashfree Payment Gateway Integration - Setup Guide

## 🎉 Implementation Complete!

The Cashfree payment gateway has been successfully integrated into the Payments app with full support for:

- ✅ Multiple Cashfree accounts (one per company/hostel)
- ✅ Default account fallback
- ✅ Sandbox and Production environments
- ✅ Invoice payments
- ✅ Shopping cart integration
- ✅ Payment links via email
- ✅ Webhook support for real-time updates
- ✅ Guest payments (onboarding flow)

---

## 📦 Installation Steps

### 1. Install the Cashfree SDK

```bash
cd /Users/dom/frappe-bench
bench pip install cashfree_pg
```

Or the SDK will be automatically installed when you update/install the app:
```bash
bench install-app payments
# or
bench update --apps payments
```

### 2. Restart Bench

```bash
bench restart
```

### 3. Run Migrations

```bash
bench --site your-site-name migrate
```

This will create the `Cashfree Settings` DocType in your database.

---

## ⚙️ Configuration

### Step 1: Get Cashfree Credentials

1. Sign up for Cashfree account at https://www.cashfree.com/
2. Login to [Cashfree Dashboard](https://merchant.cashfree.com/)
3. Go to **Developers > API Keys**
4. Get your **App ID** (Client ID) and **Secret Key**
5. Note: Use Sandbox credentials for testing

### Step 2: Create Cashfree Settings

1. In ERPNext, go to: **Payment Gateways > Cashfree Settings > New**
2. Fill in the details:

   **For Hostel 1:**
   - Gateway Name: `Cashfree-Hostel1`
   - Company: Select "Hostel 1" (or your company name)
   - Is Default: Uncheck (only if you have multiple)
   - Environment: `Sandbox` (for testing)
   - Client ID: Your Cashfree App ID
   - Client Secret: Your Cashfree Secret Key

3. Save the document

4. Copy the **Webhook URL** shown in the form

### Step 3: Configure Multiple Accounts (Optional)

Repeat Step 2 for each hostel/company:

**For Hostel 2:**
- Gateway Name: `Cashfree-Hostel2`
- Company: Select "Hostel 2"
- Environment: `Sandbox`
- ... (different credentials)

**For Default Account:**
- Gateway Name: `Cashfree-Default`
- Company: Leave blank
- Is Default: **Check this**
- Environment: `Sandbox`
- ... (credentials)

### Step 4: Configure Webhooks in Cashfree Dashboard

1. Login to [Cashfree Dashboard](https://merchant.cashfree.com/)
2. Go to **Developers > Webhooks**
3. Click **Add Webhook**
4. Paste the Webhook URL from your Cashfree Settings
5. Select these events:
   - ✅ `PAYMENT_SUCCESS_WEBHOOK`
   - ✅ `PAYMENT_FAILED_WEBHOOK`
6. Save

**Note:** For local testing, use ngrok:
```bash
ngrok http 8000
# Use the ngrok URL in webhook configuration
```

---

## 🧪 Testing

### Test 1: Invoice Payment

1. Create a Sales Invoice
2. Click **Get Payment** button (or create Payment Request)
3. Select payment gateway: `Cashfree-Hostel1`
4. Complete payment using test credentials:
   - Card: 4111 1111 1111 1111
   - CVV: 123
   - Expiry: Any future date
   - OTP: 123456
5. Verify payment status updates to "Paid"

### Test 2: Payment Link

Open ERPNext console (bench console):

```python
from payments.payment_gateways.doctype.cashfree_settings.cashfree_settings import CashfreeSettings

# Get settings for a specific company
settings = CashfreeSettings.get_cashfree_settings_by_company("Hostel 1")

# Create payment link
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

print("Payment Link:", link["link_url"])
```

### Test 3: Shopping Cart

1. Enable Shopping Cart in Website Settings
2. Add items to cart as a customer
3. Proceed to checkout
4. Complete payment
5. Verify order is created

### Test 4: Webhooks

1. Make a test payment
2. Check **Integration Request** list for status updates
3. Check Error Log if webhooks fail
4. Verify `on_payment_authorized` is called on invoice

---

## 🏢 Usage by Company

The system automatically selects the correct Cashfree account based on the company:

```python
payment_details = {
    "amount": 10000,
    "currency": "INR",
    "company": "Hostel 1",  # ← Determines which Cashfree account to use
    "reference_doctype": "Sales Invoice",
    "reference_docname": "INV-001",
    "payer_email": "student@example.com",
    "payer_name": "John Doe",
    "payer_phone": "9876543210",
    "title": "Hostel Fee Payment",
    "description": "Monthly hostel fee"
}

from payments.utils import get_payment_gateway_controller
controller = get_payment_gateway_controller("Cashfree-Hostel1")
url = controller.get_payment_url(**payment_details)
```

---

## 🔐 Production Deployment

### 1. Get Production Credentials

1. Complete KYC verification in Cashfree Dashboard
2. Get production App ID and Secret Key
3. Test in production with small amounts first

### 2. Update Settings

1. Go to your Cashfree Settings
2. Change Environment to: `Production`
3. Update Client ID and Client Secret with production credentials
4. Save

### 3. Update Webhook URL

1. Update webhook URL in Cashfree Production Dashboard
2. Ensure your site has HTTPS (required for webhooks)
3. Test webhook delivery

---

## 📊 Monitoring

### Check Payment Status

1. **Integration Request List**: Shows all payment attempts
2. **Payment Entry**: Created automatically on successful payment
3. **Error Log**: Shows any errors during payment processing

### Cashfree Dashboard

- View transactions: Cashfree Dashboard > Transactions
- Check settlements: Dashboard > Settlements
- Webhook logs: Dashboard > Developers > Webhooks

---

## 🐛 Troubleshooting

### Issue: "No Cashfree Settings found"
**Solution:** Create at least one Cashfree Settings with "Is Default" checked

### Issue: Webhook not received
**Solutions:**
- Verify webhook URL is correct in Cashfree Dashboard
- Check site is accessible from internet (not localhost)
- Use ngrok for local testing
- Check Error Log for webhook errors

### Issue: Payment fails immediately
**Solutions:**
- Verify credentials (Client ID and Secret)
- Check environment matches (Sandbox vs Production)
- Review Integration Request for error details

### Issue: "Invalid signature" in webhooks
**Solutions:**
- Ensure credentials match the account in Cashfree Dashboard
- Check that webhook secret is correct
- Verify environment setting

---

## 📁 Files Created

```
payments/
├── pyproject.toml                                          # Updated with cashfree_pg dependency
├── payment_gateways/
│   └── doctype/
│       └── cashfree_settings/
│           ├── __init__.py
│           ├── cashfree_settings.json                     # DocType definition
│           ├── cashfree_settings.py                       # Main controller
│           ├── cashfree_settings.js                       # Client script
│           ├── test_cashfree_settings.py                  # Unit tests
│           └── README.md                                   # Documentation
└── templates/
    ├── pages/
    │   ├── cashfree_checkout.py                           # Checkout page logic
    │   └── cashfree_checkout.html                         # Checkout page template
    └── includes/
        └── cashfree_checkout.js                           # Checkout client script
```

---

## 🚀 Next Steps

1. **Install SDK**: `bench pip install cashfree_pg`
2. **Restart**: `bench restart`
3. **Migrate**: `bench --site your-site migrate`
4. **Configure**: Create Cashfree Settings records
5. **Test**: Make a test payment in sandbox mode
6. **Deploy**: Switch to production when ready

---

## 📞 Support

- **Cashfree Documentation**: https://docs.cashfree.com/
- **Cashfree Support**: https://www.cashfree.com/contact-us/
- **ERPNext Forum**: https://discuss.erpnext.com/

---

## ✅ Features Implemented

| Feature | Status | Notes |
|---------|--------|-------|
| Multiple Accounts | ✅ | One per company |
| Default Fallback | ✅ | Site-wide default |
| Sandbox Support | ✅ | For testing |
| Production Support | ✅ | For live payments |
| Invoice Payment | ✅ | Via Payment Request |
| Shopping Cart | ✅ | Auto-integration |
| Payment Links | ✅ | Email/SMS support |
| Webhooks | ✅ | Real-time updates |
| Guest Payments | ✅ | Token-based |
| Signature Verification | ✅ | Security |
| Error Logging | ✅ | Debugging |
| Multi-currency | ✅ | INR, USD, EUR, etc. |

---

## 🎓 Example Usage Scenarios

### Scenario 1: Student Pays Invoice
1. Admin creates Sales Invoice for student
2. Student clicks "Pay Now" in portal
3. System selects Hostel's Cashfree account
4. Student completes payment
5. Invoice marked as paid automatically

### Scenario 2: Payment Link for Admission
1. Admin creates payment link via console/API
2. Link sent to prospective student's email
3. Student (guest) clicks link and pays
4. Webhook updates status
5. Admin notified, customer record created

### Scenario 3: Shopping Cart Purchase
1. Student browses hostel store
2. Adds items to cart (mattress, supplies)
3. Proceeds to checkout
4. Pays via Cashfree
5. Order created automatically

---

**Implementation Date:** 16 November 2025  
**Version:** 1.0.0  
**Status:** ✅ Ready for Testing
