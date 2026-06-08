// Copyright (c) 2026, Frappe Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on("Razorpay Merchant", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Test Connection"), function () {
				frappe.call({
					method:
						"payments.payment_gateways.doctype.razorpay_settings.razorpay_settings.validate_merchant_credentials",
					args: { merchant_name: frm.doc.name },
					callback(r) {
						if (r.message && r.message.success) {
							frappe.msgprint({
								title: __("Connection Successful"),
								message: __("Razorpay credentials for {0} are valid.", [frm.doc.merchant_name]),
								indicator: "green",
							});
						} else {
							frappe.msgprint({
								title: __("Connection Failed"),
								message: r.message ? r.message.error : __("Unknown error"),
								indicator: "red",
							});
						}
					},
				});
			});
		}
	},
});
