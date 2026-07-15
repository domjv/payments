# Copyright (c) 2026, Frappe Technologies and Contributors
# License: MIT. See LICENSE

import json
import unittest
from unittest.mock import patch

import frappe

from payments.payment_gateways.doctype.razorpay_settings.razorpay_settings import (
	payment_captured_webhook,
)


class TestRazorpayCapturedWebhook(unittest.TestCase):
	def test_ignores_non_captured_events(self):
		with patch.object(
			frappe,
			"request",
			frappe._dict(
				{
					"data": json.dumps({"event": "payment.authorized"}).encode("utf-8"),
					"headers": {},
				}
			),
		):
			response = payment_captured_webhook()

		self.assertTrue(response.get("success"))
		self.assertEqual(response.get("message"), "Event ignored")

	def test_empty_payload_returns_error(self):
		with patch.object(
			frappe,
			"request",
			frappe._dict(
				{
					"data": b"",
					"headers": {},
				}
			),
		):
			response = payment_captured_webhook()

		self.assertFalse(response.get("success"))
		self.assertEqual(response.get("error"), "Empty payload")
