frappe.ui.form.on('Easebuzz Settings', {
    refresh: function (frm) {
        // Add a custom button to test the API connection
        frm.add_custom_button(__('Test Connection'), function () {
            frappe.call({
                method: 'payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.test_connection',
                callback: function (r) {
                    if (r.message) {
                        frappe.msgprint(__('Connection successful!'));
                    } else {
                        frappe.msgprint(__('Connection failed. Please check your API credentials.'));
                    }
                }
            });
        });
    }
});