# CCAvenue Integration

This integration allows you to accept payments via CCAvenue in your Frappe/ERPNext site.

## Setup

1. Sign up for a CCAvenue account at [https://www.ccavenue.com](https://www.ccavenue.com)
2. Get your Merchant ID, Access Code and Encryption Key from CCAvenue dashboard
3. In your Frappe site, navigate to "CCAvenue Settings" and enter your credentials
4. Choose the environment (Sandbox for testing, Production for live payments)
5. Upload a header image (optional)
6. Save the settings

## Usage

To use CCAvenue in your application:

```python
payment_details = {
    "amount": 1000,
    "title": "Payment for Order #1234",
    "description": "Order payment",
    "reference_doctype": "Sales Order",
    "reference_docname": "SO-1234",
    "payer_name": "Customer Name",
    "payer_email": "customer@example.com",
    "order_id": "ORD-1234",
    "currency": "INR",
    "payment_gateway": "CCAvenue"
}


# Get the payment URL
from payments.utils import get_checkout_url
payment_url = get_checkout_url(**payment_details)
```

## Notes
 - CCAvenue primarily supports INR, USD, SGD, GBP, and EUR currencies
 - The integration uses AES encryption as required by CCAvenue
 - For webhook setup, please refer to the CCAvenue documentation
    ```

    ## Step 8: Installation and Testing

    ### Final Steps:

    1. Install the required dependencies:
    bench pip install -r apps/payments/requirements.txt
    ```
Run database migrations:
```
bench migrate
```
Clear cache and assets:
```
bench clear-cache && bench clear-website-cache && bench build
```
Restart the server:
```
bench restart
```
Set up the CCAvenue settings in your Frappe application at "CCAvenue Settings" doctype.

Test the integration using the sandbox environment before going live.

Important Notes
Encryption Implementation: You'll need to implement the actual encryption and decryption methods according to CCAvenue's documentation. The provided code includes placeholders that need to be completed.

Dependencies: Make sure to install the `pycryptodome` package for AES encryption.

Testing: Thoroughly test the integration using CCAvenue's sandbox environment before going live.

Documentation: Refer to CCAvenue's developer documentation for detailed API information.

Error Handling: Ensure proper error handling and logging is in place to track issues with transactions.

This implementation follows the same pattern as the existing Razorpay integration in your codebase, making it easier to maintain and understand for developers familiar with the existing payment gateways.