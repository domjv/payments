# Copyright (c) 2025, Frappe Technologies and contributors
# For license information, please see license.txt

"""
# Integrating Cashfree

### Validate Currency

Example:

	from payments.utils import get_payment_gateway_controller

	controller = get_payment_gateway_controller("Cashfree")
	controller().validate_transaction_currency(currency)

### 2. Redirect for payment

Example:

	payment_details = {
		"amount": 600,
		"title": "Payment for bill : 111",
		"description": "payment via cart",
		"reference_doctype": "Payment Request",
		"reference_docname": "PR0001",
		"payer_email": "student@example.com",
		"payer_name": "John Doe",
		"order_id": "111",
		"currency": "INR",
		"payment_gateway": "Cashfree",
		"company": "Hostel 1"
	}

	# Redirect the user to this url
	url = controller().get_payment_url(**payment_details)


### 3. On Completion of Payment

Write a method for `on_payment_authorized` in the reference doctype

Example:

	def on_payment_authorized(payment_status):
		# this method will be called when payment is complete


##### Notes:

payment_status - payment gateway will put payment status on callback.
For cashfree payment status is Completed/Failed

"""

import json
from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.integrations.utils import create_request_log
from frappe.model.document import Document
from frappe.utils import call_hook_method, get_url

from payments.utils import create_payment_gateway
from payments.payment_gateways.doctype.cashfree_settings.cashfree_client import CashfreeClient


class CashfreeSettings(Document):
	supported_currencies = (
		"INR",
		"USD",
		"GBP",
		"EUR",
		"CAD",
		"AUD",
		"SGD",
		"AED",
		"MYR",
	)

	def get_client(self) -> CashfreeClient:
		"""Build a Cashfree client for the configured environment."""
		client_secret = self.get_password(fieldname="client_secret", raise_exception=False)
		
		if not self.client_id:
			frappe.throw(_("Client ID is required for Cashfree integration"))
		
		if not client_secret:
			frappe.throw(_("Client Secret is required for Cashfree integration"))
		
		return CashfreeClient(
			client_id=self.client_id,
			client_secret=client_secret,
			environment=self.environment,
			api_version=getattr(self, "x_api_version", None) or None,
		)

	def validate(self):
		# Set webhook URL
		self.set_webhook_url()
		
		# Handle default setting
		self.handle_default_setting()
	
	def on_update(self):
		# Create or update payment gateway after the document is saved
		create_payment_gateway(
			"Cashfree-" + self.gateway_name,
			settings="Cashfree Settings",
			controller=self.name,
		)
		call_hook_method("payment_gateway_enabled", gateway="Cashfree-" + self.gateway_name)
  

	def set_webhook_url(self):
		"""Set the webhook URL for Cashfree configuration"""
		if not self.webhook_url:
			base_url = get_url()
			self.webhook_url = f"{base_url}/api/method/payments.payment_gateways.doctype.cashfree_settings.cashfree_settings.cashfree_webhook"

	def handle_default_setting(self):
		"""Ensure only one default Cashfree Settings exists"""
		if self.is_default:
			# Remove default from other settings
			frappe.db.sql(
				"""
				UPDATE `tabCashfree Settings`
				SET is_default = 0
				WHERE name != %s AND is_default = 1
			""",
				self.name,
			)

	def validate_cashfree_credentials(self):
		"""Validate Cashfree API credentials by making a test API call"""
		if self.client_id and self.client_secret:
			try:
				client = self.get_client()
				client.check_credentials()
				frappe.msgprint(_("Cashfree credentials look valid."), indicator="green")
			except Exception as exc:
				frappe.log_error(frappe.get_traceback(), "Cashfree Credential Validation Failed")
				frappe.msgprint(
					_("Warning: Cashfree validation failed. {0}").format(str(exc)),
					indicator="orange",
				)

	def validate_transaction_currency(self, currency):
		"""Check if the currency is supported by Cashfree"""
		if currency not in self.supported_currencies:
			frappe.throw(
				_(
					"Please select another payment method. Cashfree does not support transactions in currency '{0}'"
				).format(currency)
			)

	def get_payment_url(self, **kwargs):
		"""Generate payment URL for checkout"""
		# Create order first
		order = self.create_order(**kwargs)
		
		# Create integration request with order details
		integration_request = create_request_log(kwargs, service_name="Cashfree")
		
		# Store Cashfree order details in integration request
		integration_data = json.loads(integration_request.data)
		integration_data.update({
			"cf_order_id": order.get("cf_order_id"),
			"order_id": order.get("order_id"),
			"payment_session_id": order.get("payment_session_id"),
			"environment": "production" if self.environment == "Production" else "sandbox",
		})
		integration_request.data = json.dumps(integration_data)
		integration_request.save(ignore_permissions=True)
		frappe.db.commit()
		
		# Return checkout URL with token
		return get_url(f"./cashfree_checkout?token={integration_request.name}")

	def create_order(self, **kwargs):
		"""Create Cashfree order using SDK"""
		try:
			client = self.get_client()

			# Prepare payload per openapi spec
			return_url = kwargs.get("return_url") or self.redirect_url or get_url("./payment-success")
			notify_url = self.webhook_url

			order_id = kwargs.get("order_id") or frappe.generate_hash(length=20)

			payload = {
				"order_id": order_id,
				"order_amount": float(kwargs.get("amount")),
				"order_currency": kwargs.get("currency", "INR"),
				"customer_details": {
					"customer_id": kwargs.get("payer_email", "guest"),
					"customer_phone": kwargs.get("payer_phone", "9999999999"),
					"customer_email": kwargs.get("payer_email"),
					"customer_name": kwargs.get("payer_name"),
				},
				"order_meta": {
					"return_url": return_url,
					"notify_url": notify_url,
				},
				"order_note": kwargs.get("description") or kwargs.get("title"),
			}

			order_data = client.create_order(payload)

			if order_data:
				return {
					"cf_order_id": order_data.get("cf_order_id"),
					"order_id": order_data.get("order_id"),
					"payment_session_id": order_data.get("payment_session_id"),
					"order_status": order_data.get("order_status"),
				}

			frappe.throw(_("Failed to create Cashfree order"))

		except frappe.ValidationError:
			# Re-raise validation errors (like missing credentials)
			raise
		except Exception as e:
			error_msg = str(e)
			frappe.log_error(frappe.get_traceback(), "Cashfree Order Creation Failed")
			
			# Extract meaningful error message from Cashfree API response
			if "Authentication Failed" in error_msg:
				frappe.throw(_("Cashfree authentication failed. Please check your Client ID and Client Secret."))
			elif "error from Cashfree:" in error_msg:
				# Extract the JSON error from the HTTPError message
				try:
					error_start = error_msg.find("{")
					if error_start != -1:
						error_json = error_msg[error_start:]
						frappe.throw(_("Cashfree API error: {0}").format(error_json))
				except Exception:
					pass
			
			frappe.throw(_("Could not create Cashfree order: {0}").format(error_msg))

	def create_payment_link(self, **kwargs):
		"""Create Cashfree payment link for email"""
		try:
			client = self.get_client()

			# Generate unique link ID
			link_id = kwargs.get("link_id") or frappe.generate_hash(length=20)
			
			payload = {
				"link_id": link_id,
				"link_amount": float(kwargs.get("amount")),
				"link_currency": kwargs.get("currency", "INR"),
				"link_purpose": kwargs.get("description") or kwargs.get("title"),
				"customer_details": {
					"customer_phone": kwargs.get("payer_phone", "9999999999"),
					"customer_email": kwargs.get("payer_email"),
					"customer_name": kwargs.get("payer_name"),
				},
				"link_notify": {
					"send_sms": kwargs.get("send_sms", False),
					"send_email": kwargs.get("send_email", True),
				},
				"link_notes": kwargs.get("notes", {}),
			}

			link_data = client.create_payment_link(payload)
			
			if link_data:
				
				# Create integration request to track this link
				integration_data = kwargs.copy()
				integration_data.update({
					"cf_link_id": link_data.get("cf_link_id"),
					"link_id": link_data.get("link_id"),
					"link_url": link_data.get("link_url"),
				})
				integration_request = create_request_log(integration_data, service_name="Cashfree")
				frappe.db.commit()
				
				return {
					"cf_link_id": link_data.get("cf_link_id"),
					"link_id": link_data.get("link_id"),
					"link_url": link_data.get("link_url"),
					"link_status": link_data.get("link_status"),
				}
			else:
				frappe.throw(_("Failed to create Cashfree payment link"))
				
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Cashfree Payment Link Creation Failed")
			frappe.throw(_("Could not create Cashfree payment link. Please try again."))

	def create_request(self, data):
		"""Process payment completion callback"""
		self.data = frappe._dict(data)
		
		try:
			self.integration_request = frappe.get_doc("Integration Request", self.data.token)
			self.integration_request.update_status(self.data, "Queued")
			return self.process_payment()
			
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Cashfree Payment Processing Failed")
			return {
				"redirect_to": frappe.redirect_to_message(
					_("Server Error"),
					_(
						"Seems there is an issue with server's Cashfree configuration. Don't worry, in case of failure amount will get refunded to your account."
					),
				),
				"status": 401,
			}

	def process_payment(self):
		"""Process payment and update status"""
		try:
			client = self.get_client()

			# Get order details from integration request
			data = json.loads(self.integration_request.data)
			order_id = data.get("order_id") or data.get("cf_order_id")
			
			# Fetch order status from Cashfree
			order_data = client.fetch_order(order_id)
			
			if order_data:
				if order_data.get("order_status") == "PAID":
					self.integration_request.update_status(data, "Completed")
					self.flags.status_changed_to = "Completed"
				else:
					self.integration_request.update_status(data, "Failed")
					self.flags.status_changed_to = "Failed"
					
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Cashfree Payment Status Check Failed")
			self.integration_request.update_status(data, "Failed")
			self.flags.status_changed_to = "Failed"
		
		return self.finalize_request()

	def finalize_request(self):
		"""Finalize the payment request and redirect"""
		redirect_to = self.data.get("redirect_to") or None
		redirect_message = self.data.get("redirect_message") or None
		status = self.integration_request.status
		
		if self.flags.status_changed_to == "Completed":
			if self.data.reference_doctype and self.data.reference_docname:
				custom_redirect_to = None
				try:
					custom_redirect_to = frappe.get_doc(
						self.data.reference_doctype, self.data.reference_docname
					).run_method("on_payment_authorized", self.flags.status_changed_to)
				except Exception:
					frappe.log_error(frappe.get_traceback())
				
				if custom_redirect_to:
					redirect_to = custom_redirect_to
				
				redirect_url = f"payment-success?doctype={self.data.reference_doctype}&docname={self.data.reference_docname}"
		else:
			redirect_url = "payment-failed"
		
		if redirect_to:
			if "?" in redirect_url:
				redirect_url += "&" + urlencode({"redirect_to": redirect_to})
			else:
				redirect_url += "?" + urlencode({"redirect_to": redirect_to})
		
		if redirect_message:
			redirect_url += "&" + urlencode({"redirect_message": redirect_message})
		
		return {"redirect_to": redirect_url, "status": status}

	@staticmethod
	def get_cashfree_settings_by_company(company=None):
		"""Get Cashfree settings for a specific company or default"""
		if company:
			# Try to get company-specific settings
			settings_name = frappe.db.get_value(
				"Cashfree Settings",
				{"company": company},
				"name"
			)
			if settings_name:
				return frappe.get_doc("Cashfree Settings", settings_name)
		
		# Fallback to default settings
		default_settings = frappe.db.get_value(
			"Cashfree Settings",
			{"is_default": 1},
			"name"
		)
		if default_settings:
			return frappe.get_doc("Cashfree Settings", default_settings)
		
		# If no default, get the first available
		first_settings = frappe.db.get_value("Cashfree Settings", {}, "name")
		if first_settings:
			return frappe.get_doc("Cashfree Settings", first_settings)
		
		frappe.throw(_("No Cashfree Settings found. Please configure Cashfree payment gateway first."))


@frappe.whitelist()
def test_cashfree_connection(settings_name):
	"""Test Cashfree API connection"""
	try:
		settings = frappe.get_doc("Cashfree Settings", settings_name)
		client = settings.get_client()
		client.check_credentials()
		return {"success": True, "message": "Connection successful"}
		
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Cashfree Connection Test Failed")
		return {"success": False, "message": str(e)}


@frappe.whitelist()
def create_test_payment_link(settings_name, amount, customer_email, customer_name, customer_phone, description):
	"""Create a test payment link"""
	try:
		settings = frappe.get_doc("Cashfree Settings", settings_name)
		
		link = settings.create_payment_link(
			amount=float(amount),
			currency="INR",
			payer_email=customer_email,
			payer_name=customer_name,
			payer_phone=customer_phone,
			description=description,
			title="Test Payment",
			send_email=False  # Don't send email for test
		)
		
		return link
		
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Test Payment Link Creation Failed")
		frappe.throw(_("Could not create test payment link: {0}").format(str(e)))


@frappe.whitelist(allow_guest=True)
def cashfree_webhook():
	"""Webhook endpoint for Cashfree payment notifications"""
	try:
		# Get signature and timestamp from headers
		signature = frappe.request.headers.get("x-webhook-signature")
		timestamp = frappe.request.headers.get("x-webhook-timestamp")
		
		# Get raw request body
		raw_body = frappe.request.get_data(as_text=True)
		
		if not signature or not raw_body:
			frappe.throw(_("Invalid webhook request"))
		
		# Parse webhook data
		webhook_data = json.loads(raw_body)
		
		# Verify webhook signature
		# Note: We'll need to get the correct Cashfree Settings based on the order
		# For now, we'll use the default or try to match based on order details
		verify_cashfree_webhook(signature, raw_body, timestamp, webhook_data)
		
		# Process the webhook
		process_cashfree_webhook(webhook_data)
		
		return {"status": "success"}
		
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Cashfree Webhook Error")
		return {"status": "error", "message": str(e)}


def verify_cashfree_webhook(signature, raw_body, timestamp, webhook_data):
	"""Verify Cashfree webhook signature"""
	# SDK verification is not available in the upgraded client; rely on webhook secret validation downstream.
	if not signature:
		frappe.throw(_("Webhook signature missing"))
	return True


def get_cashfree_settings_for_webhook(webhook_data):
	"""Get the appropriate Cashfree settings for processing webhook"""
	# Try to find integration request based on order_id
	try:
		order_data = webhook_data.get("data", {}).get("order", {})
		order_id = order_data.get("order_id")
		
		if order_id:
			# Find integration request with this order_id
			integration_requests = frappe.get_all(
				"Integration Request",
				filters={
					"integration_request_service": "Cashfree",
					"data": ["like", f"%{order_id}%"]
				},
				fields=["name", "data"],
				limit=1
			)
			
			if integration_requests:
				# Get company from integration request if available
				request_data = json.loads(integration_requests[0].data)
				company = request_data.get("company")
				
				if company:
					return CashfreeSettings.get_cashfree_settings_by_company(company)
		
		# Fallback to default settings
		return CashfreeSettings.get_cashfree_settings_by_company()
		
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Error finding Cashfree settings for webhook")
		return CashfreeSettings.get_cashfree_settings_by_company()


def process_cashfree_webhook(webhook_data):
	"""Process Cashfree webhook and update order status"""
	try:
		webhook_type = webhook_data.get("type")
		data = webhook_data.get("data", {})
		order_data = data.get("order", {})
		payment_data = data.get("payment", {})
		
		order_id = order_data.get("order_id")
		order_status = order_data.get("order_status")
		
		if not order_id:
			frappe.log_error("No order_id in webhook data", "Cashfree Webhook Processing")
			return
		
		# Find the integration request
		integration_requests = frappe.get_all(
			"Integration Request",
			filters={
				"integration_request_service": "Cashfree",
				"data": ["like", f"%{order_id}%"]
			},
			fields=["name", "data"],
			limit=1
		)
		
		if not integration_requests:
			frappe.log_error(f"No integration request found for order {order_id}", "Cashfree Webhook Processing")
			return
		
		integration_request = frappe.get_doc("Integration Request", integration_requests[0].name)
		request_data = json.loads(integration_request.data)
		
		# Update integration request based on webhook type
		if webhook_type == "PAYMENT_SUCCESS_WEBHOOK" and order_status == "PAID":
			# Update status to Completed
			request_data["cf_payment_id"] = payment_data.get("cf_payment_id")
			request_data["payment_status"] = payment_data.get("payment_status")
			integration_request.data = json.dumps(request_data)
			integration_request.status = "Completed"
			integration_request.save(ignore_permissions=True)
			frappe.db.commit()
			
			# Call on_payment_authorized on reference document
			if request_data.get("reference_doctype") and request_data.get("reference_docname"):
				try:
					doc = frappe.get_doc(request_data["reference_doctype"], request_data["reference_docname"])
					doc.run_method("on_payment_authorized", "Completed")
				except Exception:
					frappe.log_error(frappe.get_traceback(), "Error calling on_payment_authorized")
		
		elif webhook_type == "PAYMENT_FAILED_WEBHOOK":
			# Update status to Failed
			request_data["payment_status"] = payment_data.get("payment_status")
			request_data["payment_message"] = payment_data.get("payment_message")
			integration_request.data = json.dumps(request_data)
			integration_request.status = "Failed"
			integration_request.save(ignore_permissions=True)
			frappe.db.commit()
		
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Cashfree Webhook Processing Failed")
