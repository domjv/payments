# Copyright (c) 2015, Frappe Technologies and contributors
# License: MIT. See LICENSE

"""
# Integrating Razorpay (Multi-Merchant)

### 1. Validate Currency

    from payments.utils import get_payment_gateway_controller

    controller = get_payment_gateway_controller("Razorpay")
    controller.validate_transaction_currency(currency)

### 2. Standard ERPNext redirect checkout

    payment_details = {
        "amount": 600,
        "title": "Payment for bill : 111",
        "description": "payment via cart",
        "reference_doctype": "Payment Request",
        "reference_docname": "PR0001",
        "payer_email": "customer@example.com",
        "payer_name": "Customer Name",
        "currency": "INR",
        "payment_gateway": "Razorpay",
        "company": "Hostel A",            # optional – drives merchant selection
        "custom_merchant_name": "HsA-RP",  # optional – explicit merchant override
    }

    url = controller.get_payment_url(**payment_details)

### 3. External-frontend API flow

    POST /api/method/payments.payment_gateways.doctype.razorpay_settings.razorpay_settings.initiate_payment
    POST /api/method/payments.payment_gateways.doctype.razorpay_settings.razorpay_settings.verify_payment
    GET  /api/method/payments.payment_gateways.doctype.razorpay_settings.razorpay_settings.check_payment_status
    POST /api/method/payments.payment_gateways.doctype.razorpay_settings.razorpay_settings.payment_captured  # webhook fallback

### 4. On Completion of Payment

    def on_payment_authorized(payment_status):
        # called with "Completed" on success
        pass

##### Notes:

- Per-hostel/company credentials live in **Razorpay Merchant** records.
- Global fallback credentials are stored in **Razorpay Settings** (Single).
- The merchant is resolved by: explicit merchant_name → company match → is_default.
- Subscriptions are still fully supported (setup_subscription, addons, cancel_subscription).
"""

import hashlib
import hmac
import json
import math
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse

import frappe
import razorpay
from frappe import _
from frappe.integrations.utils import (
	create_request_log,
	make_get_request,
	make_post_request,
)
from frappe.model.document import Document
from frappe.utils import add_to_date, call_hook_method, cint, get_datetime, get_timestamp, get_url, now_datetime

from payments.utils import create_payment_gateway

# Grace period before the payment.captured webhook fallback processes a stuck IR.
# Gives the preferred frontend callback (verify_payment) time to complete first.
WEBHOOK_CAPTURE_GRACE_MINUTES = 3


class RazorpaySettings(Document):
	supported_currencies = (
		"AED", "ALL", "AMD", "ARS", "AUD", "AWG", "AZN", "BAM", "BBD", "BDT",
		"BGN", "BHD", "BIF", "BMD", "BND", "BOB", "BRL", "BSD", "BTN", "BWP",
		"BZD", "CAD", "CHF", "CLP", "CNY", "COP", "CRC", "CUP", "CVE", "CZK",
		"DJF", "DKK", "DOP", "DZD", "EGP", "ETB", "EUR", "FJD", "GBP", "GHS",
		"GIP", "GMD", "GNF", "GTQ", "GYD", "HKD", "HNL", "HRK", "HTG", "HUF",
		"IDR", "ILS", "INR", "IQD", "ISK", "JMD", "JOD", "JPY", "KES", "KGS",
		"KHR", "KMF", "KRW", "KWD", "KYD", "KZT", "LAK", "LKR", "LRD", "LSL",
		"MAD", "MDL", "MGA", "MKD", "MMK", "MNT", "MOP", "MUR", "MVR", "MWK",
		"MXN", "MYR", "MZN", "NAD", "NGN", "NIO", "NOK", "NPR", "NZD", "OMR",
		"PEN", "PGK", "PHP", "PKR", "PLN", "PYG", "QAR", "RON", "RSD", "RUB",
		"RWF", "SAR", "SCR", "SEK", "SGD", "SLL", "SOS", "SSP", "SVC", "SZL",
		"THB", "TND", "TRY", "TTD", "TWD", "TZS", "UAH", "UGX", "USD", "UYU",
		"UZS", "VND", "VUV", "XAF", "XCD", "XOF", "XPF", "YER", "ZAR", "ZMW",
	)

	# ------------------------------------------------------------------
	# Merchant resolution
	# ------------------------------------------------------------------

	def get_merchant_for_company(self, company=None, merchant_name=None):
		"""
		Resolve the Razorpay Merchant to use for a payment.

		Priority:
		  1. Explicit ``merchant_name`` argument
		  2. Company-specific merchant (``company`` field on merchant)
		  3. Default merchant (``is_default = 1``)
		  4. Raises an error – no implicit fall-through to global Settings creds
		     (use ``get_settings()`` if you want the global-fallback path).

		Returns:
		    frappe.Document: RazorpayMerchant document
		"""
		if merchant_name:
			try:
				return frappe.get_doc("Razorpay Merchant", merchant_name)
			except frappe.DoesNotExistError:
				frappe.log_error(
					f"Razorpay Merchant '{merchant_name}' not found, falling back to company/default",
					"Razorpay Merchant Resolution",
				)

		if company:
			name = frappe.db.get_value("Razorpay Merchant", {"company": company}, "name")
			if name:
				return frappe.get_doc("Razorpay Merchant", name)

		default_name = frappe.db.get_value("Razorpay Merchant", {"is_default": 1}, "name")
		if default_name:
			return frappe.get_doc("Razorpay Merchant", default_name)

		frappe.throw(
			_(
				"No Razorpay Merchant configuration found. "
				"Please create a Razorpay Merchant record and mark one as the default."
			)
		)

	def get_credentials(self, data=None, company=None, merchant_name=None):
		"""
		Return a ``frappe._dict`` with ``api_key``, ``api_secret``, ``environment``
		and ``redirect_to`` for the resolved merchant.

		Falls back to global Razorpay Settings if no merchant records exist.
		Sandbox override via site config is still honoured.
		"""
		data = data or {}

		# Sandbox override via site config (legacy path – keeps subscriptions working)
		if cint(data.get("notes", {}).get("use_sandbox")) or data.get("use_sandbox"):
			return frappe._dict(
				{
					"api_key": frappe.conf.sandbox_api_key,
					"api_secret": frappe.conf.sandbox_api_secret,
					"environment": "Test",
					"redirect_to": self.redirect_to or "",
				}
			)

		# Prefer merchant record
		merchant_doc = None
		try:
			merchant_doc = self.get_merchant_for_company(
				company=company or data.get("company"),
				merchant_name=merchant_name or data.get("custom_merchant_name"),
			)
		except frappe.ValidationError:
			pass  # No merchants configured – fall back to global Settings

		if merchant_doc:
			return frappe._dict(
				{
					"api_key": merchant_doc.api_key,
					"api_secret": merchant_doc.get_password(fieldname="api_secret", raise_exception=False),
					"environment": merchant_doc.environment or "Test",
					"redirect_to": merchant_doc.redirect_to or self.redirect_to or "",
					"merchant_name": merchant_doc.name,
				}
			)

		# Global fallback
		return frappe._dict(
			{
				"api_key": self.api_key,
				"api_secret": self.get_password(fieldname="api_secret", raise_exception=False),
				"environment": self.environment or "Test",
				"redirect_to": self.redirect_to or "",
				"merchant_name": None,
			}
		)

	def get_razorpay_client(self, creds):
		"""Return a ``razorpay.Client`` initialised with the given credentials dict."""
		return razorpay.Client(auth=(creds.api_key, creds.api_secret))

	# ------------------------------------------------------------------
	# Lifecycle
	# ------------------------------------------------------------------

	def validate(self):
		create_payment_gateway("Razorpay")
		call_hook_method("payment_gateway_enabled", gateway="Razorpay")
		if not self.flags.ignore_mandatory:
			self.validate_razorpay_credentials()

	def validate_razorpay_credentials(self):
		if self.api_key and self.api_secret:
			try:
				make_get_request(
					url="https://api.razorpay.com/v1/payments",
					auth=(
						self.api_key,
						self.get_password(fieldname="api_secret", raise_exception=False),
					),
				)
			except Exception:
				frappe.throw(_("Razorpay: API Key or API Secret appears to be incorrect."))

	def validate_transaction_currency(self, currency):
		if currency not in self.supported_currencies:
			frappe.throw(
				_(
					"Please select another payment method. "
					"Razorpay does not support transactions in currency '{0}'"
				).format(currency)
			)

	# ------------------------------------------------------------------
	# Payment URL (standard ERPNext path)
	# ------------------------------------------------------------------

	def get_payment_url(self, **kwargs):
		if not kwargs.get("order_id"):
			order = self.create_order(**kwargs)
			kwargs.update({"order_id": order.get("id")})

		integration_request = create_request_log(kwargs, service_name="Razorpay")
		return get_url(f"./razorpay_checkout?token={integration_request.name}")

	# ------------------------------------------------------------------
	# Order creation
	# ------------------------------------------------------------------

	def create_order(self, **kwargs):
		"""
		Create a Razorpay order and return the order dict.

		Adds Payment Charge surcharges before sending the amount to Razorpay,
		and embeds ``reference_doctype``, ``reference_docname``, ``token`` and
		``user`` in the order ``notes`` so the callback can look up the
		Integration Request without relying on cookie session state.
		"""
		company = kwargs.get("company")
		merchant_name = kwargs.get("custom_merchant_name")
		creds = self.get_credentials(data=kwargs, company=company, merchant_name=merchant_name)

		# Apply Payment Charge surcharges
		base_amount = float(kwargs.get("amount", 0))
		charge_list = frappe.get_all("Payment Charge", filters={"disabled": 0}, fields=["*"])
		total_charges = sum(
			math.ceil(base_amount * c.charge_percent / 100 * 100) / 100 for c in charge_list
		)
		final_amount = base_amount + total_charges

		# Store final amount (post-charges) in kwargs so Integration Request records it
		kwargs["amount"] = final_amount

		# Create integration log before the API call
		integration_request = create_request_log(kwargs, service_name="Razorpay")

		# Amount in paise (Razorpay expects integers)
		amount_paise = int(final_amount * 100)

		payment_options = {
			"amount": amount_paise,
			"currency": kwargs.get("currency", "INR"),
			"receipt": kwargs.get("receipt") or integration_request.name,
			# auto-capture avoids the scheduler-based capture flow
			"payment_capture": 1,
			"notes": {
				"reference_doctype": kwargs.get("reference_doctype", ""),
				"reference_docname": kwargs.get("reference_docname", ""),
				"token": integration_request.name,
				"user": frappe.session.user or "Guest",
				"merchant_name": creds.get("merchant_name") or "",
				"company": company or "",
			},
		}

		if creds.api_key and creds.api_secret:
			try:
				order = make_post_request(
					"https://api.razorpay.com/v1/orders",
					auth=(creds.api_key, creds.api_secret),
					json=payment_options,
				)
				# Persist order id / receipt on the IR so the payment.captured
				# webhook can locate a still-Queued request without an API call.
				try:
					ir_data = json.loads(integration_request.data) if integration_request.data else {}
					ir_data["razorpay_order_id"] = order.get("id")
					ir_data["receipt"] = payment_options.get("receipt")
					ir_data["order_id"] = order.get("id")
					integration_request.db_set("data", json.dumps(ir_data))
				except Exception:
					frappe.log_error(
						frappe.get_traceback(),
						"Razorpay create_order: failed to persist order_id on IR",
					)
				order["integration_request"] = integration_request.name
				return order
			except Exception:
				frappe.log_error(frappe.get_traceback(), "Razorpay create_order failed")
				frappe.throw(_("Could not create Razorpay order. Please try again."))
		else:
			frappe.throw(_("Razorpay credentials are not configured."))

	# ------------------------------------------------------------------
	# Request / authorization
	# ------------------------------------------------------------------

	def create_request(self, data):
		self.data = frappe._dict(data)
		try:
			self.integration_request = frappe.get_doc("Integration Request", self.data.token)
			self.integration_request.update_status(self.data, "Queued")
			return self.authorize_payment()
		except Exception:
			frappe.log_error(frappe.get_traceback())
			return {
				"redirect_to": frappe.redirect_to_message(
					_("Server Error"),
					_(
						"There was an issue processing your payment. "
						"In case of failure, any amount deducted will be refunded to your account."
					),
				),
				"status": 401,
			}

	def authorize_payment(self):
		"""
		Verify the payment via Razorpay REST API and mark the Integration
		Request as Completed (auto-capture) or Authorized (manual capture).
		Then call on_payment_authorized on the reference document.
		"""
		data = json.loads(self.integration_request.data)
		company = data.get("company")
		merchant_name = data.get("custom_merchant_name") or (
			data.get("notes", {}).get("merchant_name") if isinstance(data.get("notes"), dict) else None
		)
		creds = self.get_credentials(data=data, company=company, merchant_name=merchant_name)

		try:
			resp = make_get_request(
				f"https://api.razorpay.com/v1/payments/{self.data.razorpay_payment_id}",
				auth=(creds.api_key, creds.api_secret),
			)

			if resp.get("status") == "captured":
				self.integration_request.update_status(data, "Completed")
				self.flags.status_changed_to = "Completed"
			elif resp.get("status") == "authorized":
				self.integration_request.update_status(data, "Authorized")
				self.flags.status_changed_to = "Authorized"
			elif data.get("subscription_id") and resp.get("status") == "refunded":
				# Future-dated subscription: Razorpay refunds the auth amount
				self.integration_request.update_status(data, "Completed")
				self.flags.status_changed_to = "Verified"
			else:
				frappe.log_error(
					message=str(resp), title="Razorpay Payment not authorized"
				)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Razorpay authorize_payment error")

		status = frappe.flags.integration_request.status_code
		redirect_to = creds.get("redirect_to") or data.get("redirect_to") or None
		redirect_message = data.get("redirect_message") or None

		if self.flags.status_changed_to in ("Authorized", "Verified", "Completed"):
			# If a payment.captured webhook already stashed a pending flag, clear it
			# so the grace-period scheduler does not re-process this IR.
			try:
				fresh_data = json.loads(self.integration_request.data) if self.integration_request.data else {}
				if fresh_data.get("webhook_capture_pending"):
					fresh_data["webhook_capture_pending"] = 0
					fresh_data["webhook_skipped_reason"] = "callback_completed"
					self.integration_request.db_set("data", json.dumps(fresh_data))
			except Exception:
				pass

			custom_redirect_to = self.run_payment_success_handlers(
				self.integration_request,
				data,
				self.flags.status_changed_to,
				source="callback",
			)
			if custom_redirect_to and not redirect_to:
				redirect_to = custom_redirect_to

			# Build redirect URL
			if redirect_to:
				parsed = urlparse(redirect_to)
				params = parse_qs(parsed.query)
				params["integration_id"] = [self.integration_request.name]
				new_query = urlencode({k: v[0] for k, v in params.items()})
				redirect_url = urlunparse(
					(parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment)
				)
			else:
				redirect_url = (
					f"payment-success"
					f"?doctype={self.data.reference_doctype}"
					f"&docname={self.data.reference_docname}"
				)
		else:
			if redirect_to:
				parsed = urlparse(redirect_to)
				params = parse_qs(parsed.query)
				params["integration_id"] = [self.integration_request.name]
				new_query = urlencode({k: v[0] for k, v in params.items()})
				redirect_url = urlunparse(
					(parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment)
				)
			else:
				redirect_url = "payment-failed"

		if redirect_message and not redirect_to:
			sep = "&" if "?" in redirect_url else "?"
			redirect_url += sep + urlencode({"redirect_message": redirect_message})

		return {"redirect_to": redirect_url, "status": status}

	def run_payment_success_handlers(self, integration_request, data, status, source="callback"):
		"""
		Add audit comments and dispatch to Sales Invoice / Payment Request /
		Customer payment-authorization handlers.

		``source`` is ``"callback"`` (preferred frontend verify_payment path) or
		``"webhook"`` (payment.captured fallback). When ``source == "webhook"`` an
		extra comment is added noting webhook completion.
		"""
		data = data or {}
		reference_doctype = (
			getattr(self.data, "reference_doctype", None)
			or data.get("reference_doctype")
			or integration_request.reference_doctype
		)
		reference_docname = (
			getattr(self.data, "reference_docname", None)
			or data.get("reference_docname")
			or integration_request.reference_docname
		)
		payment_id = (
			getattr(self.data, "razorpay_payment_id", None)
			or data.get("razorpay_payment_id")
			or "N/A"
		)
		order_id = (
			getattr(self.data, "razorpay_order_id", None)
			or data.get("razorpay_order_id")
			or data.get("order_id")
			or "N/A"
		)
		upi_rrn = data.get("upi_rrn") or ""

		custom_redirect_to = None
		if not reference_doctype or not reference_docname:
			return custom_redirect_to

		try:
			doc = frappe.get_doc(reference_doctype, reference_docname)

			comment_text = (
				f"<b>Razorpay Payment Processed</b><br>"
				f"Status: {status}<br>"
				f"Payment ID: {payment_id}<br>"
				f"Order ID: {order_id}<br>"
				f"Integration Request: {integration_request.name}"
			)
			if upi_rrn:
				comment_text += f"<br>UPI RRN: {upi_rrn}"
			try:
				doc.add_comment("Info", comment_text)
			except Exception:
				pass

			if source == "webhook":
				webhook_comment = (
					f"<b>Payment completed by Razorpay webhook</b><br>"
					f"Event: payment.captured<br>"
					f"Payment ID: {payment_id}<br>"
					f"Order ID: {order_id}<br>"
					f"Integration Request: {integration_request.name}"
				)
				if upi_rrn:
					webhook_comment += f"<br>UPI RRN: {upi_rrn}"
				try:
					doc.add_comment("Info", webhook_comment)
				except Exception:
					pass
				frappe.flags.razorpay_webhook_completion = True

			if reference_doctype == "Sales Invoice":
				from payments.overrides.sales_invoice import handle_payment_authorization_sales_invoice
				custom_redirect_to = handle_payment_authorization_sales_invoice(
					doc, "on_payment_authorized", status
				)
			elif reference_doctype == "Payment Request":
				from payments.utils.ivyliving_methods import handle_payment_authorization_payment_request
				custom_redirect_to = handle_payment_authorization_payment_request(
					doc, "on_payment_authorized", status
				)
			elif reference_doctype == "Customer":
				from payments.utils.ivyliving_methods import handle_payment_authorization_customer
				custom_redirect_to = handle_payment_authorization_customer(
					doc, "on_payment_authorized", status
				)
			else:
				if hasattr(doc, "on_payment_authorized"):
					custom_redirect_to = doc.run_method("on_payment_authorized", status)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(), "Razorpay on_payment_authorized error"
			)
		finally:
			if source == "webhook":
				frappe.flags.razorpay_webhook_completion = False

		return custom_redirect_to

	# ------------------------------------------------------------------
	# HMAC signature verification
	# ------------------------------------------------------------------

	def verify_signature(self, body, signature, key):
		key = bytes(key, "utf-8")
		body = bytes(body, "utf-8")
		dig = hmac.new(key=key, msg=body, digestmod=hashlib.sha256)
		generated = dig.hexdigest()
		result = hmac.compare_digest(generated, signature)
		if not result:
			frappe.throw(_("Razorpay Signature Verification Failed"), exc=frappe.PermissionError)
		return result

	def verify_webhook_signature(self, body, signature, secret):
		"""
		Non-throwing HMAC-SHA256 check for Razorpay webhook payloads.
		``body`` may be str or bytes (raw request body). Returns True/False.
		"""
		if not secret or not signature:
			return False
		try:
			if isinstance(body, bytes):
				body_bytes = body
			else:
				body_bytes = bytes(body, "utf-8")
			key = bytes(secret, "utf-8")
			generated = hmac.new(key=key, msg=body_bytes, digestmod=hashlib.sha256).hexdigest()
			return hmac.compare_digest(generated, signature)
		except Exception:
			return False

	def identify_merchant_by_signature(self, body, signature):
		"""
		Identify which Razorpay Merchant (or global Settings) owns a webhook
		by testing ``webhook_secret`` against ``X-Razorpay-Signature``.

		Returns:
		    frappe._dict with api_key, api_secret, environment, merchant_name,
		    webhook_secret — or None if no secret matches.
		"""
		merchants = frappe.get_all("Razorpay Merchant", fields=["name"])
		for row in merchants:
			merchant = frappe.get_doc("Razorpay Merchant", row.name)
			secret = merchant.get_password(fieldname="webhook_secret", raise_exception=False)
			if secret and self.verify_webhook_signature(body, signature, secret):
				return frappe._dict(
					{
						"api_key": merchant.api_key,
						"api_secret": merchant.get_password(
							fieldname="api_secret", raise_exception=False
						),
						"environment": merchant.environment or "Test",
						"merchant_name": merchant.name,
						"webhook_secret": secret,
						"redirect_to": merchant.redirect_to or self.redirect_to or "",
					}
				)

		# Global fallback
		global_secret = self.get_password(fieldname="webhook_secret", raise_exception=False)
		if global_secret and self.verify_webhook_signature(body, signature, global_secret):
			return frappe._dict(
				{
					"api_key": self.api_key,
					"api_secret": self.get_password(fieldname="api_secret", raise_exception=False),
					"environment": self.environment or "Test",
					"merchant_name": None,
					"webhook_secret": global_secret,
					"redirect_to": self.redirect_to or "",
				}
			)

		return None

	# ------------------------------------------------------------------
	# Subscription support (unchanged from upstream)
	# ------------------------------------------------------------------

	def setup_addon(self, settings, **kwargs):
		url = "https://api.razorpay.com/v1/subscriptions/{}/addons".format(
			kwargs.get("subscription_id")
		)
		try:
			if not frappe.conf.converted_rupee_to_paisa:
				convert_rupee_to_paisa(**kwargs)
			for addon in kwargs.get("addons"):
				resp = make_post_request(
					url,
					auth=(settings.api_key, settings.api_secret),
					data=json.dumps(addon),
					headers={"content-type": "application/json"},
				)
				if not resp.get("id"):
					frappe.log_error(str(resp), "Razorpay Failed while creating subscription addon")
		except Exception:
			frappe.log_error()

	def setup_subscription(self, settings, **kwargs):
		start_date = (
			get_timestamp(kwargs.get("subscription_details").get("start_date"))
			if kwargs.get("subscription_details", {}).get("start_date")
			else None
		)
		subscription_details = {
			"plan_id": kwargs.get("subscription_details", {}).get("plan_id"),
			"total_count": kwargs.get("subscription_details", {}).get("billing_frequency"),
			"customer_notify": kwargs.get("subscription_details", {}).get("customer_notify"),
		}
		if start_date:
			subscription_details["start_at"] = cint(start_date)
		if kwargs.get("addons"):
			convert_rupee_to_paisa(**kwargs)
			subscription_details.update({"addons": kwargs.get("addons")})
		try:
			resp = make_post_request(
				"https://api.razorpay.com/v1/subscriptions",
				auth=(settings.api_key, settings.api_secret),
				data=json.dumps(subscription_details),
				headers={"content-type": "application/json"},
			)
			if resp.get("status") == "created":
				kwargs["subscription_id"] = resp.get("id")
				frappe.flags.status = "created"
				return kwargs
			else:
				frappe.log_error(str(resp), "Razorpay Failed while creating subscription")
		except Exception:
			frappe.log_error()

	def prepare_subscription_details(self, settings, **kwargs):
		if not kwargs.get("subscription_id"):
			kwargs = self.setup_subscription(settings, **kwargs)
		if frappe.flags.status != "created":
			kwargs["subscription_id"] = None
		return kwargs

	def cancel_subscription(self, subscription_id):
		creds = self.get_credentials()
		try:
			make_post_request(
				f"https://api.razorpay.com/v1/subscriptions/{subscription_id}/cancel",
				auth=(creds.api_key, creds.api_secret),
			)
		except Exception:
			frappe.log_error(frappe.get_traceback())

	# ------------------------------------------------------------------
	# Settings helper (kept for backward compat with subscription code)
	# ------------------------------------------------------------------

	def get_settings(self, data):
		"""Backward-compatible alias for get_credentials()."""
		return self.get_credentials(data=data)

	# ------------------------------------------------------------------
	# Desk actions
	# ------------------------------------------------------------------

	@frappe.whitelist()
	def clear(self):
		self.api_key = self.api_secret = None
		self.redirect_to = None
		self.flags.ignore_mandatory = True
		self.save()


# ----------------------------------------------------------------------
# Module-level whitelisted APIs
# ----------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def get_api_key():
	"""Return the global fallback API key (used by razorpay.js modal)."""
	controller = frappe.get_doc("Razorpay Settings")
	return controller.api_key


@frappe.whitelist(allow_guest=True)
def get_order(doctype, docname):
	"""Order returned to be consumed by razorpay.js (reference doctype must implement get_razorpay_order)."""
	doc = frappe.get_doc(doctype, docname)
	try:
		return doc.get_razorpay_order()
	except AttributeError:
		frappe.log_error(frappe.get_traceback(), _("Controller method get_razorpay_order missing"))
		frappe.throw(_("Could not create Razorpay order. Please contact Administrator."))


@frappe.whitelist(allow_guest=True)
def order_payment_success(integration_request, params):
	"""
	Called by razorpay.js on modal payment success.
	``params`` contains razorpay_payment_id, razorpay_order_id, razorpay_signature.
	"""
	params = json.loads(params)
	integration = frappe.get_doc("Integration Request", integration_request)
	integration.update_status(params, integration.status)
	integration.reload()

	data = json.loads(integration.data)
	controller = frappe.get_doc("Razorpay Settings")
	controller.integration_request = integration
	controller.data = frappe._dict(data)
	controller.data.update(params)
	controller.authorize_payment()


@frappe.whitelist(allow_guest=True)
def order_payment_failure(integration_request, params):
	"""Called by razorpay.js on failure."""
	frappe.log_error(params, "Razorpay Payment Failure")
	params = json.loads(params)
	integration = frappe.get_doc("Integration Request", integration_request)
	integration.update_status(params, integration.status)


@frappe.whitelist()
def validate_merchant_credentials(merchant_name):
	"""
	Validate Razorpay API credentials stored in a Razorpay Merchant record.
	Called from the merchant form's Test Connection button.
	"""
	try:
		merchant = frappe.get_doc("Razorpay Merchant", merchant_name)
		make_get_request(
			url="https://api.razorpay.com/v1/payments",
			auth=(
				merchant.api_key,
				merchant.get_password(fieldname="api_secret", raise_exception=False),
			),
		)
		return {"success": True}
	except Exception as e:
		return {"success": False, "error": str(e)}


def capture_payment(is_sandbox=False, sanbox_response=None):
	"""
	Scheduled job: capture all Integration Requests in 'Authorized' status.

	Note: New payments created with payment_capture=1 on the Razorpay order are
	auto-captured and will be in 'Completed' status immediately. This job only
	handles legacy 'Authorized' records from before auto-capture was enabled.
	"""
	controller = frappe.get_doc("Razorpay Settings")

	for doc in frappe.get_all(
		"Integration Request",
		filters={"status": "Authorized", "integration_request_service": "Razorpay"},
		fields=["name", "data"],
	):
		try:
			if is_sandbox:
				resp = sanbox_response
			else:
				data = json.loads(doc.data)
				creds = controller.get_credentials(data=data)

				resp = make_get_request(
					"https://api.razorpay.com/v1/payments/{}".format(
						data.get("razorpay_payment_id")
					),
					auth=(creds.api_key, creds.api_secret),
					data={"amount": data.get("amount")},
				)

				if resp.get("status") == "authorized":
					resp = make_post_request(
						"https://api.razorpay.com/v1/payments/{}/capture".format(
							data.get("razorpay_payment_id")
						),
						auth=(creds.api_key, creds.api_secret),
						data={"amount": data.get("amount")},
					)

			if resp.get("status") == "captured":
				frappe.db.set_value("Integration Request", doc.name, "status", "Completed")

		except Exception:
			doc_obj = frappe.get_doc("Integration Request", doc.name)
			doc_obj.status = "Failed"
			doc_obj.error = frappe.get_traceback()
			doc_obj.save()
			frappe.log_error(doc_obj.error, f"{doc_obj.name} Razorpay capture failed")


@frappe.whitelist(allow_guest=True)
def razorpay_subscription_callback():
	try:
		data = frappe.local.form_dict
		validate_payment_callback(data)
		data.update({"payment_gateway": "Razorpay"})
		doc = frappe.get_doc(
			{
				"data": json.dumps(frappe.local.form_dict),
				"doctype": "Integration Request",
				"request_description": "Subscription Notification",
				"is_remote_request": 1,
				"status": "Queued",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		frappe.enqueue(
			method="payments.payment_gateways.doctype.razorpay_settings.razorpay_settings.handle_subscription_notification",
			queue="long",
			timeout=600,
			is_async=True,
			**{"doctype": "Integration Request", "docname": doc.name},
		)
	except frappe.InvalidStatusError:
		pass
	except Exception as e:
		frappe.log(frappe.log_error(title=e))


def validate_payment_callback(data):
	def _throw():
		frappe.throw(_("Invalid Subscription"), exc=frappe.InvalidStatusError)

	subscription_id = data.get("payload", {}).get("subscription", {}).get("entity", {}).get("id")
	if not subscription_id:
		_throw()

	controller = frappe.get_doc("Razorpay Settings")
	creds = controller.get_credentials()
	resp = make_get_request(
		f"https://api.razorpay.com/v1/subscriptions/{subscription_id}",
		auth=(creds.api_key, creds.api_secret),
	)
	if resp.get("status") != "active":
		_throw()


def handle_subscription_notification(doctype, docname):
	call_hook_method("handle_subscription_notification", doctype=doctype, docname=docname)


def convert_rupee_to_paisa(**kwargs):
	for addon in kwargs.get("addons"):
		addon["item"]["amount"] *= 100
	frappe.conf.converted_rupee_to_paisa = True


# ----------------------------------------------------------------------
# External-frontend API  (mirrors CCAvenue / Easebuzz contract)
# ----------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def initiate_payment(**kwargs):
	"""
	Initiate a Razorpay payment from an external frontend (React/Next.js app).

	Unlike CCAvenue/Easebuzz which redirect the browser to a hosted page,
	Razorpay uses an in-page JavaScript modal.  This endpoint creates a
	Razorpay *order* on the server side and returns the credentials/order
	details needed for the frontend to open the Checkout.js modal.

	Required kwargs
	---------------
	amount            float   Payment amount (in major currency units, e.g. INR)
	reference_doctype str     ERPNext doctype being paid (e.g. "Sales Invoice")
	reference_docname str     ERPNext document name
	payer_email       str     Payer e-mail address
	payer_name        str     Customer ID or display name

	Optional kwargs
	---------------
	currency          str     ISO currency code (default: "INR")
	company           str     Company name – drives merchant selection
	custom_merchant_name str  Explicit Razorpay Merchant record name
	description       str     Payment description
	custom_pincode    str     Customer pincode (stored in notes)
	custom_state      str     Customer state (stored in notes)
	phone             str     Customer phone (stored in notes)

	Returns
	-------
	{
	    "success": True,
	    "payment_token": "<integration_request_name>",
	    "order_id":      "<razorpay_order_id>",
	    "api_key":       "<razorpay_api_key>",       # for Checkout.js
	    "amount":        <amount_in_paise>,
	    "currency":      "INR",
	    "merchant_name": "<merchant_record_name>",
	    "company":       "<company>",
	    "environment":   "Test|Production",
	    "prefill": {
	        "name":   "<payer_name>",
	        "email":  "<payer_email>",
	        "contact": "<phone>"
	    }
	}
	"""
	try:
		required_params = ["amount", "reference_doctype", "reference_docname", "payer_email", "payer_name"]
		for param in required_params:
			if not kwargs.get(param):
				return {"success": False, "error": f"Missing required parameter: {param}"}

		kwargs.setdefault("currency", "INR")
		kwargs.setdefault("payment_gateway", "Razorpay")

		settings = frappe.get_doc("Razorpay Settings")
		order = settings.create_order(**kwargs)

		integration_request_name = order.get("integration_request")
		if not integration_request_name:
			return {"success": False, "error": "Failed to create integration request"}

		# Resolve credentials to get api_key and environment for the frontend
		company = kwargs.get("company")
		merchant_name = kwargs.get("custom_merchant_name")
		creds = settings.get_credentials(
			data=kwargs, company=company, merchant_name=merchant_name
		)

		# Get customer details for Checkout.js prefill
		customer_name = kwargs.get("payer_name")
		phone = kwargs.get("phone", "")
		if customer_name and frappe.db.exists("Customer", customer_name) and not phone:
			phone = frappe.db.get_value("Customer", customer_name, "mobile_no") or ""

		return {
			"success": True,
			"payment_token": integration_request_name,
			"order_id": order.get("id"),
			"api_key": creds.api_key,
			"amount": order.get("amount"),  # already in paise
			"currency": order.get("currency", kwargs.get("currency", "INR")),
			"merchant_name": creds.get("merchant_name"),
			"company": company or "",
			"environment": creds.get("environment", "Test"),
			"prefill": {
				"name": customer_name or "",
				"email": kwargs.get("payer_email", ""),
				"contact": phone,
			},
		}

	except Exception as e:
		frappe.log_error(
			f"Razorpay initiate_payment error: {str(e)}\n{frappe.get_traceback()}",
			"Razorpay Payment Initiation Error",
		)
		return {"success": False, "error": str(e)}


@frappe.whitelist(allow_guest=True)
def verify_payment(razorpay_payment_id, razorpay_order_id, razorpay_signature, token):
	"""
	Verify a completed Razorpay payment and trigger ERPNext authorization.

	Called by the external frontend after the Checkout.js modal fires the
	``payment.success`` event.  Verifies the HMAC-SHA256 signature, restores
	the Frappe user session, updates the Integration Request and calls
	``authorize_payment()`` – identical to what CCAvenue/Easebuzz do in
	their ``verify_transaction`` endpoints.

	Parameters
	----------
	razorpay_payment_id  str  ``razorpay_payment_id`` from Checkout.js handler
	razorpay_order_id    str  ``razorpay_order_id`` from Checkout.js handler
	razorpay_signature   str  ``razorpay_signature`` from Checkout.js handler
	token                str  Integration Request name (``payment_token`` from
	                          the ``initiate_payment`` response)

	Returns
	-------
	{
	    "success": True,
	    "status": "<integration_request_status>",
	    "payment_id": "<razorpay_payment_id>",
	    "redirect_to": "<url>",
	    "reference_doctype": "...",
	    "reference_docname": "..."
	}
	"""
	try:
		integration_request = frappe.get_doc("Integration Request", token)

		# Duplicate-prevention: skip if already processed
		if integration_request.status in ("Completed", "Authorized"):
			frappe.logger().info(
				f"Razorpay verify_payment: {token} already processed "
				f"with status {integration_request.status}. Skipping."
			)
			data = json.loads(integration_request.data) if integration_request.data else {}
			return {
				"success": True,
				"message": "Payment already processed",
				"status": integration_request.status,
				"payment_id": razorpay_payment_id,
				"reference_doctype": data.get("reference_doctype"),
				"reference_docname": data.get("reference_docname"),
			}

		data = json.loads(integration_request.data) if integration_request.data else {}

		# Restore user session (same pattern as CCAvenue / Easebuzz)
		notes = data.get("notes") or {}
		if isinstance(notes, str):
			try:
				notes = json.loads(notes)
			except Exception:
				notes = {}
		user = notes.get("user") or data.get("user") or ""
		if user and user != "Guest" and frappe.session.user == "Guest":
			try:
				frappe.set_user(user)
				frappe.local.login_manager.login_as(user)
			except Exception:
				frappe.log_error(frappe.get_traceback(), "Razorpay session restore error")

		# Resolve merchant credentials for signature verification
		settings = frappe.get_doc("Razorpay Settings")
		company = data.get("company") or (notes.get("company") if isinstance(notes, dict) else None)
		merchant_name = (
			data.get("custom_merchant_name")
			or (notes.get("merchant_name") if isinstance(notes, dict) else None)
		)
		creds = settings.get_credentials(data=data, company=company, merchant_name=merchant_name)

		# Verify HMAC-SHA256 signature: order_id + "|" + payment_id
		body = f"{razorpay_order_id}|{razorpay_payment_id}"
		try:
			settings.verify_signature(body, razorpay_signature, creds.api_secret)
		except frappe.PermissionError as sig_err:
			frappe.log_error(str(sig_err), "Razorpay Signature Verification Failed")
			return {"success": False, "error": "Signature verification failed"}

		# Merge Razorpay callback params into integration data
		data.update(
			{
				"razorpay_payment_id": razorpay_payment_id,
				"razorpay_order_id": razorpay_order_id,
				"razorpay_signature": razorpay_signature,
				"user": user or frappe.session.user,
				"webhook_source": "verify_payment_api",
			}
		)
		integration_request.data = json.dumps(data)
		integration_request.save(ignore_permissions=True)
		frappe.db.commit()

		# Authorize payment
		controller = frappe.get_doc("Razorpay Settings")
		controller.integration_request = integration_request
		controller.data = frappe._dict(data)
		controller.data.razorpay_payment_id = razorpay_payment_id
		controller.data.reference_doctype = data.get("reference_doctype", "")
		controller.data.reference_docname = data.get("reference_docname", "")
		result = controller.authorize_payment()

		# Set session cookies so the browser retains the restored session
		if user and user != "Guest":
			try:
				frappe.local.cookie_manager.set_cookie("system_user", user)
				frappe.local.cookie_manager.set_cookie("user_id", user)
				frappe.local.cookie_manager.set_cookie("sid", frappe.session.sid)
			except Exception:
				pass

		return {
			"success": True,
			"status": result.get("status"),
			"payment_id": razorpay_payment_id,
			"redirect_to": result.get("redirect_to"),
			"reference_doctype": data.get("reference_doctype"),
			"reference_docname": data.get("reference_docname"),
		}

	except frappe.DoesNotExistError:
		return {"success": False, "error": "Payment request not found"}
	except Exception as e:
		frappe.log_error(
			f"Razorpay verify_payment error: {str(e)}\n{frappe.get_traceback()}",
			"Razorpay Payment Verification Error",
		)
		return {"success": False, "error": str(e)}


@frappe.whitelist(allow_guest=True)
def refund_status():
	"""
	Webhook endpoint for Razorpay refund events.

	Razorpay sends a signed JSON payload to this URL for events such as
	``refund.created``, ``refund.processed``, and ``refund.failed``.

	Configure this URL in the Razorpay Dashboard under
	Settings → Webhooks: ``<your-site>/api/method/payments.payment_gateways.doctype.razorpay_settings.razorpay_settings.refund_status``

	Webhook secret is verified via the ``X-Razorpay-Signature`` header.
	The endpoint calls ``on_refund_status_update(refund_data)`` on the
	original reference document if it implements the method.

	Returns HTTP 200 in all non-error cases so Razorpay stops retrying.
	"""
	try:
		payload_bytes = frappe.request.data
		signature = frappe.request.headers.get("X-Razorpay-Signature", "")

		if not payload_bytes:
			frappe.local.response.http_status_code = 400
			return {"success": False, "error": "Empty payload"}

		data = json.loads(payload_bytes)
		event = data.get("event", "")

		if not event.startswith("refund."):
			# Not a refund event – acknowledge and ignore
			return {"success": True, "message": "Event ignored"}

		refund_entity = (
			data.get("payload", {}).get("refund", {}).get("entity", {})
		)
		payment_id = refund_entity.get("payment_id")
		refund_id = refund_entity.get("id")
		refund_status_val = refund_entity.get("status")

		if not payment_id:
			return {"success": False, "error": "payment_id missing from refund payload"}

		# Find the Integration Request by razorpay_payment_id stored in data
		integration_requests = frappe.get_all(
			"Integration Request",
			filters={"integration_request_service": "Razorpay"},
			fields=["name", "data", "reference_doctype", "reference_docname"],
		)

		integration_request = None
		for ir in integration_requests:
			ir_data = json.loads(ir.data) if ir.data else {}
			if ir_data.get("razorpay_payment_id") == payment_id or ir_data.get("order_id") == refund_entity.get("payment_id"):
				integration_request = frappe.get_doc("Integration Request", ir.name)
				break

		if not integration_request:
			frappe.log_error(
				f"Integration Request not found for Razorpay payment_id={payment_id} refund_id={refund_id}",
				"Razorpay Refund Webhook",
			)
			return {"success": True, "message": "Integration Request not found – acknowledged"}

		# Verify signature if a webhook secret is available
		settings = frappe.get_doc("Razorpay Settings")
		ir_data = json.loads(integration_request.data) if integration_request.data else {}
		try:
			creds = settings.get_credentials(data=ir_data)
			if creds.api_secret and signature:
				settings.verify_signature(
					payload_bytes.decode("utf-8"), signature, creds.api_secret
				)
		except frappe.PermissionError:
			frappe.log_error("Razorpay refund signature verification failed", "Razorpay Refund Webhook")
			frappe.local.response.http_status_code = 401
			return {"success": False, "error": "Signature verification failed"}
		except Exception:
			# If signature check isn't possible (no secret configured), log and continue
			frappe.log_error(frappe.get_traceback(), "Razorpay Refund Signature Check Warning")

		# Update the integration request with refund details
		ir_data.update(
			{
				"refund_id": refund_id,
				"refund_status": refund_status_val,
				"refund_amount": refund_entity.get("amount"),
				"refund_event": event,
			}
		)
		integration_request.data = json.dumps(ir_data)
		integration_request.save(ignore_permissions=True)
		frappe.db.commit()

		# Call on_refund_status_update on the reference document if it exists
		if integration_request.reference_doctype and integration_request.reference_docname:
			try:
				ref_doc = frappe.get_doc(
					integration_request.reference_doctype,
					integration_request.reference_docname,
				)
				if hasattr(ref_doc, "on_refund_status_update"):
					ref_doc.run_method(
						"on_refund_status_update",
						{
							"refund_id": refund_id,
							"payment_id": payment_id,
							"status": refund_status_val,
							"amount": refund_entity.get("amount"),
							"event": event,
							"gateway": "Razorpay",
						},
					)
			except Exception:
				frappe.log_error(
					frappe.get_traceback(),
					f"Razorpay on_refund_status_update error for {integration_request.reference_doctype} {integration_request.reference_docname}",
				)

		return {
			"success": True,
			"refund_id": refund_id,
			"status": refund_status_val,
		}

	except Exception as e:
		frappe.log_error(
			f"Razorpay refund webhook error: {str(e)}\n{frappe.get_traceback()}",
			"Razorpay Refund Webhook Error",
		)
		return {"success": False, "error": str(e)}


@frappe.whitelist(allow_guest=True)
def payment_captured():
	"""
	Webhook endpoint for Razorpay ``payment.captured`` events.

	Acts as a **fallback** only: if the preferred frontend callback
	(``verify_payment``) has already completed the Integration Request, this
	endpoint acknowledges and does nothing. Otherwise it stashes the captured
	payload on the IR and lets the grace-period scheduler finish processing.

	Configure in the Razorpay Dashboard under Settings → Webhooks:
	``<site>/api/method/payments.payment_gateways.doctype.razorpay_settings.razorpay_settings.payment_captured``

	Subscribe to the ``payment.captured`` event. Use the per-merchant
	``webhook_secret`` (or the global Settings fallback) for signature verification.
	"""
	try:
		payload_bytes = frappe.request.data
		signature = frappe.request.headers.get("X-Razorpay-Signature", "")

		if not payload_bytes:
			frappe.local.response.http_status_code = 400
			return {"success": False, "error": "Empty payload"}

		data = json.loads(payload_bytes)
		event = data.get("event", "")

		if event != "payment.captured":
			return {"success": True, "message": "Event ignored"}

		settings = frappe.get_doc("Razorpay Settings")
		creds = settings.identify_merchant_by_signature(payload_bytes, signature)
		if not creds:
			frappe.log_error(
				"No Razorpay Merchant/Settings webhook_secret matched the signature",
				"Razorpay payment.captured Webhook",
			)
			frappe.local.response.http_status_code = 401
			return {"success": False, "error": "Signature verification failed"}

		payment_entity = data.get("payload", {}).get("payment", {}).get("entity", {}) or {}
		payment_id = payment_entity.get("id")
		order_id = payment_entity.get("order_id")
		acquirer_data = payment_entity.get("acquirer_data") or {}
		upi_rrn = (
			acquirer_data.get("rrn")
			or acquirer_data.get("upi_transaction_id")
			or payment_entity.get("acquirer_data", {}).get("rrn")
			or ""
		)

		if not order_id and not payment_id:
			return {"success": False, "error": "order_id and payment_id missing from payload"}

		integration_request = _find_integration_request_for_captured_payment(
			order_id=order_id,
			payment_id=payment_id,
			creds=creds,
		)

		if not integration_request:
			frappe.log_error(
				f"Integration Request not found for Razorpay payment_id={payment_id} order_id={order_id}",
				"Razorpay payment.captured Webhook",
			)
			# ACK so Razorpay stops retrying unknown/orphan events
			return {"success": True, "message": "Integration Request not found – acknowledged"}

		if integration_request.status in ("Completed", "Authorized"):
			return {
				"success": True,
				"message": "Already processed by callback",
				"status": integration_request.status,
				"integration_request": integration_request.name,
			}

		ir_data = json.loads(integration_request.data) if integration_request.data else {}
		ir_data.update(
			{
				"razorpay_payment_id": payment_id,
				"razorpay_order_id": order_id or ir_data.get("razorpay_order_id"),
				"upi_rrn": upi_rrn,
				"payment_method": payment_entity.get("method"),
				"webhook_source": "payment.captured",
				"webhook_capture_pending": 1,
				"webhook_captured_at": str(now_datetime()),
				"webhook_merchant_name": creds.get("merchant_name") or "",
			}
		)
		# Ensure reference fields are present for the scheduler handler
		if not ir_data.get("reference_doctype"):
			ir_data["reference_doctype"] = integration_request.reference_doctype
		if not ir_data.get("reference_docname"):
			ir_data["reference_docname"] = integration_request.reference_docname

		integration_request.db_set("data", json.dumps(ir_data))
		frappe.db.commit()

		return {
			"success": True,
			"message": "Captured payload stashed; awaiting grace period",
			"integration_request": integration_request.name,
			"payment_id": payment_id,
		}

	except Exception as e:
		frappe.log_error(
			f"Razorpay payment.captured webhook error: {str(e)}\n{frappe.get_traceback()}",
			"Razorpay payment.captured Webhook Error",
		)
		return {"success": False, "error": str(e)}


def _find_integration_request_for_captured_payment(order_id=None, payment_id=None, creds=None):
	"""
	Locate the Razorpay Integration Request for a captured payment.

	Lookup order:
	  1. IR whose data JSON contains the given razorpay_order_id / order_id
	  2. IR whose data JSON contains the given razorpay_payment_id
	  3. Fetch Razorpay order → notes.token / receipt → IR name
	"""
	# Prefer SQL LIKE on recent Razorpay IRs rather than loading every row.
	# Cap the scan window to keep this cheap under load.
	candidates = frappe.get_all(
		"Integration Request",
		filters={"integration_request_service": "Razorpay"},
		fields=["name", "data", "status", "reference_doctype", "reference_docname"],
		order_by="creation desc",
		limit_page_length=500,
	)

	order_match = None
	payment_match = None
	for ir in candidates:
		ir_data = {}
		try:
			ir_data = json.loads(ir.data) if ir.data else {}
		except Exception:
			continue

		stored_order = ir_data.get("razorpay_order_id") or ir_data.get("order_id")
		stored_payment = ir_data.get("razorpay_payment_id")

		if order_id and stored_order == order_id:
			order_match = ir.name
			break
		if payment_id and stored_payment == payment_id and not payment_match:
			payment_match = ir.name

	ir_name = order_match or payment_match
	if ir_name:
		return frappe.get_doc("Integration Request", ir_name)

	# Fallback: ask Razorpay for the order notes/receipt
	if order_id and creds and creds.get("api_key") and creds.get("api_secret"):
		try:
			order = make_get_request(
				f"https://api.razorpay.com/v1/orders/{order_id}",
				auth=(creds.api_key, creds.api_secret),
			)
			notes = order.get("notes") or {}
			if isinstance(notes, str):
				try:
					notes = json.loads(notes)
				except Exception:
					notes = {}
			token = notes.get("token") if isinstance(notes, dict) else None
			receipt = order.get("receipt")
			for candidate in (token, receipt):
				if candidate and frappe.db.exists("Integration Request", candidate):
					return frappe.get_doc("Integration Request", candidate)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				"Razorpay payment.captured: order lookup failed",
			)

	return None


def process_webhook_captured_payments():
	"""
	Scheduled job: complete Razorpay Integration Requests that were stashed by
	the payment.captured webhook and whose grace period has elapsed.

	If the preferred callback already marked the IR Completed/Authorized during
	the grace window, the pending flag is cleared and nothing else is done.
	"""
	grace_cutoff = add_to_date(now_datetime(), minutes=-WEBHOOK_CAPTURE_GRACE_MINUTES)
	candidates = frappe.get_all(
		"Integration Request",
		filters={
			"integration_request_service": "Razorpay",
			"status": ["not in", ["Completed", "Authorized", "Cancelled"]],
		},
		fields=["name", "data", "status", "reference_doctype", "reference_docname"],
		order_by="creation desc",
		limit_page_length=200,
	)

	controller = frappe.get_doc("Razorpay Settings")

	for row in candidates:
		try:
			ir_data = json.loads(row.data) if row.data else {}
		except Exception:
			continue

		if not ir_data.get("webhook_capture_pending"):
			continue

		captured_at = ir_data.get("webhook_captured_at")
		if not captured_at:
			continue
		try:
			if get_datetime(captured_at) > grace_cutoff:
				continue  # still inside grace window
		except Exception:
			continue

		try:
			integration_request = frappe.get_doc("Integration Request", row.name)
			integration_request.reload()

			# Callback may have finished during the grace window
			if integration_request.status in ("Completed", "Authorized"):
				ir_data = json.loads(integration_request.data) if integration_request.data else {}
				ir_data["webhook_capture_pending"] = 0
				ir_data["webhook_skipped_reason"] = "callback_completed_during_grace"
				integration_request.db_set("data", json.dumps(ir_data))
				frappe.db.commit()
				continue

			ir_data = json.loads(integration_request.data) if integration_request.data else {}
			ir_data["webhook_capture_pending"] = 0
			ir_data["webhook_processed_at"] = str(now_datetime())
			ir_data["webhook_source"] = ir_data.get("webhook_source") or "payment.captured"

			# Mark Completed then run the same success handlers as the callback
			integration_request.update_status(ir_data, "Completed")
			integration_request.reload()

			controller.integration_request = integration_request
			controller.data = frappe._dict(ir_data)
			controller.data.razorpay_payment_id = ir_data.get("razorpay_payment_id")
			controller.data.razorpay_order_id = ir_data.get("razorpay_order_id")
			controller.data.reference_doctype = (
				ir_data.get("reference_doctype") or integration_request.reference_doctype
			)
			controller.data.reference_docname = (
				ir_data.get("reference_docname") or integration_request.reference_docname
			)

			controller.run_payment_success_handlers(
				integration_request,
				ir_data,
				"Completed",
				source="webhook",
			)
			frappe.db.commit()

		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"Razorpay webhook fallback failed for {row.name}",
			)
			frappe.db.rollback()


@frappe.whitelist(allow_guest=True)
def check_payment_status(integration_request_name):
	"""
	Poll the status of a Razorpay payment by Integration Request name.

	Returns
	-------
	{
	    "success": True,
	    "status":            "Queued|Authorized|Completed|Failed",
	    "payment_id":        "<razorpay_payment_id>",
	    "order_id":          "<razorpay_order_id>",
	    "amount":            <float>,
	    "currency":          "INR",
	    "reference_doctype": "...",
	    "reference_docname": "...",
	    "company":           "...",
	    "merchant_name":     "..."
	}
	"""
	try:
		integration_request = frappe.get_doc("Integration Request", integration_request_name)
		data = json.loads(integration_request.data) if integration_request.data else {}
		notes = data.get("notes") or {}
		if isinstance(notes, str):
			try:
				notes = json.loads(notes)
			except Exception:
				notes = {}

		return {
			"success": True,
			"status": integration_request.status,
			"payment_id": data.get("razorpay_payment_id"),
			"order_id": data.get("razorpay_order_id") or data.get("order_id"),
			"amount": data.get("amount"),
			"currency": data.get("currency", "INR"),
			"reference_doctype": integration_request.reference_doctype or data.get("reference_doctype"),
			"reference_docname": integration_request.reference_docname or data.get("reference_docname"),
			"company": data.get("company") or (notes.get("company") if isinstance(notes, dict) else None),
			"merchant_name": data.get("custom_merchant_name") or (
				notes.get("merchant_name") if isinstance(notes, dict) else None
			),
		}

	except frappe.DoesNotExistError:
		return {"success": False, "error": "Payment request not found"}
	except Exception as e:
		frappe.log_error(
			f"Razorpay check_payment_status error: {str(e)}\n{frappe.get_traceback()}",
			"Razorpay Payment Status Error",
		)
		return {"success": False, "error": str(e)}
