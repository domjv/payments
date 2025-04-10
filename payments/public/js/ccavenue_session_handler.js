frappe.provide("payments.ccavenue");

payments.ccavenue.checkAndRestoreSession = function() {
    // Check if we're coming back from a payment
    const urlParams = new URLSearchParams(window.location.search);
    const isPaymentReturn = urlParams.has("doctype") && urlParams.has("docname");
    
    if (isPaymentReturn && frappe.session.user === "Guest") {
        // Try to restore session
        frappe.call({
            method: "payments.payment_gateways.doctype.ccavenue_settings.ccavenue_settings.restore_user_session",
            args: {
                "reference_doctype": urlParams.get("doctype"),
                "reference_docname": urlParams.get("docname")
            },
            callback: function(r) {
                if (r.message && r.message.success) {
                    // Reload to refresh the session
                    window.location.reload();
                }
            }
        });
    }
};

$(document).ready(function() {
    payments.ccavenue.checkAndRestoreSession();
});