import frappe
import requests
from frappe import _
from frappe.model.document import Document
from payments.utils import create_payment_gateway

class EasebuzzSettings(Document):
    supported_currencies = ("INR",)

    def validate(self):
        print("validate")
        """Validate the settings and create the payment gateway entry."""
        create_payment_gateway("Easebuzz")
    #     self.validate_transaction_currency()

    def validate_transaction_currency(self):
        """Ensure the selected currency is supported by Easebuzz."""
        if self.currency not in self.supported_currencies:
            frappe.throw(
                _("Easebuzz does not support transactions in currency '{0}'").format(self.currency)
            )

    def get_payment_url(self, **kwargs):
        """Generate the payment URL for Easebuzz."""
        base_url = "https://sandbox.easebuzz.in" if self.environment == "Sandbox" else "https://easebuzz.in"
        return f"{base_url}/payment/initiate"

    def get_headers(self):
        """Return the headers required for API requests."""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
    pass

@frappe.whitelist()
def test_connection():
    """Test the API connection with Easebuzz."""
    settings = frappe.get_doc("Easebuzz Settings")
    if not settings.api_key or not settings.api_secret:
        frappe.throw(_("Please configure the API Key and Secret Key in the Easebuzz Settings form."))

    url = "https://sandbox.easebuzz.in/test-api" if settings.environment == "Sandbox" else "https://easebuzz.in/test-api"
    headers = {
        "Authorization": f"Bearer {settings.api_key}"
    }

    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return True
        else:
            frappe.throw(_("Failed to connect to Easebuzz. Please check your credentials."))
    except Exception as e:
        frappe.throw(_("An error occurred: {0}").format(str(e)))
