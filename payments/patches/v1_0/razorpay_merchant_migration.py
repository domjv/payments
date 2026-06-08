# Copyright (c) 2026, Frappe Technologies and contributors
# License: MIT. See LICENSE

"""
Migration patch: seed default Razorpay Merchant from existing Razorpay Settings.

Runs once via patches.txt after bench migrate.

What this does:
  1. If no Razorpay Merchant records exist and Razorpay Settings has api_key/secret,
     creates a default Razorpay Merchant named "Default" with:
       - api_key / api_secret copied from Razorpay Settings
       - environment = "Test" (safe default; admin should change to Production)
       - is_default = 1
  2. Processes lingering Integration Requests with status "Authorized" and
     integration_request_service "Razorpay" – attempts to capture them via
     the Razorpay API and marks them Completed.  This clears the backlog
     before the scheduler-based capture is deprecated.
  3. No data is deleted or destructively modified.

Safe to run on a production instance.
"""

import json

import frappe
from frappe import _
from frappe.integrations.utils import make_get_request, make_post_request


def execute():
	_seed_default_merchant()
	_capture_authorized_payments()


def _seed_default_merchant():
	"""Create a default Razorpay Merchant record from global Settings if none exist."""
	if frappe.db.count("Razorpay Merchant") > 0:
		frappe.logger().info("razorpay_merchant_migration: Merchant records already exist, skipping seed.")
		return

	settings = frappe.get_doc("Razorpay Settings")
	if not settings.api_key:
		frappe.logger().info(
			"razorpay_merchant_migration: No api_key in Razorpay Settings, skipping default merchant creation."
		)
		return

	frappe.get_doc(
		{
			"doctype": "Razorpay Merchant",
			"merchant_name": "Default",
			"is_default": 1,
			"api_key": settings.api_key,
			"api_secret": settings.get_password(fieldname="api_secret", raise_exception=False) or "",
			"environment": "Test",
		}
	).insert(ignore_permissions=True)
	frappe.db.commit()
	frappe.logger().info("razorpay_merchant_migration: Created default Razorpay Merchant from Settings.")


def _capture_authorized_payments():
	"""
	Attempt to capture lingering 'Authorized' Razorpay Integration Requests.

	New orders use payment_capture=1 so they are auto-captured.  This routine
	handles any pre-migration records that are still in 'Authorized' status.
	"""
	authorized = frappe.get_all(
		"Integration Request",
		filters={"status": "Authorized", "integration_request_service": "Razorpay"},
		fields=["name", "data"],
	)

	if not authorized:
		return

	frappe.logger().info(
		f"razorpay_merchant_migration: Found {len(authorized)} Authorized Razorpay payment(s) to capture."
	)

	settings = frappe.get_doc("Razorpay Settings")

	for ir in authorized:
		try:
			data = json.loads(ir.data) if ir.data else {}
			payment_id = data.get("razorpay_payment_id")
			if not payment_id:
				continue

			creds = settings.get_credentials(data=data)

			resp = make_get_request(
				f"https://api.razorpay.com/v1/payments/{payment_id}",
				auth=(creds.api_key, creds.api_secret),
			)

			if resp.get("status") == "captured":
				frappe.db.set_value("Integration Request", ir.name, "status", "Completed")
				frappe.db.commit()
				frappe.logger().info(
					f"razorpay_merchant_migration: {ir.name} already captured – marked Completed."
				)
			elif resp.get("status") == "authorized":
				capture_resp = make_post_request(
					f"https://api.razorpay.com/v1/payments/{payment_id}/capture",
					auth=(creds.api_key, creds.api_secret),
					data={"amount": data.get("amount")},
				)
				if capture_resp.get("status") == "captured":
					frappe.db.set_value("Integration Request", ir.name, "status", "Completed")
					frappe.db.commit()
					frappe.logger().info(
						f"razorpay_merchant_migration: Captured {ir.name} successfully."
					)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"razorpay_merchant_migration: Failed to capture {ir.name}",
			)
