# Easebuzz Split Payments - Agent Skill

**Agent Type:** Payment Integration Specialist  
**Skill Level:** Advanced  
**Domain:** Payment Gateway Integration  
**Version:** 1.0

---

## Overview

This agent skill document describes the capabilities and knowledge required to work with Easebuzz Split Payments integration in the ERPNext/Frappe payments app. This skill enables agents to configure, troubleshoot, and optimize split payment functionality.

---

## Core Competencies

### 1. Understanding Split Payments

**What the agent knows:**
- Split payments allow a single transaction to be distributed across multiple accounts/entities
- Easebuzz handles the distribution automatically based on labels provided
- Labels are pre-configured by Easebuzz team for each merchant account
- Split amounts must sum to the total transaction amount (including charges)

**Key concepts:**
- **Labels:** Unique identifiers for accounts (e.g., `label_HDFC`, `label_ICICI`)
- **Split Configuration:** JSON mapping of labels to amounts
- **Merchant Default:** Default split configuration stored in merchant document
- **API Override:** Dynamic split configuration passed per transaction

### 2. Configuration Management

**Agent can:**
- Configure split payments in Easebuzz Merchant document
- Validate JSON format of split payment configuration
- Set up merchant-level default splits
- Override merchant defaults via API parameters

**Configuration locations:**
1. **Easebuzz Merchant DocType** (`split_payments_config` field)
2. **API Parameter** (`split_payments_labels` in initiate_payment call)

**Validation rules:**
- JSON must be valid dictionary/object
- Labels must be non-empty strings
- Amounts must be numeric and positive
- Recommended: Sum of amounts should equal transaction amount

### 3. API Integration

**Endpoints:**
- `POST /api/method/payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.initiate_payment`

**Parameters:**
```json
{
  "split_payments_labels": {
    "label_name": amount,
    ...
  }
}
```

**OR**

```json
{
  "split_payments_labels": "{\"label_name\": amount}"
}
```

**Priority:**
1. API parameter `split_payments_labels` (highest priority)
2. Merchant's `split_payments_config`
3. No splits (standard payment)

---

## Quick Reference

### API Example

```bash
curl -X POST "https://site.com/api/method/...initiate_payment" \
  -H "Content-Type: application/json" \
  -H "Authorization: token key:secret" \
  -d '{
    "amount": 250,
    "reference_doctype": "Sales Invoice",
    "reference_docname": "SINV-001",
    "payer_email": "customer@example.com",
    "payer_name": "CUST-001",
    "split_payments_labels": {
      "label_HDFC": 150,
      "label_ICICI": 100
    }
  }'
```

### Configuration Example

```json
{
  "label_platform": 100,
  "label_vendor": 900
}
```

---

## Key Files Modified

1. `/payments/payment_gateways/doctype/easebuzz_merchant/easebuzz_merchant.json`
   - Added `split_payments_config` field (Long Text)

2. `/payments/payment_gateways/doctype/easebuzz_merchant/easebuzz_merchant.py`
   - Added `validate_split_payments_config()` method

3. `/payments/payment_gateways/doctype/easebuzz_settings/easebuzz_settings.py`
   - Updated `create_payment_request_data()` to handle split payments
   - Updated `initiate_payment()` docstring

---

## Testing Checklist

- [ ] Create merchant with valid split configuration
- [ ] Validate JSON format on save
- [ ] Initiate payment using merchant default
- [ ] Initiate payment with API override
- [ ] Verify amounts sum to transaction total
- [ ] Complete payment in Easebuzz UAT
- [ ] Verify split in Easebuzz dashboard

---

## Common Issues

| Issue | Solution |
|-------|----------|
| Invalid JSON error | Validate JSON format at jsonlint.com |
| Amount mismatch warning | Recalculate split amounts to match total |
| Invalid label error | Contact Easebuzz for valid labels |
| Payment rejected | Verify split payments enabled in Easebuzz account |

---

## Resources

- **EASEBUZZ_SPLIT_PAYMENTS.md** - Complete user guide
- **EASEBUZZ_SPLIT_PAYMENTS_PLAN.md** - Implementation plan
- [Easebuzz API Docs](https://docs.easebuzz.in/)

---

**Status:** Active  
**Version:** 1.0  
**Date:** April 1, 2026
