# Easebuzz Split Payments Integration - Detailed Plan

**Date:** April 1, 2026  
**Author:** GitHub Copilot Agent  
**Status:** Implementation Plan

---

## Executive Summary

This document outlines the implementation plan for integrating Easebuzz Split Payments functionality into the existing payment gateway integration. Split payments allow a transaction's amount to be divided among multiple entities (e.g., vendors, sub-merchants, or accounts) in a single transaction.

---

## 1. Understanding Split Payments

### What are Split Payments?

Split payments is a feature offered by Easebuzz that allows a single transaction amount to be automatically distributed across multiple accounts/entities. This is useful for:

- **Marketplace platforms**: Split payments between platform and vendors
- **Multi-tenant systems**: Distribute fees to different business units
- **Commission-based systems**: Automatically split revenue between parties

### How Split Payments Work in Easebuzz

According to Easebuzz API documentation:

1. **Parameter Name**: `split_payments` (or `splitPayments` in some SDKs)
2. **Data Type**: JSON string
3. **Format**: 
   ```json
   {
     "label_HDFC": 100,
     "label_icici": 150
   }
   ```
4. **Labels**: Pre-configured labels provided by Easebuzz team for each merchant
5. **Requirement**: 
   - Mandatory only if using split payment feature
   - Amounts must sum to total transaction amount
   - Labels must match exactly as provided by Easebuzz

### Key Requirements from Easebuzz Tech Team

Based on the problem statement:

1. ✅ Pass labels in `split_payments` parameter in Initiate Payment API
2. ✅ Support both UAT (https://testpay.easebuzz.in) and Production (https://pay.easebuzz.in)
3. ✅ Handle webhooks properly
4. ✅ Implement Transaction Status Check API V2.1
5. ✅ Verify response hash using SHA512 with specific sequence

---

## 2. Current Implementation Analysis

### Existing Architecture

The current Easebuzz integration consists of:

**Core Files:**
- `easebuzz_settings.py` (843 lines) - Main controller with payment initiation logic
- `easebuzz_utils.py` (298 lines) - Utility functions for API calls and hash generation
- `easebuzz_merchant.py` (105 lines) - Multi-merchant configuration management
- `easebuzz_settings.json` - Singleton settings schema
- `easebuzz_merchant.json` - Multi-merchant schema

**Key Features Already Implemented:**
- ✅ Multi-merchant support with company-based routing
- ✅ SHA-512 hash generation and verification
- ✅ Initiate Payment API integration
- ✅ Webhook and callback handling
- ✅ Transaction status checking
- ✅ Integration with ERPNext (Sales Invoice, Payment Request)
- ✅ Payment charges calculation
- ✅ UDF (User Defined Fields) for custom data

**Payment Flow:**
```
Client → initiate_payment() → Create Integration Request 
  → Get Merchant Config → Build Payment Data 
  → Generate Hash → Call Easebuzz API → Return Payment URL
  → Customer pays → Webhook/Callback → Verify Hash → Update Status
```

### Hash Generation (Current Implementation)

**Request Hash Sequence:**
```
key|txnid|amount|productinfo|firstname|email|udf1|udf2|udf3|udf4|udf5||||||salt
```

**Response Hash Sequence (from problem statement):**
```
salt|status|udf10|udf9|udf8|udf7|udf6|udf5|udf4|udf3|udf2|udf1|email|firstname|productinfo|amount|txnid|key
```

---

## 3. Implementation Strategy

### Design Principles

1. **Minimal Changes**: Only add what's necessary for split payments
2. **Backward Compatibility**: Existing integrations must continue to work
3. **Multi-Merchant Support**: Each merchant can have different split payment configurations
4. **Flexibility**: Support dynamic split configurations per transaction
5. **Validation**: Ensure split amounts match total transaction amount
6. **Security**: Maintain hash verification integrity

### Why This Approach?

#### Option 1: Store Split Labels in Merchant Config (CHOSEN ✓)
**Pros:**
- Centralized configuration per merchant
- Easy to manage and update
- Clear separation of concerns
- Supports merchant-specific labels
- Can be optional (backward compatible)

**Cons:**
- Less flexible for dynamic splits per transaction

#### Option 2: Pass Split Payments in Every API Call
**Pros:**
- Maximum flexibility per transaction
- No schema changes needed

**Cons:**
- Client must calculate splits
- Error-prone
- Less secure (client controls distribution)

#### Option 3: Create Separate Split Payment Configuration DocType
**Pros:**
- Very flexible
- Can have multiple split configurations

**Cons:**
- Over-engineered for current requirements
- More complex to implement

**DECISION: Choose Option 1 with ability to override via API parameter**

This provides the best balance of:
- Ease of configuration (default splits in merchant config)
- Flexibility (can override per transaction if needed)
- Security (server-side validation)
- Backward compatibility (optional field)

---

## 4. Detailed Implementation Plan

### Phase 1: Data Model Changes

#### 1.1 Update Easebuzz Merchant Schema
**File**: `easebuzz_merchant.json`

Add new field:
```json
{
  "fieldname": "split_payments_config",
  "fieldtype": "Long Text",
  "label": "Split Payments Configuration",
  "description": "JSON configuration for split payments. Example: {\"label_HDFC\": 100, \"label_ICICI\": 50}. Labels must be provided by Easebuzz team.",
  "depends_on": "eval:doc.environment"
}
```

**Reasoning:**
- Long Text allows JSON storage
- Optional field (backward compatible)
- Per-merchant configuration
- Clear description guides users

#### 1.2 Add Validation Method
**File**: `easebuzz_merchant.py`

Add method to validate split payment JSON:
```python
def validate_split_payments_config(self):
    """Validate split payments JSON format"""
    if self.split_payments_config:
        try:
            split_data = json.loads(self.split_payments_config)
            # Validate format
            if not isinstance(split_data, dict):
                frappe.throw("Split payments must be a JSON object")
            # Validate labels
            for label, amount in split_data.items():
                if not isinstance(amount, (int, float)):
                    frappe.throw(f"Amount for {label} must be numeric")
        except json.JSONDecodeError:
            frappe.throw("Invalid JSON format in split payments configuration")
```

**Reasoning:**
- Catch configuration errors early
- Provide clear error messages
- Prevent runtime failures

### Phase 2: Payment Data Builder Changes

#### 2.1 Update `create_payment_request_data()` Method
**File**: `easebuzz_settings.py`

**Changes:**
1. Add parameter handling for `split_payments_labels` in kwargs
2. Get merchant's split_payments_config if available
3. Calculate split amounts if labels provided
4. Add to payment_data dictionary

**Implementation:**
```python
def create_payment_request_data(self, integration_request_name, **kwargs):
    # ... existing code ...
    
    # Get merchant configuration
    merchant_doc = self.get_merchant_for_company(company=company, merchant_name=merchant_name)
    
    # ... existing code for customer, charges, etc. ...
    
    # Handle split payments
    split_payments_json = None
    split_payments_labels = kwargs.get('split_payments_labels')
    
    if split_payments_labels:
        # API caller provided split configuration
        # Validate it's a dict or JSON string
        if isinstance(split_payments_labels, str):
            split_payments_json = split_payments_labels
        elif isinstance(split_payments_labels, dict):
            split_payments_json = json.dumps(split_payments_labels)
    elif merchant_doc.get('split_payments_config'):
        # Use merchant's default configuration
        split_payments_json = merchant_doc.split_payments_config
    
    # Validate split amounts equal final_amount if splits provided
    if split_payments_json:
        try:
            split_data = json.loads(split_payments_json)
            total_split = sum(float(v) for v in split_data.values())
            # Allow small floating point differences
            if abs(total_split - final_amount) > 0.01:
                frappe.log_error(
                    f"Split payments total ({total_split}) doesn't match transaction amount ({final_amount})",
                    "Easebuzz Split Payment Warning"
                )
        except Exception as e:
            frappe.log_error(f"Split payments validation error: {str(e)}", "Easebuzz Split Payment Error")
    
    # Build payment data
    payment_data = {
        'txnid': txnid,
        'amount': str(final_amount),
        # ... existing fields ...
    }
    
    # Add split_payments if configured
    if split_payments_json:
        payment_data['split_payments'] = split_payments_json
    
    return {
        "payment_data": payment_data,
        # ... existing return values ...
    }
```

**Reasoning:**
- Supports both API-provided and merchant-default splits
- Validates split amounts match transaction total
- Logs warnings instead of throwing errors (merchant might know better)
- Maintains backward compatibility (split_payments is optional)

#### 2.2 Update `initiate_payment()` API
**File**: `easebuzz_settings.py`

Add documentation for new parameter:
```python
@frappe.whitelist(allow_guest=True)
def initiate_payment(**kwargs):
    """
    API endpoint to initiate an Easebuzz payment from frontend/mobile app.
    
    Args:
        # ... existing parameters ...
        split_payments_labels (dict|str, optional): Split payment configuration.
            Can be a dict like {"label_HDFC": 100, "label_ICICI": 50} or JSON string.
            If not provided, uses merchant's default split configuration.
    
    Returns:
        dict: Payment initiation data
    """
    # ... existing implementation (no changes needed, just documentation) ...
```

**Reasoning:**
- No code changes needed, just documentation
- Parameter flows through kwargs automatically
- Maintains API simplicity

### Phase 3: Hash Generation Updates

#### 3.1 Review Hash Sequence
**File**: `easebuzz_utils.py`

Current implementation already handles the request hash correctly. Need to verify if `split_payments` affects hash calculation.

According to Easebuzz documentation, `split_payments` is typically NOT included in the hash sequence. The hash remains:
```
key|txnid|amount|productinfo|firstname|email|udf1|udf2|udf3|udf4|udf5||||||salt
```

**Action:** No changes needed to `generate_hash()` function.

#### 3.2 Verify Response Hash
**File**: `easebuzz_utils.py`

Current response hash verification already implements the correct sequence:
```python
def verify_response_hash(response_data, salt):
    # Response hash: salt|status|udf10|udf9|...|udf1|email|firstname|productinfo|amount|txnid|key
```

**Action:** Verify current implementation matches problem statement requirements.

### Phase 4: API Integration Changes

#### 4.1 Update `initiate_payment_api()` Function
**File**: `easebuzz_utils.py`

The function already passes all payment_data fields to the API:
```python
response = requests.post(api_url, data=payment_data, timeout=30)
```

Since we're adding `split_payments` to `payment_data`, it will automatically be sent.

**Action:** No changes needed. Verify with testing.

### Phase 5: Webhook and Callback Updates

#### 5.1 Review Callback Handlers
**Files**: `easebuzz_settings.py` - `verify_transaction()` and `webhook_callback()`

Current implementation:
1. ✅ Receives response data
2. ✅ Verifies hash
3. ✅ Updates Integration Request status
4. ✅ Calls on_payment_authorized()

**Question:** Does split payment response include additional fields?

**Research needed:** Check if Easebuzz returns split payment details in response.

**Action:** 
- Review webhook response format for split payments
- Log split payment details if present
- No changes to core flow needed (hash verification handles it)

### Phase 6: Documentation Updates

#### 6.1 Create Implementation Guide
**File**: Create `EASEBUZZ_SPLIT_PAYMENTS.md`

Contents:
- What are split payments
- How to configure in Easebuzz Merchant
- API usage examples
- Testing guide
- Troubleshooting

#### 6.2 Update Existing Documentation
**Files**: 
- `EASEBUZZ_INTEGRATION.md` - Add split payments section
- `EASEBUZZ_SETUP.md` - Add configuration steps

#### 6.3 Create Agent Skill Documentation
**File**: Create `.github/agents/easebuzz-split-payments-skill.md`

Contents:
- Agent capabilities
- When to use split payments
- Configuration examples
- Common issues and solutions

---

## 5. Testing Strategy

### 5.1 Unit Tests
Create test file: `test_easebuzz_split_payments.py`

Test cases:
1. ✅ Validate split payments JSON format
2. ✅ Calculate split amounts correctly
3. ✅ Verify splits sum to transaction total
4. ✅ Handle missing split configuration
5. ✅ Override merchant default with API parameter

### 5.2 Integration Tests

Test scenarios:
1. **Scenario 1**: Payment with merchant default split configuration
2. **Scenario 2**: Payment with API-provided split labels
3. **Scenario 3**: Payment without split payments (backward compatibility)
4. **Scenario 4**: Invalid split configuration (error handling)
5. **Scenario 5**: Split amounts don't match total (validation)

### 5.3 UAT Environment Testing

Using Easebuzz test environment:
1. Configure test merchant with split labels
2. Initiate payment with splits
3. Complete payment
4. Verify webhook receives split details
5. Check transaction status API response

### 5.4 Manual Testing Checklist

- [ ] Create Easebuzz Merchant with split_payments_config
- [ ] Initiate payment via API (with merchant default)
- [ ] Initiate payment via API (with custom splits)
- [ ] Complete payment in Easebuzz test gateway
- [ ] Verify webhook callback received
- [ ] Verify hash validation passes
- [ ] Check Integration Request status updated
- [ ] Verify transaction status API works
- [ ] Test with production environment (after UAT success)

---

## 6. Migration and Rollout Plan

### 6.1 Backward Compatibility

**Guarantee:**
- Existing merchants without split_payments_config continue working
- Existing API calls without split_payments_labels work unchanged
- No breaking changes to API or data models

**How:**
- All new fields are optional
- Default behavior remains unchanged
- Split payments only active when explicitly configured

### 6.2 Rollout Strategy

**Phase 1: Development & Testing (Current)**
- Implement changes
- Unit testing
- Integration testing
- Documentation

**Phase 2: UAT Environment (2-3 days)**
- Deploy to staging/UAT
- Test with Easebuzz test environment
- Gather test merchant labels from Easebuzz team
- End-to-end testing

**Phase 3: Production Preparation (1 day)**
- Code review
- Security audit
- Performance testing
- Documentation review

**Phase 4: Production Rollout (Gradual)**
- Deploy to production
- Enable for pilot merchant first
- Monitor for 24 hours
- Enable for remaining merchants
- Continuous monitoring

### 6.3 Rollback Plan

If issues occur:
1. Disable split payments in merchant configuration
2. Revert to previous version if critical
3. Split payments field is optional, so old code works

---

## 7. Security Considerations

### 7.1 Hash Verification

**Current:**
- ✅ SHA-512 hash on request
- ✅ SHA-512 hash verification on response
- ✅ Salt stored securely (Password field)

**With Split Payments:**
- ✅ Split payments NOT in hash (per Easebuzz spec)
- ✅ Hash verification unchanged
- ✅ Additional validation: amounts must match

### 7.2 Input Validation

**Validations to Add:**
1. ✅ JSON format validation
2. ✅ Numeric amounts validation
3. ✅ Total amount matching
4. ✅ Label format validation (alphanumeric + underscore)

### 7.3 Data Protection

**Considerations:**
- Split payment configuration stored in database
- No sensitive data (just labels and amounts)
- Merchant-specific (access controlled by permissions)

---

## 8. Performance Considerations

### 8.1 Impact Analysis

**Additions:**
- JSON parsing: negligible impact (< 1ms)
- Validation: minimal computation
- API payload: slight increase in size (< 1KB)

**Overall Impact:** MINIMAL - No performance degradation expected

### 8.2 Optimization Opportunities

- Cache merchant split configuration (already cached via frappe.get_doc)
- Reuse JSON parsing results
- Pre-validate on merchant save (already implemented)

---

## 9. Monitoring and Logging

### 9.1 Log Points

Add logging for:
1. Split payment configuration loaded
2. Split payment validation results
3. API request with split payments
4. Webhook response with split details

### 9.2 Metrics to Track

- Number of payments with split configuration
- Split payment success rate
- Validation failures
- Amount mismatch warnings

---

## 10. Success Criteria

### 10.1 Functional Requirements

- ✅ Can configure split payments in Easebuzz Merchant
- ✅ Can pass split_payments in initiate payment API
- ✅ Easebuzz accepts split payment parameter
- ✅ Payment completes successfully with splits
- ✅ Webhook receives and processes split payment response
- ✅ Transaction status API shows split payment details

### 10.2 Non-Functional Requirements

- ✅ No breaking changes to existing integrations
- ✅ Performance impact < 5ms per request
- ✅ Code coverage > 80% for new code
- ✅ Documentation complete and accurate
- ✅ Security review passed

### 10.3 Acceptance Criteria

- [ ] All tests passing
- [ ] Manual testing completed
- [ ] UAT testing successful
- [ ] Documentation reviewed and approved
- [ ] Code review completed
- [ ] Security scan passed (CodeQL)

---

## 11. Timeline

| Phase | Duration | Tasks |
|-------|----------|-------|
| **Phase 1: Implementation** | 2-3 hours | Schema changes, code updates, basic testing |
| **Phase 2: Testing** | 1-2 hours | Unit tests, integration tests, manual testing |
| **Phase 3: Documentation** | 1 hour | Create guides, update existing docs |
| **Phase 4: UAT** | 1-2 days | Test environment validation with real labels |
| **Phase 5: Production** | 1 day | Deployment and monitoring |

**Total Estimated Time:** 2-3 days from start to production

---

## 12. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Incorrect hash sequence with split payments | Medium | High | Thorough testing, verify with Easebuzz docs |
| Split amounts don't match transaction total | Medium | Medium | Validation logic, warning logs |
| Labels not matching Easebuzz configuration | Medium | High | Clear documentation, validation error messages |
| Backward compatibility broken | Low | Critical | Extensive testing, optional fields only |
| Performance degradation | Low | Medium | Performance testing, monitoring |

---

## 13. Dependencies

### 13.1 External Dependencies

- Easebuzz API support for split_payments parameter
- Easebuzz team providing valid labels for merchants
- Test environment access for validation

### 13.2 Internal Dependencies

- ERPNext framework (frappe)
- Existing Easebuzz integration
- Python 3.10+
- requests library

### 13.3 Assumptions

1. Easebuzz split_payments parameter format is stable
2. Labels are provided by Easebuzz team before configuration
3. Hash algorithm doesn't change with split payments
4. Response format includes split payment details
5. UAT environment supports split payments

---

## 14. Future Enhancements

### Potential Improvements (Out of Scope)

1. **UI for Split Configuration**: Visual editor for split payments instead of JSON
2. **Split Templates**: Reusable split configurations for common scenarios
3. **Dynamic Split Calculation**: Percentage-based splits calculated automatically
4. **Split Payment Reporting**: Dedicated reports for split payment analytics
5. **Multi-Level Splits**: Nested split configurations for complex scenarios
6. **Split Payment Reconciliation**: Tools to reconcile split amounts with settlements

---

## 15. References

### Documentation
- Easebuzz Initiate Payment API: https://docs.easebuzz.in/docs/payment-gateway/8ec545c331e6f-initiate-payment-api
- Easebuzz Webhooks: https://docs.easebuzz.in/docs/payment-gateway/587zy3v064so6-what-are-webhooks
- Easebuzz Transaction API V2.1: https://docs.easebuzz.in/docs/payment-gateway/6il9ej80xoydr-transaction-api-v2-1

### Code References
- `payments/payment_gateways/doctype/easebuzz_settings/easebuzz_settings.py`
- `payments/payment_gateways/doctype/easebuzz_settings/easebuzz_utils.py`
- `payments/payment_gateways/doctype/easebuzz_merchant/easebuzz_merchant.py`

### Related Issues
- Problem statement provided by user

---

## Conclusion

This implementation plan provides a comprehensive, surgical approach to integrating Easebuzz split payments while maintaining backward compatibility and code quality. The chosen strategy balances flexibility, security, and ease of use.

**Next Steps:**
1. Review and approve this plan
2. Begin Phase 1 implementation
3. Create agent skill documentation
4. Execute testing strategy
5. Deploy to UAT environment

---

**Document Version:** 1.0  
**Last Updated:** April 1, 2026  
**Status:** Ready for Implementation
