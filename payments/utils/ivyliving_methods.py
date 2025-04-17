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