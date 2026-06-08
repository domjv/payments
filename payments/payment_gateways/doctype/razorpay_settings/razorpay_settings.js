// Copyright (c) 2016, Frappe Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on("Razorpay Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Clear"), function () {
			frm.call({
				doc: frm.doc,
				method: "clear",
				callback(r) {
					frm.refresh();
				},
			});
		});

		if (frm.doc.api_key && frm.doc.api_secret) {
			frm.add_custom_button(__("Test Global Connection"), function () {
				frappe.call({
					method:
						"payments.payment_gateways.doctype.razorpay_settings.razorpay_settings.validate_merchant_credentials",
					// pass a dummy sentinel so the function uses Settings creds
					args: { merchant_name: "__global__" },
					callback(r) {
						// validate_merchant_credentials will fail on __global__ – use inline validation instead
					},
				});
				// Inline: validate global creds directly
				frappe.call({
					method: "frappe.integrations.utils.make_get_request",
					args: {
						url: "https://api.razorpay.com/v1/payments",
						auth: [frm.doc.api_key, frm.doc.api_secret],
					},
					callback(r) {
						if (!r.exc) {
							frappe.msgprint({
								title: __("Connection Successful"),
								message: __("Global Razorpay credentials are valid."),
								indicator: "green",
							});
						}
					},
					error() {
						frappe.msgprint({
							title: __("Connection Failed"),
							message: __("API Key or API Secret appears to be incorrect."),
							indicator: "red",
						});
					},
				});
			});
		}

		frm.add_custom_button(__("Manage Merchants"), function () {
			frappe.set_route("List", "Razorpay Merchant");
		});
	},
});
