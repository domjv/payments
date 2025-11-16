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
							frappe.show_alert({
								message: __('Cashfree connection failed. Check your credentials.'),
								indicator: 'red'
							}, 5);
						}
					}
				});
			});
		}
		
		// Add button to create test payment link
		if (!frm.is_new()) {
			frm.add_custom_button(__('Create Test Payment Link'), function() {
				frappe.prompt([
					{
						fieldname: 'amount',
						fieldtype: 'Currency',
						label: __('Amount'),
						reqd: 1,
						default: 100
					},
					{
						fieldname: 'customer_email',
						fieldtype: 'Data',
						label: __('Customer Email'),
						reqd: 1
					},
					{
						fieldname: 'customer_name',
						fieldtype: 'Data',
						label: __('Customer Name'),
						reqd: 1
					},
					{
						fieldname: 'customer_phone',
						fieldtype: 'Data',
						label: __('Customer Phone'),
						reqd: 1,
						default: '9999999999'
					},
					{
						fieldname: 'description',
						fieldtype: 'Data',
						label: __('Description'),
						reqd: 1,
						default: 'Test Payment'
					}
				], function(values) {
					frappe.call({
						method: 'payments.payment_gateways.doctype.cashfree_settings.cashfree_settings.create_test_payment_link',
						args: {
							settings_name: frm.doc.name,
							amount: values.amount,
							customer_email: values.customer_email,
							customer_name: values.customer_name,
							customer_phone: values.customer_phone,
							description: values.description
						},
						callback: function(r) {
							if (r.message && r.message.link_url) {
								frappe.msgprint({
									title: __('Payment Link Created'),
									message: __('Payment link: <a href="{0}" target="_blank">{0}</a>', [r.message.link_url]),
									indicator: 'green'
								});
							}
						}
					});
				}, __('Create Test Payment Link'));
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
