frappe.provide("frappe.checkout");

frappe.checkout.ccavenue = class CCAvenueCheckout {
  constructor(opts) {
    Object.assign(this, opts);
  }

  init() {
    frappe.run_serially([
      () => this.make_order(),
      () => this.prepare_checkout(),
    ]);
  }

  make_order() {
    return new Promise((resolve) => {
      frappe
        .call({
          method: "payments.payment_gateways.doctype.ccavenue_settings.ccavenue_settings.create_order",
          args: {
            doctype: this.doctype,
            docname: this.docname,
            amount: this.amount,
            payer_name: this.payer_name,
            payer_email: this.payer_email,
            currency: this.currency
          }
        })
        .then((res) => {
          this.order = res.message;
          resolve(true);
        });
    });
  }

  prepare_checkout() {
    // Redirect to checkout URL
    if (this.order && this.order.redirect_url) {
      window.location.href = this.order.redirect_url;
    } else {
      frappe.msgprint(__("Error creating payment order"));
    }
  }
};