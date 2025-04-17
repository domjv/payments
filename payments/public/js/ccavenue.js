// Copyright (c) 2024, Frappe Technologies and contributors
// For license information, please see license.txt

/* HOW-TO

CCAvenue Payment

1. 	Include checkout script in your code
    {{ include_script('/assets/payments/js/ccavenue.js') }}

2.	Create payment details in your backend
    def get_ccavenue_payment(self):
        from payments.utils import get_payment_gateway_controller

        controller = get_payment_gateway_controller("CCAvenue")

        payment_details = {
            "amount": 300,
            "title": "Payment for Order #123",
            "description": "Payment for Order #123",
            "reference_doctype": "Your DocType",
            "reference_docname": self.name,
            "payer_name": "Customer Name",
            "payer_email": "customer@example.com",
            "order_id": self.name,
            "currency": "INR"
        }

        return controller.get_payment_url(**payment_details)

3. 	Initiate the payment in client
    function make_payment() {
        var payment_url = {{ get_ccavenue_payment() }};
        window.location.href = payment_url;
    }
*/

frappe.provide("frappe.checkout");

frappe.checkout.ccavenue = class CCAvenueCheckout {
  constructor(opts) {
    Object.assign(this, opts);
  }

  init() {
    var me = this;
    
    return new Promise(function(resolve, reject) {
      if(me.order_id) {
        me.process_payment();
        resolve();
      } else {
        reject("Missing order_id");
      }
    });
  }

  process_payment() {
    var me = this;
    
    frappe.call({
      method: "frappe.client.get",
      args: {
        doctype: me.doctype,
        name: me.docname
      },
      callback: function(r) {
        if(r.message && r.message.ccavenue_payment_url) {
          window.location.href = r.message.ccavenue_payment_url;
        } else {
          frappe.msgprint(__("Unable to process payment. Please try again."));
        }
      }
    });
  }
};