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

    # Resolve gateway from integration request
    ir_row = frappe.db.get_value(
        "Integration Request",
        {"reference_doctype": "Payment Request", "reference_docname": doc.name},
        ["data", "integration_request_service"],
        as_dict=True,
    )

    ir_data = {}
    service = ""
    reference_no = "INV-0001"

    if ir_row:
        ir_data = json.loads(ir_row.get("data") or "{}")
        service = ir_row.get("integration_request_service") or ""

    if service == "Razorpay":
        notes = ir_data.get("notes") or {}
        if isinstance(notes, str):
            try:
                notes = json.loads(notes)
            except Exception:
                notes = {}
        merchant_name = ir_data.get("custom_merchant_name") or (
            notes.get("merchant_name") if isinstance(notes, dict) else None
        )
        merchant_doc = None
        if merchant_name:
            try:
                merchant_doc = frappe.get_doc("Razorpay Merchant", merchant_name)
            except Exception:
                pass
        if not merchant_doc:
            try:
                rzp_settings = frappe.get_doc("Razorpay Settings")
                merchant_doc = rzp_settings.get_merchant_for_company(company=company)
            except Exception:
                pass
        debtors_account = f"{merchant_doc.debtors_account} - {company_abbr}" if (merchant_doc and merchant_doc.get("debtors_account")) else f"Debtors - {company_abbr}"
        bank_account = f"{merchant_doc.bank_account} - {company_abbr}" if (merchant_doc and merchant_doc.get("bank_account")) else f"Razorpay - {company_abbr}"
        reference_no = ir_data.get("razorpay_payment_id") or ir_data.get("razorpay_order_id") or "INV-0001"
        mode_of_payment = "Razorpay"
    elif service == "Easebuzz":
        merchant_name = ir_data.get("custom_merchant_name")
        merchant_doc = None
        if merchant_name:
            try:
                merchant_doc = frappe.get_doc("Easebuzz Merchant", merchant_name)
            except Exception:
                pass
        if not merchant_doc:
            try:
                eb_settings = frappe.get_doc("Easebuzz Settings")
                merchant_doc = eb_settings.get_merchant_for_company(company=company)
            except Exception:
                pass
        debtors_account = f"{merchant_doc.debtors_account} - {company_abbr}" if (merchant_doc and merchant_doc.get("debtors_account")) else f"Debtors - {company_abbr}"
        bank_account = f"{merchant_doc.bank_account} - {company_abbr}" if (merchant_doc and merchant_doc.get("bank_account")) else f"Easebuzz - {company_abbr}"
        reference_no = ir_data.get("easepayid") or ir_data.get("txnid") or "INV-0001"
        mode_of_payment = "Easebuzz"
    else:
        # CCAvenue (default)
        debtors_account = f"Debtors - {company_abbr}"
        bank_account = f"CCAvenue - {company_abbr}"
        reference_no = ir_data.get("tracking_id") or "INV-0001"
        mode_of_payment = "CCAvenue"

    integration_request = frappe.db.get_value(
        "Integration Request",
        {"reference_doctype": "Payment Request", "reference_docname": doc.name},
        "data"
    )

    if integration_request and service not in ("Razorpay", "Easebuzz"):
        reference_no = json.loads(integration_request).get("tracking_id") or reference_no

    try:
        payment_entry = frappe.get_doc({
            "doctype": "Payment Entry",
            "payment_type": "Receive",
            "mode_of_payment": mode_of_payment,
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
    ir_row = frappe.db.get_value(
        "Integration Request",
        {"reference_doctype": "Customer", "reference_docname": doc.name},
        ["data", "integration_request_service"],
        as_dict=True,
    )
    if not ir_row:
        frappe.log_error(
            f"Integration Request not found for Customer {doc.name}",
            "Customer Payment Authorization Error",
        )
        return
    integration_request = ir_row.get("data")
    service = ir_row.get("integration_request_service") or ""
    request_data = json.loads(integration_request)

    remarks = request_data.get("description","")
    items_part = remarks.split("Items:")[1].split("|")[0].strip()
    item_codes_and_prices = [item.strip() for item in items_part.split(",")]
    item_codes = [item.split("=")[0].strip() for item in item_codes_and_prices]
    item_prices = [item.split("=")[1].strip() for item in item_codes_and_prices]
    merchant_name = request_data.get("custom_merchant_name")
    merchant_dict = {}

    if service == "Razorpay":
        notes = request_data.get("notes") or {}
        if isinstance(notes, str):
            try:
                notes = json.loads(notes)
            except Exception:
                notes = {}
        merchant_name = merchant_name or (notes.get("merchant_name") if isinstance(notes, dict) else None)
        if merchant_name:
            try:
                merchant_dict = frappe.get_doc("Razorpay Merchant", merchant_name).as_dict()
            except Exception:
                frappe.log_error(f"Razorpay Merchant {merchant_name} not found, using default")
        if not merchant_dict:
            company = doc.custom_hostel_name
            try:
                rzp_settings = frappe.get_doc("Razorpay Settings")
                merchant_doc = rzp_settings.get_merchant_for_company(company=company)
                if merchant_doc:
                    merchant_dict = merchant_doc.as_dict()
                    merchant_name = merchant_doc.name
            except Exception:
                pass
    elif service == "Easebuzz":
        if merchant_name:
            try:
                merchant_dict = frappe.get_doc("Easebuzz Merchant", merchant_name).as_dict()
            except Exception:
                frappe.log_error(f"Easebuzz Merchant {merchant_name} not found, using default")
        if not merchant_dict:
            company = doc.custom_hostel_name
            try:
                eb_settings = frappe.get_doc("Easebuzz Settings")
                merchant_doc = eb_settings.get_merchant_for_company(company=company)
                if merchant_doc:
                    merchant_dict = merchant_doc.as_dict()
                    merchant_name = merchant_doc.name
            except Exception:
                pass
    else:
        # CCAvenue (default)
        if merchant_name:
            try:
                merchant_dict = frappe.get_doc("CCAvenue Merchant", merchant_name).as_dict()
            except Exception:
                frappe.log_error(f"Merchant {merchant_name} not found, using default")
                merchant_dict = {}

        if not merchant_dict:
            company = doc.custom_hostel_name
            settings = frappe.get_doc("CCAvenue Settings")
            merchant_doc = settings.get_merchant_for_company(company=company)
            if merchant_doc:
                merchant_dict = merchant_doc.as_dict()
                merchant_name = merchant_doc.name
    
    total_amount = 0
    for item_price in item_prices:
        total_amount = total_amount + float(item_price)

    company = doc.custom_hostel_name
    debtors_account_name = "Debtors"
    if service == "Razorpay":
        bank_account_name = "Razorpay"
        mode_of_payment = "Razorpay"
        reference_no = request_data.get("razorpay_payment_id") or request_data.get("razorpay_order_id")
    elif service == "Easebuzz":
        bank_account_name = "Easebuzz"
        mode_of_payment = "Easebuzz"
        reference_no = request_data.get("easepayid") or request_data.get("txnid")
    else:
        bank_account_name = "CCAvenue"
        mode_of_payment = "CCAvenue"
        reference_no = request_data.get("tracking_id")
    if merchant_name and merchant_dict:
        if merchant_dict.get("company") is not None and merchant_dict.get("company") != "":
            company = merchant_dict.get("company")
        if merchant_dict.get("bank_account") is not None and merchant_dict.get("bank_account") != "":
            bank_account_name = merchant_dict.get("bank_account")
        if merchant_dict.get("debtors_account") is not None and merchant_dict.get("debtors_account") != "":
            debtors_account_name = merchant_dict.get("debtors_account")
        remarks = remarks + f" | Merchant: {merchant_name}"
    default_currency = frappe.db.get_value("Company", company, "default_currency")
    company_abbr = frappe.db.get_value("Company", company, "abbr")

    source_exchange_rate = 1

    debtors_account = f"{debtors_account_name} - {company_abbr}"
    bank_account = f"{bank_account_name} - {company_abbr}"

    try:
        payment_entry = frappe.get_doc({
            "doctype": "Payment Entry",
            "payment_type": "Receive",
            "mode_of_payment": mode_of_payment,
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
            "reference_no": reference_no,
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
        customer = frappe.get_doc("Customer", customer_id)
        company = customer.get("custom_hostel_name")
        total_money_to_pay = round(total_amount, 2)

        # Resolve gateway and optional merchant for this company
        from payments.payments.doctype.payment_gateway_config.payment_gateway_config import (
            get_gateway_for_company,
        )
        gateway, config_merchant = get_gateway_for_company(company)

        # Explicit item-level merchant takes precedence over config
        resolved_merchant = merchant_name or config_merchant

        # Resolve controller doctype name → settings doctype
        gateway_settings_doctype_map = {
            "CCAvenue": "CCAvenue Settings",
            "Easebuzz": "Easebuzz Settings",
            "Razorpay": "Razorpay Settings",
        }
        settings_doctype = gateway_settings_doctype_map.get(gateway, "CCAvenue Settings")
        controller = frappe.get_doc(settings_doctype)

        payment_details = {
            "amount": total_money_to_pay,
            "currency": "INR",
            "description": remarks,
            "payer_name": customer.name,
            "payer_email": frappe.session.user,
            "payment_gateway": gateway,
            "reference_docname": customer.name,
            "reference_doctype": "Customer",
            "company": company,
        }

        if resolved_merchant:
            payment_details["custom_merchant_name"] = resolved_merchant

        payment_url = controller.get_payment_url(**payment_details)

        if not payment_url:
            frappe.response['success'] = False
            frappe.response['message'] = f"Failed to create {gateway} payment URL."
            frappe.throw(_(f"Failed to create {gateway} payment URL."))

        frappe.response['success'] = True
        frappe.response['message'] = "Order created successfully."
        frappe.response['payment_url'] = payment_url
        frappe.response['gateway'] = gateway

    except Exception as e:
        frappe.log_error(f"Payment Order Creation Error ({gateway if 'gateway' in dir() else 'unknown'})", str(e))
        frappe.response['success'] = False
        frappe.response['message'] = f"An error occurred while creating the payment order: {str(e)}"