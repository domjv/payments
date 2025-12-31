# Copyright (c) 2025, Frappe Technologies and contributors
# For license information, please see license.txt

import json
import frappe
from frappe import _
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice


class CustomSalesInvoice(SalesInvoice):
	"""
	Custom Sales Invoice class to handle CCAvenue payment authorization.
	This creates Payment Entry automatically when payment is successful.
	"""
	
	def on_payment_authorized(self, payment_status):
		"""
		Called by CCAvenue payment gateway when payment is completed.
		
		Args:
			payment_status (str): Payment status from gateway (typically "Completed")
		"""
		frappe.log_error(
			f"CCAvenue Payment Authorization received for Sales Invoice {self.name} with status {payment_status}",
			"CCAvenue Payment Authorization"
		)
		if payment_status == "Completed":
			# Get the integration request to fetch payment details
			integration_request = self.get_integration_request()
			
			if not integration_request:
				frappe.log_error(
					f"Integration Request not found for Sales Invoice {self.name}",
					"CCAvenue Payment Entry Creation Error"
				)
				return
			
			# Create payment entry
			try:
				payment_entry = self.create_payment_entry_from_ccavenue(integration_request)
				
				if payment_entry:
					frappe.msgprint(
						_("Payment Entry {0} created successfully for {1}").format(
							frappe.bold(payment_entry.name),
							frappe.bold(self.name)
						),
						indicator="green",
						alert=True
					)
					
					# Return custom redirect URL if needed
					# return f"/app/payment-entry/{payment_entry.name}"
					
			except Exception as e:
				frappe.log_error(
					f"Failed to create Payment Entry for Sales Invoice {self.name}: {str(e)}\n{frappe.get_traceback()}",
					"CCAvenue Payment Entry Creation Error"
				)
	
	def get_integration_request(self):
		"""Get the most recent Integration Request for this Sales Invoice"""
		integration_requests = frappe.get_all(
			"Integration Request",
			filters={
				"reference_doctype": "Sales Invoice",
				"reference_docname": self.name,
				"status": "Completed"
			},
			fields=["name", "data"],
			order_by="creation desc",
			limit=1
		)
		
		if integration_requests:
			return frappe.get_doc("Integration Request", integration_requests[0].name)
		
		return None
	
	def create_payment_entry_from_ccavenue(self, integration_request):
		"""
		Create Payment Entry from CCAvenue Integration Request.
		
		Args:
			integration_request: Integration Request document
			
		Returns:
			Payment Entry document if created, None otherwise
		"""
		frappe.log_error(
			f"Creating Payment Entry for Sales Invoice {self.name} from Integration Request {integration_request.name}",
			"CCAvenue Payment Entry Creation"
		)
		# Parse integration request data
		data = json.loads(integration_request.data) if integration_request.data else {}
		
		# Get tracking ID and other payment details
		tracking_id = data.get("tracking_id", "")
		payment_mode_name = "CCAvenue"
		bank_ref_no = data.get("bank_ref_no", "")
		
		# # Validate and get mode of payment
		# if not frappe.db.exists("Mode of Payment", payment_mode_name):
		# 	# Try common alternatives
		# 	alternatives = ["CCAvenue", "Online Payment", "Online", "Bank Transfer"]
		# 	payment_mode_name = None
		# 	for alt in alternatives:
		# 		if frappe.db.exists("Mode of Payment", alt):
		# 			payment_mode_name = alt
		# 			break
			
		# 	# If still not found, create a default CCAvenue mode
		# 	if not payment_mode_name:
		# 		if not frappe.db.exists("Mode of Payment", "CCAvenue"):
		# 			mode_of_payment = frappe.get_doc({
		# 				"doctype": "Mode of Payment",
		# 				"mode_of_payment": "CCAvenue",
		# 				"type": "Bank"
		# 			})
		# 			mode_of_payment.insert(ignore_permissions=True)
		# 		payment_mode_name = "CCAvenue"
		
		# Get merchant details from integration request
		merchant_name = data.get("custom_merchant_name")
		merchant_doc = None
		
		# Try to get merchant configuration
		if merchant_name:
			try:
				merchant_doc = frappe.get_doc("CCAvenue Merchant", merchant_name)
			except:
				pass
		
		# If no explicit merchant, get based on company
		if not merchant_doc:
			ccavenue_settings = frappe.get_doc("CCAvenue Settings")
			merchant_doc = ccavenue_settings.get_merchant_for_company(company=self.company)
		
		# Determine accounts
		company_abbr = frappe.db.get_value("Company", self.company, "abbr")
		
		# Get debtors account (paid_from)
		if merchant_doc and merchant_doc.get("debtors_account"):
			paid_from = f"{merchant_doc.debtors_account} - {company_abbr}"
		else:
			paid_from = self.debit_to
		
		# Get bank account (paid_to)
		if merchant_doc and merchant_doc.get("bank_account"):
			paid_to = f"{merchant_doc.bank_account} - {company_abbr}"
		else:
			# Default CCAvenue account
			paid_to = f"CCAvenue - {company_abbr}"
			
			# Check if account exists, if not use default bank account
			if not frappe.db.exists("Account", paid_to):
				# Get default bank account
				bank_account = frappe.get_all(
					"Account",
					filters={
						"company": self.company,
						"account_type": "Bank",
						"is_group": 0
					},
					limit=1
				)
				if bank_account:
					paid_to = bank_account[0].name
				else:
					frappe.throw(_("No bank account found for company {0}").format(self.company))
		
		# Calculate payment amount (should match the amount paid including charges)
		payment_amount = data.get("amount", self.outstanding_amount)
		
		# Create Payment Entry
		payment_entry = frappe.get_doc({
			"doctype": "Payment Entry",
			"payment_type": "Receive",
			"posting_date": frappe.utils.nowdate(),
			"mode_of_payment": payment_mode_name,
			"party_type": "Customer",
			"party": self.customer,
			"company": self.company,
			"paid_from": paid_from,
			"paid_to": paid_to,
			"paid_from_account_currency": self.currency,
			"paid_to_account_currency": frappe.db.get_value("Company", self.company, "default_currency"),
			"paid_amount": payment_amount,
			"received_amount": payment_amount,
			"reference_no": tracking_id or integration_request.name,
			"reference_date": frappe.utils.nowdate(),
			"remarks": f"Payment received via CCAvenue for {self.name}. Tracking ID: {tracking_id}. Bank Ref: {bank_ref_no}",
			"references": [
				{
					"reference_doctype": "Sales Invoice",
					"reference_name": self.name,
					"total_amount": self.grand_total,
					"outstanding_amount": self.outstanding_amount,
					"allocated_amount": min(payment_amount, self.outstanding_amount)
				}
			]
		})
		
		# Insert and submit payment entry
		payment_entry.insert(ignore_permissions=True)
		payment_entry.submit()
		
		# Reload sales invoice to update outstanding amount
		self.reload()
		
		return payment_entry


def handle_payment_authorization_sales_invoice(doc, method, payment_status):
	"""
	Doc event handler for Sales Invoice on_payment_authorized.
	Called via doc_events hook in hooks.py.
	
	Args:
		doc: Sales Invoice document
		method: Method name (on_payment_authorized)
		payment_status: Payment status from gateway
	"""
	frappe.log_error(
		f"Doc event handler called for Sales Invoice {doc.name} with status {payment_status}",
		"CCAvenue Payment Authorization - Doc Event"
	)
	
	if payment_status == "Completed":
		# Get the integration request to fetch payment details
		integration_requests = frappe.get_all(
			"Integration Request",
			filters={
				"reference_doctype": "Sales Invoice",
				"reference_docname": doc.name,
				"status": "Completed"
			},
			fields=["name", "data"],
			order_by="creation desc",
			limit=1
		)
		
		if not integration_requests:
			frappe.log_error(
				f"Integration Request not found for Sales Invoice {doc.name}",
				"CCAvenue Payment Entry Creation Error"
			)
			return
		
		integration_request = frappe.get_doc("Integration Request", integration_requests[0].name)
		
		# Create payment entry
		try:
			# Parse integration request data
			data = json.loads(integration_request.data) if integration_request.data else {}
			
			# Get tracking ID and other payment details
			tracking_id = data.get("tracking_id", "")
			payment_mode_name = data.get("payment_mode", "CCAvenue")
			bank_ref_no = data.get("bank_ref_no", "")
			
			# Get merchant details from integration request
			merchant_name = data.get("custom_merchant_name")
			merchant_doc = None
			
			# Try to get merchant configuration
			if merchant_name:
				try:
					merchant_doc = frappe.get_doc("CCAvenue Merchant", merchant_name)
				except:
					pass
			
			# If no explicit merchant, get based on company
			if not merchant_doc:
				ccavenue_settings = frappe.get_doc("CCAvenue Settings")
				merchant_doc = ccavenue_settings.get_merchant_for_company(company=doc.company)
			
			# Determine accounts
			company_abbr = frappe.db.get_value("Company", doc.company, "abbr")
			
			# Get debtors account (paid_from)
			if merchant_doc and merchant_doc.get("debtors_account"):
				paid_from = f"{merchant_doc.debtors_account} - {company_abbr}"
			else:
				paid_from = doc.debit_to
			
			# Get bank account (paid_to)
			if merchant_doc and merchant_doc.get("bank_account"):
				paid_to = f"{merchant_doc.bank_account} - {company_abbr}"
			else:
				# Default CCAvenue account
				paid_to = f"CCAvenue - {company_abbr}"
				
				# Check if account exists, if not use default bank account
				if not frappe.db.exists("Account", paid_to):
					# Get default bank account
					bank_account = frappe.get_all(
						"Account",
						filters={
							"company": doc.company,
							"account_type": "Bank",
							"is_group": 0
						},
						limit=1
					)
					if bank_account:
						paid_to = bank_account[0].name
					else:
						frappe.throw(_("No bank account found for company {0}").format(doc.company))
			
			# Calculate payment amount (should match the amount paid including charges)
			payment_amount = data.get("amount", doc.outstanding_amount)
			
			# Create Payment Entry
			payment_entry = frappe.get_doc({
				"doctype": "Payment Entry",
				"payment_type": "Receive",
				"posting_date": frappe.utils.nowdate(),
				"mode_of_payment": payment_mode_name,
				"party_type": "Customer",
				"party": doc.customer,
				"company": doc.company,
				"paid_from": paid_from,
				"paid_to": paid_to,
				"paid_from_account_currency": doc.currency,
				"paid_to_account_currency": frappe.db.get_value("Company", doc.company, "default_currency"),
				"paid_amount": payment_amount,
				"received_amount": payment_amount,
				"reference_no": tracking_id or integration_request.name,
				"reference_date": frappe.utils.nowdate(),
				"remarks": f"Payment received via CCAvenue for {doc.name}. Tracking ID: {tracking_id}. Bank Ref: {bank_ref_no}",
				"references": [
					{
						"reference_doctype": "Sales Invoice",
						"reference_name": doc.name,
						"total_amount": doc.grand_total,
						"outstanding_amount": doc.outstanding_amount,
						"allocated_amount": min(payment_amount, doc.outstanding_amount)
					}
				]
			})
			
			# Insert and submit payment entry
			payment_entry.insert(ignore_permissions=True)
			payment_entry.submit()
			
			frappe.log_error(
				f"Payment Entry {payment_entry.name} created successfully for Sales Invoice {doc.name}",
				"CCAvenue Payment Entry Created"
			)
			
			# Reload sales invoice to update outstanding amount
			doc.reload()
			
		except Exception as e:
			frappe.log_error(
				f"Failed to create Payment Entry for Sales Invoice {doc.name}: {str(e)}\n{frappe.get_traceback()}",
				"CCAvenue Payment Entry Creation Error"
			)


def get_sales_invoice_for_payment(sales_invoice_name):
	"""
	Helper function to get Sales Invoice details for payment initiation.
	Can be called from frontend to prepare payment data.
	
	Args:
		sales_invoice_name (str): Sales Invoice name
		
	Returns:
		dict: Payment details ready for initiate_payment API
	"""
	if not frappe.has_permission("Sales Invoice", "read", sales_invoice_name):
		frappe.throw(_("Not permitted to access Sales Invoice {0}").format(sales_invoice_name))
	
	doc = frappe.get_doc("Sales Invoice", sales_invoice_name)
	
	if doc.outstanding_amount <= 0:
		frappe.throw(_("Sales Invoice {0} has no outstanding amount").format(sales_invoice_name))
	
	return {
		"amount": doc.outstanding_amount,
		"currency": doc.currency,
		"reference_doctype": "Sales Invoice",
		"reference_docname": doc.name,
		"company": doc.company,
		"payer_email": doc.contact_email or frappe.session.user,
		"payer_name": doc.customer,
		"description": f"Payment for Invoice {doc.name}",
		"custom_pincode": doc.get("custom_pincode"),
		"custom_state": doc.get("custom_state")
	}


@frappe.whitelist()
def get_payment_details(sales_invoice_name):
	"""
	API endpoint to get payment details for a Sales Invoice.
	Call this from frontend before initiating payment.
	
	Args:
		sales_invoice_name (str): Sales Invoice name
		
	Returns:
		dict: Payment details
	"""
	try:
		return {
			"success": True,
			"data": get_sales_invoice_for_payment(sales_invoice_name)
		}
	except Exception as e:
		frappe.log_error(f"Error getting payment details: {str(e)}\n{frappe.get_traceback()}")
		return {
			"success": False,
			"error": str(e)
		}
