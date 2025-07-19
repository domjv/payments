import frappe
from frappe import _
import json

def handle_payment_authorization_payment_request(doc, method, status):
    payment_request = frappe.get_doc(doc)
    company = doc.company
    default_currency = frappe.db.get_value("Company", company, "default_currency")

    company_abbr = frappe.db.get_value("Company", company, "abbr")

    if doc.currency != default_currency:
        source_exchange_rate = frappe.db.get_value(
            "Currency Exchange",
            {"from_currency": doc.currency, "to_currency": default_currency},
            "exchange_rate",
        )
        if not source_exchange_rate:
            frappe.throw(f"Exchange Rate is missing for {doc.currency} to {default_currency}.")

    debtors_account = f"Debtors - {company_abbr}"
    bank_account = f"CCAvenue - {company_abbr}"

    integration_request = frappe.db.get_value(
        "Integration Request",
        {"reference_doctype": "Payment Request", "reference_docname": doc.name},
        "data"
    )

    reference_no = "INV-0001"

    if integration_request:
        reference_no = json.loads(integration_request).get("tracking_id")

    try:
        payment_entry = frappe.get_doc({
            "doctype": "Payment Entry",
            "payment_type": "Receive",
            "mode_of_payment": "CCAvenue",
            "party_type": doc.party_type,
            "party": doc.party,
            "party_name": doc.party,
            "company": company,
            "posting_date": frappe.utils.nowdate(),
            "received_amount": doc.grand_total,
            "paid_amount": doc.grand_total,
            "paid_from": debtors_account,
            "paid_to": bank_account,
            "paid_to_account_currency": default_currency,
            "reference_no": reference_no,
            "reference_date": frappe.utils.nowdate(),
            "source_exchange_rate": 1,
            "references": [
                {
                    "reference_doctype": "Sales Invoice",
                    "reference_name": doc.reference_name,
                    "total_amount": doc.grand_total,
                    "outstanding_amount": doc.grand_total,
                    "allocated_amount": doc.grand_total,
                    "payment_request": doc.name,
                    "account": debtors_account
                }
            ],
        })
        payment_entry.insert(ignore_permissions=True)
        payment_entry.submit()
    except Exception as e:
        frappe.log_error(
            f"Failed to create Payment Entry for Payment Request {doc.name}",
            message=str(e)
        )

def handle_payment_authorization_customer(doc, method, status):
    customer = frappe.get_doc(doc)
    integration_request = frappe.db.get_value(
        "Integration Request",
        {"reference_doctype": "Customer", "reference_docname": doc.name},
        "data"
    )
    request_data = json.loads(integration_request)

    remarks = request_data.get("description","")
    items_part = remarks.split("Items:")[1].split("|")[0].strip()
    item_codes_and_prices = [item.strip() for item in items_part.split(",")]
    item_codes = [item.split("=")[0].strip() for item in item_codes_and_prices]
    item_prices = [item.split("=")[1].strip() for item in item_codes_and_prices]
    merchant_name = request_data.get("custom_merchant_name")
    merchant_dict = {}
    if merchant_name:
        merchant_dict = frappe.get_doc("CCAvenue Merchant", merchant_name).as_dict()
    total_amount = 0
    for item_price in item_prices:
        total_amount = total_amount + float(item_price)

    company = doc.custom_hostel_name
    debtors_account_name = "Debtors"
    bank_account_name = "CCAvenue"
    if merchant_name and merchant_dict:
        if merchant_dict.get("company") is not None and merchant_dict.get("company") != "":
            company = merchant_dict.get("company")
        if merchant_dict.get("bank_account") is not None and merchant_dict.get("bank_account") != "":
            bank_account_name = merchant_dict.get("bank_account")
        if merchant_dict.get("debtors_account") is not None and merchant_dict.get("debtors_account") != "":
            debtors_account_name = merchant_dict.get("debtors_account")
        remarks = remarks + f" for merchant name = {merchant_name}"
    default_currency = frappe.db.get_value("Company", company, "default_currency")
    company_abbr = frappe.db.get_value("Company", company, "abbr")

    source_exchange_rate = 1

    debtors_account = f"{debtors_account_name} - {company_abbr}"
    bank_account = f"{bank_account_name} - {company_abbr}"

    try:
        payment_entry = frappe.get_doc({
            "doctype": "Payment Entry",
            "payment_type": "Receive",
            "mode_of_payment": "CCAvenue",
            "party_type": "Customer",
            "party": doc.name,  # Customer name
            "party_name": doc.name,
            "company": company,
            "posting_date": frappe.utils.nowdate(),
            "received_amount": total_amount,
            "paid_amount": total_amount,
            "paid_from": debtors_account,
            "paid_to": bank_account,
            "paid_to_account_currency": default_currency,
            "reference_no": request_data.get("tracking_id"),
            "reference_date": frappe.utils.nowdate(),
            "source_exchange_rate": source_exchange_rate,
            "remarks": remarks
        })

        payment_entry.insert(ignore_permissions=True)
        payment_entry.submit()

        try:
            invoice_items = []
            for item_code in item_codes:
                item_price = item_prices[item_codes.index(item_code)]
                item_name = frappe.db.get_value("Item", item_code, "item_name")

                invoice_items.append({
                    "item_code": item_code,
                    "item_name": item_name,
                    "qty": 1,
                    "rate": item_price,
                    "amount": item_price,
                    "uom": "Nos",
                    "conversion_factor": 1.0,
                    "cost_center": f"Main - {company_abbr}",
                    "income_account": f"Sales - {company_abbr}"
                })

            # Create sales invoice
            sales_invoice = frappe.get_doc({
                "doctype": "Sales Invoice",
                "customer": doc.name,
                "company": company,
                "posting_date": frappe.utils.nowdate(),
                "currency": default_currency,
                "price_list": "Standard Selling",
                "price_list_currency": default_currency,
                "debit_to": debtors_account,
                "items": invoice_items,
                "remarks": remarks,
                "is_pos": 0,
                "disable_rounded_total": 1,
                "update_stock": 0,
                "allocate_advances_automatically": 1,
                "advances": [{
                    "reference_type": "Payment Entry",
                    "reference_name": payment_entry.name,
                    "reference_row": None,
                    "advance_amount": total_amount,
                    "allocated_amount": total_amount,
                    "remarks": f"Amount {default_currency} {total_amount} received from {doc.name}\nTransaction reference no {request_data.get('tracking_id')} dated {frappe.utils.nowdate()}"
                }]
            })

            sales_invoice.insert(ignore_permissions=True)
            sales_invoice.submit()

            try:
                for item_code in item_codes:
                    optional_service_record = frappe.get_doc({
                        "doctype": "Optional Service Record",
                        "company": company,
                        "customer": doc.name,
                        "payment_entry": payment_entry.name,
                        "sales_invoice": sales_invoice.name,
                        "item": item_code,
                        "price": item_prices[item_codes.index(item_code)]
                    })
                    optional_service_record.insert(ignore_permissions=True)
                    optional_service_record.submit()
            except Exception as e:
                frappe.log_error(
                    f"Failed to create Optional Service Records for Customer {doc.name}",
                    message=str(e)
                )
        except Exception as e:
            frappe.log_error(
                f"Failed to create Sales Invoice for Customer {doc.name}",
                message=str(e)
            )
    except Exception as e:
        frappe.log_error(
            f"Failed to create Payment Entry for Customer {doc.name}",
            message=str(e)
        )

@frappe.whitelist(allow_guest=True)
def handle_cart_submit():
    data = json.loads(frappe.form_dict.get("requestObj"))
    cart_data = data.get("cart")
    customer_id = data.get("customer")
    remarks = None

    # --- Validate Inputs ---
    if not cart_data or not customer_id:
        frappe.response['success'] = False
        frappe.response['message'] = "Missing required parameters: cart and customer."
        frappe.throw(_("Missing required parameters: cart and customer."))

    if not isinstance(cart_data, list):
        frappe.response['success'] = False
        frappe.response['message'] = "Invalid cart data.  Must be a list."
        frappe.throw(_("Invalid cart data. Must be a list."))

    total_amount = 0.0
    merchant_name = None
    item_code_and_price = []
    for item in cart_data:
        if not isinstance(item, dict) or 'itemCode' not in item or 'price' not in item:
            frappe.response['success'] = False
            frappe.response['message'] = "Invalid item in cart.  Each item must have itemCode and price."
            frappe.throw(_("Invalid item data. Each item must be a dictionary with a 'itemCode' and 'price'."))

        item_doc = frappe.get_doc("Item", item["itemCode"]).as_dict()
        local_merchant_name = item_doc.get("custom_merchant_account")
        if (merchant_name is not None and merchant_name != "" and local_merchant_name != merchant_name) or ( merchant_name == "" and local_merchant_name is not None ) :
            frappe.response['success'] = False
            frappe.response['message'] = "Invalid merchant name. All items must have the same merchant name."
            return

        if local_merchant_name is not None:
            merchant_name = local_merchant_name
        else:
            merchant_name = ""

        total_amount = total_amount + float(item['price'])
        item_code_and_price.append(f"{item['itemCode']} = {round(item['price'], 2)}")

    if total_amount <= 0:
        frappe.response['success'] = False
        frappe.response['message'] = "Total amount must be greater than zero."
        frappe.throw(_("Total amount must be greater than zero."))

    if remarks is None:
        remarks = f"Items: {', '.join(item_code_and_price)} | Student ID: {customer_id}"
    else:
        remarks = f"{remarks} | Items: {', '.join(item_code_and_price)} | Student ID: {customer_id}"

    try:
        controller = frappe.get_doc("CCAvenue Settings")

        customer = frappe.get_doc("Customer", customer_id)

        total_money_to_pay = round(total_amount, 2)
        payment_url = controller.get_payment_url(
            amount=total_money_to_pay,
            currency="INR",
            description=remarks,
            order_id = customer.customer_name,
            payer_name=customer.customer_name,
            payer_email=frappe.session.user,
            payment_gateway="CCAvenue",
            reference_docname=customer.name,
            reference_doctype="Customer",
            custom_merchant_name=merchant_name,
        )


        if not payment_url:
            frappe.response['success'] = False
            frappe.response['message'] = "Failed to create Razorpay order."
            frappe.throw(_("Failed to create Razorpay order."))

        frappe.response['success'] = True
        frappe.response['message'] = "Order created successfully."
        frappe.response['payment_url'] = payment_url


    except Exception as e:
        frappe.log_error("Razorpay Order Creation Error", str(e))
        frappe.response['success'] = False
        frappe.response['message'] = f"An error occurred while creating the payment order: {str(e)}"

def process_ccavenue_payment_safely(order_id, tracking_id, status, source="Unknown"):
    """
    Centralized function to process CCAvenue payments safely without duplicates.
    This function should be called from both normal flow and webhook flow.
    
    Args:
        order_id: The order ID from CCAvenue
        tracking_id: The tracking ID from CCAvenue
        status: Payment status (Success, Shipped, etc.)
        source: Source of the payment (Normal Flow, Echo, Reconciliation, etc.)
    """
    if not order_id or not tracking_id:
        frappe.logger().warning(f"Missing order_id or tracking_id for {source}")
        return False
        
    # Extract Payment Request name from order_id
    pr_name = order_id.split("@")[0] if "@" in order_id else order_id
    
    try:
        # Use database-level check to prevent race conditions
        with frappe.db.transaction():
            # Double-check if Payment Entry already exists for this tracking_id (atomic operation)
            existing_payment = frappe.db.get_value("Payment Entry", {"reference_no": tracking_id}, "name")
            if existing_payment:
                frappe.logger().info(f"Payment Entry already exists for tracking_id: {tracking_id} (found: {existing_payment})")
                
                # Still update Payment Request status if not already paid
                try:
                    pr = frappe.get_doc("Payment Request", pr_name)
                    if pr.status != "Paid":
                        pr.db_set("status", "Paid")
                        pr.add_comment("Comment", text=f"Payment status updated via CCAvenue {source}. Tracking ID: {tracking_id} (Payment Entry: {existing_payment})")
                        
                        # Update reference document status
                        ref_doc = frappe.get_doc(pr.reference_doctype, pr.reference_name)
                        ref_doc.db_set("status", "Paid")
                        ref_doc.add_comment("Comment", text=f"Payment status updated via CCAvenue {source}. Tracking ID: {tracking_id} (Payment Entry: {existing_payment})")
                except Exception as e:
                    frappe.log_error(f"Failed to update Payment Request status for existing payment: {str(e)}", f"CCAvenue {source} Status Update Error")
                
                return True
            
            # Check if Payment Request is already paid
            try:
                pr = frappe.get_doc("Payment Request", pr_name)
                if pr.status == "Paid":
                    frappe.logger().info(f"Payment Request {pr.name} already marked as Paid")
                    return True
            except frappe.DoesNotExistError:
                frappe.log_error(f"Payment Request not found for order_id: {order_id}", f"CCAvenue {source} Payment Error")
                return False
            
            # Only proceed if status indicates success
            if status not in ["Success", "Shipped"]:
                frappe.logger().info(f"Payment status '{status}' is not successful for {pr.name}")
                return False
            
            # Update Integration Request data with tracking_id
            try:
                integration_request_name = order_id.split("@")[1] if "@" in order_id else None
                if integration_request_name:
                    integration_request = frappe.get_doc("Integration Request", integration_request_name)
                    existing_data = json.loads(integration_request.data) if integration_request.data else {}
                    existing_data.update({
                        "tracking_id": tracking_id,
                        "order_status": status,
                        "webhook_source": source
                    })
                    integration_request.data = json.dumps(existing_data)
                    integration_request.save(ignore_permissions=True)
            except Exception as e:
                frappe.log_error(f"Failed to update Integration Request with tracking_id: {str(e)}", f"CCAvenue {source} Error")
            
            # Create Payment Entry using existing utility function with additional safety
            try:
                handle_payment_authorization_payment_request(pr, "on_payment_authorized", "Completed")
            except Exception as e:
                # Check if this is a duplicate key error
                if "Duplicate entry" in str(e) or "UNIQUE constraint failed" in str(e):
                    frappe.logger().info(f"Payment Entry already exists (caught by database constraint) for tracking_id: {tracking_id}")
                    # Still update Payment Request status if not already paid
                    if pr.status != "Paid":
                        pr.db_set("status", "Paid")
                        pr.add_comment("Comment", text=f"Payment status updated via CCAvenue {source}. Tracking ID: {tracking_id} (caught duplicate)")
                        
                        # Update reference document status
                        ref_doc = frappe.get_doc(pr.reference_doctype, pr.reference_name)
                        ref_doc.db_set("status", "Paid")
                        ref_doc.add_comment("Comment", text=f"Payment status updated via CCAvenue {source}. Tracking ID: {tracking_id} (caught duplicate)")
                    return True
                else:
                    # Re-raise if it's not a duplicate error
                    raise
            
            # Update Payment Request status
            pr.db_set("status", "Paid")
            pr.add_comment("Comment", text=f"Payment updated via CCAvenue {source}. Tracking ID: {tracking_id}")
            
            # Update reference document status
            ref_doc = frappe.get_doc(pr.reference_doctype, pr.reference_name)
            ref_doc.db_set("status", "Paid")
            ref_doc.add_comment("Comment", text=f"Payment updated via CCAvenue {source}. Tracking ID: {tracking_id}")
            
            frappe.logger().info(f"Payment Entry created for {pr.name} via {source}. Tracking ID: {tracking_id}")
            return True
            
    except Exception as e:
        frappe.log_error(f"Failed to process payment for {pr_name} via {source}: {str(e)}", f"CCAvenue {source} Payment Error")
        return False

def ensure_payment_entry_unique_constraint():
    """
    Ensure that Payment Entry reference_no field has a unique constraint to prevent duplicates.
    This should be called during app installation or migration.
    Unfortunatly, this  cannot be used as there are chances that multiple invoices are paid for the same tracking_id when paid manually.
    So, we need to clean up the duplicate payment entries manually, only for CCAvenue payments.
    This function is not used in the code, but is kept here for reference.
    """
    try:
        # Check if unique constraint already exists
        constraints = frappe.db.sql("""
            SELECT CONSTRAINT_NAME 
            FROM information_schema.TABLE_CONSTRAINTS 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = 'tabPayment Entry' 
            AND CONSTRAINT_TYPE = 'UNIQUE'
            AND CONSTRAINT_NAME LIKE '%reference_no%'
        """, as_dict=True)
        
        if not constraints:
            # Add unique constraint on reference_no field
            frappe.db.sql("""
                ALTER TABLE `tabPayment Entry` 
                ADD UNIQUE INDEX `unique_reference_no` (`reference_no`)
            """)
            frappe.logger().info("Added unique constraint on Payment Entry reference_no field")
        else:
            frappe.logger().info("Unique constraint on Payment Entry reference_no field already exists")
            
    except Exception as e:
        frappe.log_error(f"Failed to add unique constraint on Payment Entry reference_no: {str(e)}", "Payment Entry Constraint Error")

def cleanup_duplicate_payment_entries():
    """
    Clean up existing duplicate Payment Entries by keeping only the first one for each tracking_id.
    Instead of deleting, set the status of the duplicate entries to 'Cancelled'.
    This should be called before adding the unique constraint.
    """
    try:
        # Find duplicate Payment Entries by reference_no
        duplicates = frappe.db.sql("""
            SELECT reference_no, COUNT(*) as count, GROUP_CONCAT(name ORDER BY creation) as payment_entries
            FROM `tabPayment Entry` 
            WHERE reference_no IS NOT NULL AND reference_no != '' AND mode_of_payment = 'CCAvenue' AND status = 'Submitted'
            GROUP BY reference_no 
            HAVING COUNT(*) > 1
        """, as_dict=True)
        
        if not duplicates:
            frappe.logger().info("No duplicate Payment Entries found")
            return
            
        frappe.logger().info(f"Found {len(duplicates)} duplicate Payment Entry groups to clean up")
        
        for duplicate in duplicates:
            reference_no = duplicate.reference_no
            payment_entries = duplicate.payment_entries.split(',')
            
            # Keep the first one (oldest by creation), cancel the rest
            to_keep = payment_entries[0]
            to_cancel = payment_entries[1:]
            
            frappe.logger().info(f"Cleaning up duplicates for reference_no {reference_no}: keeping {to_keep}, cancelling {to_cancel}")
            
            for payment_entry_name in to_cancel:
                try:
                    # Check if the Payment Entry is submitted
                    docstatus = frappe.db.get_value("Payment Entry", payment_entry_name, "docstatus")
                    if docstatus == 1:
                        # Cancel the Payment Entry (do not delete)
                        pe = frappe.get_doc("Payment Entry", payment_entry_name)
                        pe.cancel()
                        frappe.logger().info(f"Cancelled Payment Entry: {payment_entry_name}")
                    else:
                        # If not submitted, just set status to 'Cancelled'
                        frappe.db.set_value("Payment Entry", payment_entry_name, "status", "Cancelled")
                        frappe.db.set_value("Payment Entry", payment_entry_name, "docstatus", 2)
                        frappe.logger().info(f"Set Payment Entry to Cancelled: {payment_entry_name}")
                except Exception as e:
                    frappe.log_error(f"Failed to cancel Payment Entry {payment_entry_name}: {str(e)}", "Payment Entry Cleanup Error")
                    
    except Exception as e:
        frappe.log_error(f"Failed to cleanup duplicate Payment Entries: {str(e)}", "Payment Entry Cleanup Error")

@frappe.whitelist()
def fix_duplicate_payment_entries():
    """
    Manual function to fix duplicate Payment Entries.
    This can be called from the desk or via API.
    """
    try:
        frappe.logger().info("Starting duplicate Payment Entry cleanup...")
        
        # Clean up existing duplicates
        cleanup_duplicate_payment_entries()
        
        frappe.logger().info("Successfully cleaned up duplicate Payment Entries")
        return {"success": True, "message": "Duplicate Payment Entries cleaned up"}
        
    except Exception as e:
        frappe.log_error(f"Failed to fix duplicate Payment Entries: {str(e)}", "Payment Entry Fix Error")
        return {"success": False, "message": f"Failed to fix duplicate Payment Entries: {str(e)}"}