// Copyright (c) 2026, Frappe Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on("Payment Gateway Config", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("View Merchant"), function () {
				const gw = frm.doc.preferred_gateway;
				const merchant = frm.doc.merchant_name;
				if (!gw) return frappe.msgprint(__("No gateway selected."));
				const doctype = gw + " Merchant";
				if (merchant) {
					frappe.set_route("Form", doctype, merchant);
				} else {
					frappe.set_route("List", doctype);
				}
			});
		}
	},
});
