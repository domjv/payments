import frappe
from payments.payment_gateways.ccavenue_settings.utils import decrypt

@frappe.whitelist(allow_guest=True)
def order_status():
    frappe.log_error(frappe.local.form_dict, "CCAvenue Order Status Redirect")
    return "OK"

@frappe.whitelist(allow_guest=True)
def order_status_echo():
    _handle_ccavenue("Echo")

@frappe.whitelist(allow_guest=True)
def reconciliation_status():
    _handle_ccavenue("Reconciliation")

def _handle_ccavenue(source):
    try:
        enc_resp = frappe.local.form_dict.get("encResp")
        if not enc_resp:
            frappe.log_error("Missing encResp", f"CCAvenue {source}")
            return "Missing encResp"

        from payments.payment_gateways.ccavenue_settings.ccavenue_settings import get_working_key
        working_key = get_working_key()

        decrypted = decrypt(enc_resp, working_key)
        frappe.log_error(decrypted, f"CCAvenue {source} Decrypted")

        data = dict(item.split('=') for item in decrypted.split('&') if '=' in item)
        _process_payment_update(data)

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"CCAvenue {source} Error")

def _process_payment_update(data):
    order_id = data.get("order_id")
    status = data.get("order_status")

    if not order_id or not status:
        frappe.log_error(data, "Missing Order ID or Status")
        return

    pr = frappe.get_doc("Payment Request", {"reference_name": order_id})
    if pr.status == "Paid":
        return

    if status in ["Success", "Shipped"]:
        _create_payment_entry(pr, data)
        pr.db_set("status", "Paid")
        frappe.get_doc(pr.reference_doctype, pr.reference_name).db_set("status", "Paid")
    elif status in ["Failure", "Aborted", "Invalid"]:
        pr.db_set("status", "Cancelled")

def _create_payment_entry(pr, data):
    pe = frappe.get_doc({
        "doctype": "Payment Entry",
        "payment_type": "Receive",
        "party_type": pr.party_type,
        "party": pr.party,
        "paid_to": "Bank - COMPANY",  # Replace with actual account
        "paid_amount": pr.grand_total,
        "received_amount": pr.grand_total,
        "reference_no": data.get("tracking_id"),
        "reference_date": frappe.utils.nowdate(),
        "mode_of_payment": "CCAvenue",
        "references": [{
            "reference_doctype": pr.reference_doctype,
            "reference_name": pr.reference_name,
            "allocated_amount": pr.grand_total
        }]
    })
    pe.insert()
    pe.submit()