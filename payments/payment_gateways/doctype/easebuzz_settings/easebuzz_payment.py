import frappe
import requests
from frappe import _
from payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings import EasebuzzSettings

@frappe.whitelist(allow_guest=True)
def make_payment(amount, currency, order_id, customer_email, customer_phone):
    """Create a payment request and redirect to Easebuzz."""
    settings = frappe.get_doc("Easebuzz Settings")
    if not settings.api_key or not settings.secret_key:
        frappe.throw(_("Please configure Easebuzz Settings."))

    # Prepare payload
    payload = {
        "amount": amount,
        "currency": currency,
        "txnid": order_id,
        "email": customer_email,
        "phone": customer_phone,
        "productinfo": "Payment for Order",
        "surl": frappe.utils.get_url("/api/method/payments.payment_gateways.doctype.easebuzz_settings.easebuzz_payment.handle_callback"),
        "furl": frappe.utils.get_url("/payment-failed"),
    }

    # Make the API request
    try:
        response = requests.post(
            settings.get_payment_url(),
            json=payload,
            headers=settings.get_headers()
        )
        response_data = response.json()
        if response.status_code == 200 and response_data.get("status") == "success":
            return {"redirect_url": response_data.get("payment_url")}
        else:
            frappe.throw(_("Failed to create payment: {0}").format(response_data.get("message")))
    except Exception as e:
        frappe.throw(_("An error occurred while creating the payment: {0}").format(str(e)))

@frappe.whitelist(allow_guest=True)
def handle_callback():
    """Handle the callback from Easebuzz."""
    data = frappe.local.form_dict
    if not data:
        frappe.throw(_("No data received from Easebuzz."))

    # Verify the signature (if required by Easebuzz)
    # Add your signature verification logic here

    # Process the payment status
    if data.get("status") == "success":
        # Mark the payment as successful
        frappe.db.set_value("Payment Entry", data.get("txnid"), "status", "Completed")
        frappe.db.commit()
        frappe.local.response["type"] = "redirect"
        frappe.local.response["location"] = "/payment-success"
    else:
        # Mark the payment as failed
        frappe.db.set_value("Payment Entry", data.get("txnid"), "status", "Failed")
        frappe.db.commit()
        frappe.local.response["type"] = "redirect"
        frappe.local.response["location"] = "/payment-failed"