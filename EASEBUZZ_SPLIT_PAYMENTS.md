# Easebuzz Split Payments Integration Guide

**Version:** 1.0  
**Last Updated:** April 1, 2026

---

## Table of Contents

1. [What are Split Payments?](#what-are-split-payments)
2. [Prerequisites](#prerequisites)
3. [Configuration](#configuration)
4. [API Usage](#api-usage)
5. [Examples](#examples)
6. [Testing](#testing)
7. [Troubleshooting](#troubleshooting)
8. [FAQ](#faq)

---

## What are Split Payments?

Split payments is a feature offered by Easebuzz that allows a single transaction amount to be automatically distributed across multiple accounts or entities in a single transaction. This is particularly useful for:

- **Marketplace platforms**: Automatically split payments between the platform and vendors
- **Multi-tenant systems**: Distribute transaction fees to different business units
- **Commission-based systems**: Automatically split revenue between multiple parties

### How It Works

When a customer makes a payment of ₹250:
- ₹150 goes to Account A (label_HDFC)
- ₹100 goes to Account B (label_ICICI)

Easebuzz handles the distribution automatically based on the labels you provide.

---

## Prerequisites

Before using split payments, ensure you have:

1. ✅ **Easebuzz Merchant Account** with split payments enabled
2. ✅ **Split Payment Labels** provided by Easebuzz support team
3. ✅ **Merchant Configuration** in ERPNext/Frappe
4. ✅ **UAT Environment Access** for testing

### Getting Split Payment Labels

Contact the Easebuzz support team and request:
- Enable split payments for your merchant account
- List of labels (e.g., `label_HDFC`, `label_ICICI`, etc.)
- Label format and validation rules

**Important:** Labels must exactly match those provided by Easebuzz. Using incorrect labels will cause payment failures.

---

## Configuration

### Method 1: Configure in Easebuzz Merchant (Recommended)

This method sets default split configuration for all payments through a specific merchant.

#### Step 1: Navigate to Easebuzz Merchant

1. Go to **Payments** → **Payment Gateways** → **Easebuzz Merchant**
2. Open the merchant you want to configure
3. Scroll to the **Split Payments Configuration** section

#### Step 2: Add Split Payment Configuration

In the **Split Payments Labels** field, enter a JSON object with your labels and amounts:

```json
{
  "label_HDFC": 150,
  "label_ICICI": 100
}
```

**Format Rules:**
- Must be valid JSON
- Keys are the labels provided by Easebuzz
- Values are numeric amounts (can be integers or decimals)
- All amounts must be positive
- Total should match your typical transaction amount (or be calculated dynamically per transaction)

#### Step 3: Save

Click **Save**. The system will validate your JSON format automatically.

**Validation Checks:**
- ✅ Valid JSON format
- ✅ Labels are non-empty strings
- ✅ Amounts are numeric and positive

---

### Method 2: Pass Split Payments via API

For dynamic split configurations that change per transaction, you can pass split payments directly in the API call.

See [API Usage](#api-usage) section below.

---

## API Usage

### Initiate Payment with Split Payments

**Endpoint:** `/api/method/payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.initiate_payment`

**Method:** `POST`

**Headers:**
```
Content-Type: application/json
Authorization: token <api_key>:<api_secret>
```

### Example 1: Using Merchant Default Configuration

If you've configured split payments in the Easebuzz Merchant document, you don't need to pass any additional parameters:

```json
{
  "amount": 250,
  "currency": "INR",
  "reference_doctype": "Sales Invoice",
  "reference_docname": "SINV-2026-00123",
  "payer_email": "customer@example.com",
  "payer_name": "CUST-00001",
  "description": "Payment for invoice SINV-2026-00123",
  "company": "My Company Ltd"
}
```

The system will automatically use the split configuration from the merchant.

### Example 2: Override with Custom Split Configuration

To override the merchant's default or provide dynamic splits:

```json
{
  "amount": 250,
  "currency": "INR",
  "reference_doctype": "Sales Invoice",
  "reference_docname": "SINV-2026-00123",
  "payer_email": "customer@example.com",
  "payer_name": "CUST-00001",
  "description": "Payment for invoice SINV-2026-00123",
  "company": "My Company Ltd",
  "split_payments_labels": {
    "label_HDFC": 150,
    "label_ICICI": 100
  }
}
```

### Example 3: Using JSON String

You can also pass split payments as a JSON string:

```json
{
  "amount": 250,
  "split_payments_labels": "{\"label_HDFC\": 150, \"label_ICICI\": 100}"
}
```

---

## Examples

### Example 1: Marketplace Platform

**Scenario:** Customer pays ₹1000 for a product. Platform keeps ₹100 commission, vendor gets ₹900.

**Configuration:**
```json
{
  "label_platform": 100,
  "label_vendor_001": 900
}
```

**API Call:**
```bash
curl -X POST "https://your-site.com/api/method/payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.initiate_payment" \
  -H "Content-Type: application/json" \
  -H "Authorization: token <api_key>:<api_secret>" \
  -d '{
    "amount": 1000,
    "reference_doctype": "Sales Order",
    "reference_docname": "SO-2026-00001",
    "payer_email": "buyer@example.com",
    "payer_name": "CUST-00123",
    "split_payments_labels": {
      "label_platform": 100,
      "label_vendor_001": 900
    }
  }'
```

### Example 2: Multi-Campus University

**Scenario:** Student pays ₹50,000 fees. Split between multiple accounts:
- Campus A: ₹30,000
- Campus B: ₹15,000
- Central Fund: ₹5,000

**Merchant Configuration:**
```json
{
  "label_campus_a": 30000,
  "label_campus_b": 15000,
  "label_central": 5000
}
```

Since this is configured in the merchant, API calls don't need to include split_payments_labels.

### Example 3: Dynamic Commission System

**Scenario:** Commission varies per transaction based on product category.

**Implementation:**
```python
# Python example - calculate split dynamically
def create_payment_with_split(invoice):
    amount = invoice.total
    commission_rate = get_commission_rate(invoice.customer)
    
    commission = amount * commission_rate
    vendor_share = amount - commission
    
    split_config = {
        "label_platform": commission,
        "label_vendor": vendor_share
    }
    
    # Call Easebuzz API
    response = requests.post(
        f"{base_url}/api/method/...initiate_payment",
        json={
            "amount": amount,
            "reference_doctype": "Sales Invoice",
            "reference_docname": invoice.name,
            "payer_email": invoice.customer_email,
            "payer_name": invoice.customer,
            "split_payments_labels": split_config
        }
    )
    return response.json()
```

---

## Testing

### UAT Environment Testing

Before going to production, test thoroughly in the UAT environment.

#### Step 1: Configure Test Merchant

1. Create an Easebuzz Merchant with UAT credentials
2. Set Environment to **Test**
3. Add test split payment labels (get from Easebuzz team)

Example test configuration:
```json
{
  "label_test_account_1": 100,
  "label_test_account_2": 50
}
```

#### Step 2: Initiate Test Payment

Use the API or create a test transaction:

```bash
curl -X POST "https://your-uat-site.com/api/method/...initiate_payment" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 150,
    "reference_doctype": "Sales Invoice",
    "reference_docname": "TEST-SINV-001",
    "payer_email": "test@example.com",
    "payer_name": "Test Customer",
    "custom_merchant_name": "Test Merchant UAT"
  }'
```

#### Step 3: Complete Payment

1. You'll receive a payment URL: `https://testpay.easebuzz.in/pay/...`
2. Open the URL in a browser
3. Complete the test payment using Easebuzz test cards
4. Verify webhook callback is received
5. Check Integration Request status is updated

#### Step 4: Verify Split in Easebuzz Dashboard

1. Log into Easebuzz UAT dashboard
2. Check transaction details
3. Verify split amounts are correct
4. Verify amounts credited to correct accounts

### Test Checklist

- [ ] Split configuration validates on save
- [ ] Payment initiation succeeds with splits
- [ ] Payment URL generated correctly
- [ ] Payment completes successfully
- [ ] Webhook callback received
- [ ] Transaction status updated correctly
- [ ] Split amounts match configuration
- [ ] Amounts credited to correct labels
- [ ] Error handling works (invalid labels, wrong amounts)

---

## Troubleshooting

### Issue 1: "Invalid split_payments configuration"

**Cause:** JSON format error in split payments configuration.

**Solution:**
1. Validate your JSON using a JSON validator (https://jsonlint.com/)
2. Check for:
   - Missing or extra commas
   - Missing quotes around strings
   - Trailing commas (not allowed in JSON)

**Correct:**
```json
{
  "label_HDFC": 100,
  "label_ICICI": 50
}
```

**Incorrect:**
```json
{
  label_HDFC: 100,        ❌ Missing quotes
  "label_ICICI": 50,      ❌ Trailing comma
}
```

### Issue 2: "Split amounts don't match transaction total"

**Cause:** The sum of split amounts doesn't equal the transaction amount.

**Solution:**
1. Calculate total split amount
2. Ensure it matches the transaction amount exactly
3. Account for payment charges if applicable

**Example:**
```
Transaction amount: ₹250
Payment charges: ₹10
Final amount: ₹260

Split configuration should total ₹260:
{
  "label_HDFC": 160,
  "label_ICICI": 100
}
Total: ₹260 ✅
```

**Note:** A warning is logged if amounts don't match, but the payment is still attempted. Easebuzz may reject if the mismatch is significant.

### Issue 3: Payment fails with "Invalid label"

**Cause:** Using labels not configured in your Easebuzz merchant account.

**Solution:**
1. Contact Easebuzz support to verify your labels
2. Ensure labels match exactly (case-sensitive)
3. Use only labels provided by Easebuzz team

### Issue 4: Split payments not appearing in Easebuzz dashboard

**Cause:** Split payments might not be enabled for your merchant account.

**Solution:**
1. Contact Easebuzz support
2. Request activation of split payments feature
3. Verify in UAT environment first

### Issue 5: Hash verification failure

**Cause:** Split payments should NOT be included in hash calculation.

**Solution:**
- Hash generation is automatic
- `split_payments` parameter is excluded from hash
- No action needed (system handles this correctly)

---

## FAQ

### Q1: Can I change split configuration per transaction?

**A:** Yes, in two ways:
1. Pass `split_payments_labels` parameter in API call (overrides merchant default)
2. Create multiple merchants with different split configurations

### Q2: What happens if split amounts don't match transaction total?

**A:** 
- System logs a warning
- Payment is still attempted
- Easebuzz may reject if mismatch is significant
- Best practice: Always ensure amounts match exactly

### Q3: Can I use percentage-based splits instead of fixed amounts?

**A:** 
- Easebuzz API requires actual amounts, not percentages
- Calculate percentages in your application before calling API
- Pass calculated amounts in split_payments_labels

**Example:**
```python
amount = 1000
platform_percentage = 10  # 10%
vendor_percentage = 90    # 90%

split_config = {
    "label_platform": amount * platform_percentage / 100,  # 100
    "label_vendor": amount * vendor_percentage / 100       # 900
}
```

### Q4: Are split payments mandatory?

**A:** No. Split payments are completely optional.
- If not configured, payments work normally (100% to merchant)
- Backward compatible with existing integrations
- Only activated when explicitly configured

### Q5: Can I have more than 2 splits?

**A:** Yes, you can split across multiple labels:

```json
{
  "label_account_1": 100,
  "label_account_2": 50,
  "label_account_3": 30,
  "label_account_4": 20
}
```

Limit depends on Easebuzz's restrictions (confirm with support).

### Q6: How do I test in UAT before production?

**A:**
1. Create test merchant with Environment = "Test"
2. Use UAT credentials from Easebuzz
3. Get test labels from Easebuzz team
4. Test thoroughly using test cards
5. Verify splits in Easebuzz UAT dashboard
6. Once confirmed working, create production merchant

### Q7: What's the difference between merchant config and API parameter?

**A:**

| Method | Use Case | Priority |
|--------|----------|----------|
| **Merchant Config** | Fixed splits for all transactions through that merchant | Lower |
| **API Parameter** | Dynamic splits that vary per transaction | Higher (overrides merchant) |

**Best Practice:** 
- Use merchant config for consistent splits
- Use API parameter for dynamic/variable splits

### Q8: Can I split payments across different payment gateways?

**A:** No. Split payments only work within Easebuzz. To split across gateways, you'd need to:
1. Receive full payment in one gateway
2. Use separate transfer/payout APIs to distribute funds

### Q9: How are refunds handled with split payments?

**A:** 
- Refunds reverse the split proportionally
- Handled automatically by Easebuzz
- Each account is debited based on original split

### Q10: Does split payments affect transaction fees?

**A:**
- Easebuzz may charge additional fees for split payments
- Check your merchant agreement
- Fees are typically deducted from the total before split
- Confirm fee structure with Easebuzz support

---

## Best Practices

### 1. Validation

✅ **Do:**
- Validate split amounts sum to transaction total
- Use exact label names from Easebuzz
- Test thoroughly in UAT environment
- Handle errors gracefully

❌ **Don't:**
- Hardcode labels without confirmation
- Skip UAT testing
- Ignore validation warnings

### 2. Configuration Management

✅ **Do:**
- Document your labels and their purpose
- Use merchant config for standard splits
- Use API parameters for dynamic splits
- Keep labels centralized and maintained

❌ **Don't:**
- Spread label configuration across multiple places
- Change labels without coordination with Easebuzz
- Use production labels in UAT

### 3. Error Handling

✅ **Do:**
- Log split payment errors
- Monitor for amount mismatch warnings
- Have fallback logic for payment failures
- Alert on split configuration issues

❌ **Don't:**
- Silently ignore errors
- Assume splits will always work
- Skip monitoring

### 4. Documentation

✅ **Do:**
- Document your split payment logic
- Maintain label registry
- Keep team informed of changes
- Update documentation when labels change

❌ **Don't:**
- Leave split logic undocumented
- Change without communication
- Assume everyone knows the labels

---

## Support and Resources

### Easebuzz Documentation
- [Initiate Payment API](https://docs.easebuzz.in/docs/payment-gateway/8ec545c331e6f-initiate-payment-api)
- [Webhooks](https://docs.easebuzz.in/docs/payment-gateway/587zy3v064so6-what-are-webhooks)
- [Transaction API V2.1](https://docs.easebuzz.in/docs/payment-gateway/6il9ej80xoydr-transaction-api-v2-1)

### ERPNext/Frappe Documentation
- [EASEBUZZ_INTEGRATION.md](./EASEBUZZ_INTEGRATION.md)
- [EASEBUZZ_SETUP.md](./EASEBUZZ_SETUP.md)
- [EASEBUZZ_IMPLEMENTATION_SUMMARY.md](./EASEBUZZ_IMPLEMENTATION_SUMMARY.md)

### Getting Help
- **Easebuzz Support:** For label configurations, account setup, API issues
- **Internal Team:** For integration questions, configuration help
- **GitHub Issues:** For bug reports and feature requests

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | April 1, 2026 | Initial release with split payments support |

---

**Last Updated:** April 1, 2026  
**Document Version:** 1.0  
**Status:** Active
