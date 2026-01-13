// Copyright (c) 2025, Frappe Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('Cashfree Settings', {
	refresh: function(frm) {
		// Show webhook URL prominently
		if (frm.doc.webhook_url) {
			frm.dashboard.add_comment(
				__('Configure this webhook URL in your Cashfree Dashboard: {0}', [frm.doc.webhook_url]),
				'blue',
				true
			);
		}
		
		// Add button to test credentials
		if (!frm.is_new() && frm.doc.client_id && frm.doc.client_secret) {
			frm.add_custom_button(__('Test Connection'), function() {
				frappe.call({
					method: 'payments.payment_gateways.doctype.cashfree_settings.cashfree_settings.test_cashfree_connection',
					args: {
						settings_name: frm.doc.name
					},
					callback: function(r) {
						if (r.message && r.message.success) {
							frappe.show_alert({
								message: __('Cashfree connection successful!'),
								indicator: 'green'
							}, 5);
						} else {
							const detail = (r.message && r.message.message) ? r.message.message : __('Check your credentials.');
							frappe.show_alert({
								message: __('Cashfree connection failed. {0}', [detail]),
								indicator: 'red'
							}, 5);
						}
					}
				});
			});
		}
	},
	
	is_default: function(frm) {
		if (frm.doc.is_default) {
			frappe.show_alert({
				message: __('This will be set as the default Cashfree account'),
				indicator: 'blue'
			}, 3);
		}
	},
	
	environment: function(frm) {
		if (frm.doc.environment === 'Production') {
			frappe.show_alert({
				message: __('You are switching to Production mode. Make sure to use production credentials.'),
				indicator: 'orange'
			}, 5);
		}
	}
});
