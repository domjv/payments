// Copyright (c) 2025, Frappe Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('Easebuzz Settings', {
	refresh: function(frm) {
		// Add test connection button
		frm.add_custom_button(__('Test Connection'), function() {
			test_easebuzz_credentials(frm);
		});
	}
});

function test_easebuzz_credentials(frm) {
	frappe.call({
		method: 'payments.payment_gateways.doctype.easebuzz_settings.easebuzz_utils.test_connection',
		args: {
			merchant_key: frm.doc.merchant_key,
			salt: frm.doc.salt,
			environment: frm.doc.environment
		},
		callback: function(r) {
			if (r.message && r.message.success) {
				frappe.msgprint({
					title: __('Success'),
					message: __('Easebuzz credentials are valid'),
					indicator: 'green'
				});
			} else {
				frappe.msgprint({
					title: __('Error'),
					message: __('Connection test failed: ') + (r.message ? r.message.error : 'Unknown error'),
					indicator: 'red'
				});
			}
		}
	});
}
