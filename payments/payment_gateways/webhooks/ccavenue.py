import frappe
from payments.payment_gateways.doctype.ccavenue_settings.ccavenue_utils import decrypt
from payments.payment_gateways.doctype.ccavenue_settings.ccavenue_settings import get_working_key

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

        working_key = get_working_key()
        if not working_key:
            frappe.log_error("Missing working key", f"CCAvenue {source}")
            return "Missing working key"
        
        decrypted = decrypt(enc_resp, working_key)
        data = dict(item.split('=') for item in decrypted.split('&') if '=' in item)

        # 👇 Switch to privileged user context
        frappe.set_user("Administrator")
        _process_payment_update(data, source)

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"CCAvenue {source} Error")

    finally:
        # 👇 Always revert back
        frappe.set_user("Guest")

def _process_payment_update(data, source):
    order_id = data.get("order_id")
    status = data.get("order_status")
    amount = data.get("amount")

    if not order_id or not status:
        frappe.log_error(data, "Missing Order ID or Status")
        return

    try:
        pr_name = order_id.split("@")[0] if "@" in order_id else order_id
        pr = frappe.get_doc("Payment Request", {"name": pr_name})
    except frappe.DoesNotExistError:
        frappe.log_error(f"Payment Request not found for order_id: {order_id}", f"CCAvenue {source} Webhook Payment Error")
        return

    if pr.status == "Paid":
        frappe.logger().info(f"Payment already marked Paid for {pr.name}") 
        return

    # TODO: Uncomment this when we have a way to handle amount mismatch
    # # Verify amount matches
    # if amount and float(amount) != float(pr.grand_total):
    #     frappe.log_error(
    #         f"Amount mismatch - CCAvenue: {amount}, Payment Request: {pr.grand_total}",
    #         f"CCAvenue {source} Webhook Payment Error"
    #     )
    #     return

    if status in ["Success", "Shipped"]:
        if frappe.db.exists("Payment Entry", {"reference_no": data.get("tracking_id")}):
            frappe.log_error(f"Payment Entry already exists for {data.get('tracking_id')}", f"CCAvenue {source} Webhook Payment Error")
            return
        _create_payment_entry(pr, data, source)
        pr.db_set("status", "Paid")
        pr.add_comment("Comment", text=f"Payment updated via CCAvenue {source} webhook with status {status}. Tracking ID: {data.get('tracking_id')}")
        
        ref_doc = frappe.get_doc(pr.reference_doctype, pr.reference_name)
        ref_doc.db_set("status", "Paid")
        ref_doc.add_comment("Comment", text=f"Payment updated via CCAvenue {source} webhook with status {status}. Tracking ID: {data.get('tracking_id')}")
    elif status in ["Failure", "Aborted", "Invalid"]:
        pr.db_set("status", "Cancelled")
        pr.add_comment("Comment", text=f"Payment cancelled via CCAvenue {source} webhook with status {status}. Tracking ID: {data.get('tracking_id')}")

def _create_payment_entry(pr, data, source):
    company = pr.company

    # Get default account for this company under CCAvenue Mode of Payment
    bank_account = frappe.db.get_value(
        "Mode of Payment Account",
        filters={
            "parent": "CCAvenue",
            "parenttype": "Mode of Payment",
            "company": company
        },
        fieldname="default_account"
    )

    if not bank_account:
        frappe.log_error(
            f"No default account configured for company {company} under Mode of Payment 'CCAvenue'",
            f"CCAvenue {source} Webhook Payment Error"
        )
        return

    pe = frappe.new_doc("Payment Entry")
    pe.company = company  # 👈 Set early to prevent validation issue

    pe.update({
        "payment_type": "Receive",
        "party_type": pr.party_type,
        "party": pr.party,
        "paid_to": bank_account,
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
    pe.add_comment("Comment", text=f"Payment Entry created via CCAvenue {source} webhook. Tracking ID: {data.get('tracking_id')}")
    frappe.logger().info(f"Payment Entry created for {pr.name}")