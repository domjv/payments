import frappe
from payments.payment_gateways.doctype.ccavenue_settings.ccavenue_utils import decrypt
from payments.payment_gateways.doctype.ccavenue_settings.ccavenue_settings import get_working_key
from payments.utils.ivyliving_methods import handle_payment_authorization_payment_request
import json

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

        # 👇 Log webhook data for debugging
        frappe.logger().info(f"CCAvenue {source} webhook received - Order ID: {data.get('order_id')}, Status: {data.get('order_status')}")

        # 👇 Switch to privileged user context
        frappe.set_user("Administrator")
        _process_payment_update(data, source)

    except Exception as e:
        frappe.log_error(f"CCAvenue {source} webhook error: {str(e)}\n{frappe.get_traceback()}", f"CCAvenue {source} Error")
        return f"Error processing {source} webhook"

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

    # 👇 Add date filtering for reconciliation webhooks to ignore very old transactions
    if source == "Reconciliation":
        # Get max days configuration from CCAvenue Settings
        try:
            ccavenue_settings = frappe.get_doc("CCAvenue Settings")
            max_days = getattr(ccavenue_settings, 'reconciliation_max_days', 2)  # Default to 2 days
        except:
            max_days = 2  # Fallback default
            
        # Check if this is a very old transaction
        try:
            integration_request_name = order_id.split("@")[1] if "@" in order_id else None
            if integration_request_name:
                integration_request = frappe.get_doc("Integration Request", integration_request_name)
                days_old = (frappe.utils.now_datetime() - integration_request.creation).days
                
                if days_old > max_days:
                    frappe.logger().info(f"Skipping old reconciliation webhook for order_id: {order_id} (created {days_old} days ago, max allowed: {max_days} days)")
                    return
                    
        except Exception as e:
            frappe.log_error(f"Failed to check transaction age for {order_id}: {str(e)}", f"CCAvenue {source} Age Check Error")
            # Continue processing if we can't determine the age

    # 👇 Update Integration Request (similar to normal flow)
    try:
        integration_request_name = order_id.split("@")[1] if "@" in order_id else None
        if integration_request_name:
            integration_request = frappe.get_doc("Integration Request", integration_request_name)
            
            # Update integration request data
            existing_data = json.loads(integration_request.data) if integration_request.data else {}
            existing_data.update({
                "order_status": status,
                "tracking_id": data.get("tracking_id"),
                "bank_ref_no": data.get("bank_ref_no"),
                "payment_mode": data.get("payment_mode"),
                "failure_message": data.get("failure_message"),
                "ccavenue_response": data,
                "webhook_source": source
            })
            integration_request.data = json.dumps(existing_data)
            integration_request.save(ignore_permissions=True)
            
            # Update integration request status
            if status in ["Success", "Shipped"]:
                integration_request.update_status(existing_data, "Completed")
            elif status in ["Failure", "Aborted", "Invalid"]:
                integration_request.update_status(existing_data, "Failed")
                
    except Exception as e:
        frappe.log_error(f"Failed to update Integration Request: {str(e)}", f"CCAvenue {source} Webhook Error")

    # Use centralized function to prevent duplicates
    from payments.utils.ivyliving_methods import process_ccavenue_payment_safely
    
    if status in ["Success", "Shipped"]:
        # Process payment using centralized function
        success = process_ccavenue_payment_safely(order_id, data.get("tracking_id"), status, source)
        
        if success:
            frappe.logger().info(f"Payment processed successfully via {source} webhook for order_id: {order_id}")
            # 👇 Send email notification for reconciliation webhooks
            if source == "Reconciliation":
                try:
                    frappe.sendmail(
                        recipients=["dominic.v@pleasantbiz.com"],
                        subject=f"CCAvenue Reconciliation Webhook Payment Update - {order_id}",
                        message=f"""
                            Payment Request has been updated via CCAvenue Reconciliation.
                            <br><br>
                            Details:
                            <br>
                            - Order ID: {data.get('order_id')}
                            <br>
                            - Status: {data.get('order_status')}
                            <br>
                            - Amount: {data.get('amount')}
                            <br>
                            - Tracking ID: {data.get('tracking_id')}
                        """,
                        now=True
                    )
                except Exception as e:
                    frappe.log_error(f"Failed to send reconciliation email: {str(e)}", f"CCAvenue {source} Email Error")
                    
        else:
            frappe.log_error(f"Payment processing failed via {source} webhook for order_id: {order_id}", f"CCAvenue {source} Webhook Error")
            
    elif status in ["Failure", "Aborted", "Invalid", "Unsuccessful"]:
        # Handle failed payments
        try:
            pr_name = order_id.split("@")[0] if "@" in order_id else order_id
            pr = frappe.get_doc("Payment Request", {"name": pr_name})
            
            # Use proper cancellation method instead of just db_set
            if pr.docstatus == 1:
                pr.cancel()
                pr.add_comment("Comment", text=f"Payment cancelled via CCAvenue {source} webhook with status {status}. Tracking ID: {data.get('tracking_id')}")
            else:
                pr.db_set("status", "Cancelled")
                pr.add_comment("Comment", text=f"Payment status updated to Cancelled via CCAvenue {source} webhook with status {status}. Tracking ID: {data.get('tracking_id')}")
        except Exception as e:
            frappe.log_error(f"Failed to handle failed payment for {order_id}: {str(e)}", f"CCAvenue {source} Cancellation Error")