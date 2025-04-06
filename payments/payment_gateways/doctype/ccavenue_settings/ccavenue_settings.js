// Copyright (c) 2024, Frappe Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on("CCAvenue Settings", {
    refresh: function (frm) {
      frm.add_custom_button(__("Clear"), function () {
        frm.call({
          doc: frm.doc,
          method: "clear",
          callback: function (r) {
            frm.refresh();
          },
        });
      });
      
      frm.add_custom_button(__("Test Connection"), function () {
        frappe.call({
          method: "payments.payment_gateways.doctype.ccavenue_settings.ccavenue_utils.test_connection",
          args: {
            merchant_id: frm.doc.merchant_id,
            access_code: frm.doc.access_code,
            encryption_key: frm.doc.encryption_key,
            environment: frm.doc.environment
          },
          callback: function (r) {
            if (r.message && r.message.success) {
              frappe.msgprint(__('Connection Successful'));
            } else {
              frappe.msgprint(__('Connection Failed: ') + r.message.error);
            }
          }
        });
      });
    },
  });