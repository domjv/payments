# Lightweight Cashfree REST client generated from cashfree-openapi.yaml
# Uses requests to call the core Orders/Payments/Payment Links endpoints.

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Optional

import requests


class CashfreeClient:
	"""Minimal REST client for the Cashfree PG API."""

	# The live Cashfree PG API currently expects 2023-08-01 for most endpoints.
	DEFAULT_API_VERSION = "2023-08-01"

	def __init__(self, client_id: str, client_secret: str, environment: str, api_version: str | None = None):
		self.client_id = client_id
		self.client_secret = client_secret
		self.environment = environment
		self.base_url = (
			"https://api.cashfree.com/pg"
			if environment == "Production"
			else "https://sandbox.cashfree.com/pg"
		)
		self.api_version = api_version or self.DEFAULT_API_VERSION
		self.session = requests.Session()

	def _headers(self, include_content_type: bool = False) -> Dict[str, str]:
		headers = {
			"x-client-id": self.client_id,
			"x-client-secret": self.client_secret,
			"x-api-version": self.api_version,
			"Accept": "application/json",
		}
		if include_content_type:
			headers["Content-Type"] = "application/json"
		return headers

	def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
		url = f"{self.base_url}{path}"
		resp = self.session.post(
			url,
			headers=self._headers(include_content_type=True),
			json=payload,
			timeout=30,
		)
		self._raise_for_status(resp)
		return resp.json()

	def _get(self, path: str) -> Dict[str, Any]:
		url = f"{self.base_url}{path}"
		resp = self.session.get(url, headers=self._headers(), timeout=30)
		self._raise_for_status(resp)
		if resp.text:
			return resp.json()
		return {}

	def _raise_for_status(self, resp: requests.Response) -> None:
		try:
			resp.raise_for_status()
		except requests.HTTPError as exc:
			# Try to surface Cashfree error payload for easier debugging
			message = None
			try:
				err_json = resp.json()
				message = json.dumps(err_json)
			except Exception:
				message = resp.text
			raise requests.HTTPError(f"{resp.status_code} error from Cashfree: {message}") from exc

	def check_credentials(self) -> bool:
		"""Hit a known missing order to validate headers. 404 implies auth success."""
		random_order = f"health-{uuid.uuid4().hex}"
		url = f"{self.base_url}/orders/{random_order}"
		resp = self.session.get(url, headers=self._headers(), timeout=30)

		# 404 is expected (order missing) and means auth headers are accepted.
		if resp.status_code == 404:
			return True

		# 2xx would also be fine (unlikely here)
		if 200 <= resp.status_code < 300:
			return True

		try:
			detail = resp.json()
		except Exception:
			detail = resp.text

		raise requests.HTTPError(f"Cashfree responded with {resp.status_code}: {detail}")

	def create_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
		return self._post("/orders", payload)

	def fetch_order(self, order_id: str) -> Dict[str, Any]:
		return self._get(f"/orders/{order_id}")

	def create_payment_session(self, payload: Dict[str, Any]) -> Dict[str, Any]:
		return self._post("/orders/sessions", payload)

	def create_payment_link(self, payload: Dict[str, Any]) -> Dict[str, Any]:
		return self._post("/links", payload)

	def fetch_payment_link(self, link_id: str) -> Dict[str, Any]:
		return self._get(f"/links/{link_id}")
