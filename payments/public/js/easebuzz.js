// Copyright (c) 2025, Frappe Technologies and contributors
// For license information, please see license.txt

/* 
 * Easebuzz Payment Gateway Integration
 * 
 * Usage with API endpoints for NextJS/React Native:
 * 
 * 1. Initiate Payment:
 *    POST /api/method/payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.initiate_payment
 *    
 * 2. Check Status:
 *    GET /api/method/payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.check_payment_status
 *    
 * 3. Webhook Callback (for mobile apps):
 *    POST /api/method/payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.webhook_callback
 */

frappe.provide("frappe.checkout");

frappe.checkout.easebuzz = class EasebuzzCheckout {
  constructor(opts) {
    Object.assign(this, opts);
    this.base_url = window.location.origin;
  }

  /**
   * Initialize Easebuzz payment
   */
  init() {
    var me = this;
    
    return new Promise(function(resolve, reject) {
      if(me.payment_details) {
        me.initiate_payment()
          .then(function(response) {
            if(response.success) {
              me.open_payment_page(response);
              resolve(response);
            } else {
              reject(response.error || "Payment initiation failed");
            }
          })
          .catch(function(error) {
            reject(error);
          });
      } else {
        reject("Missing payment_details");
      }
    });
  }

  /**
   * Call API to initiate payment
   */
  initiate_payment() {
    var me = this;
    
    return new Promise(function(resolve, reject) {
      frappe.call({
        method: "payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.initiate_payment",
        args: me.payment_details,
        callback: function(r) {
          if(r.message) {
            resolve(r.message);
          } else {
            reject("No response from server");
          }
        },
        error: function(err) {
          reject(err);
        }
      });
    });
  }

  /**
   * Open payment page in new window or iframe
   */
  open_payment_page(response) {
    var me = this;
    
    if(me.use_iframe) {
      // Open in iframe
      me.create_iframe(response.payment_url);
    } else {
      // Redirect to payment page
      window.location.href = response.payment_url;
    }
  }

  /**
   * Create iframe for payment
   */
  create_iframe(payment_url) {
    var me = this;
    
    // Create modal dialog
    var dialog = new frappe.ui.Dialog({
      title: __('Complete Payment'),
      size: 'large',
      static: true,
      fields: [
        {
          fieldtype: 'HTML',
          fieldname: 'payment_iframe'
        }
      ]
    });

    dialog.show();

    // Add iframe
    var iframe_html = `
      <iframe 
        id="easebuzz-payment-frame" 
        src="${payment_url}" 
        style="width: 100%; height: 600px; border: none;"
        frameborder="0">
      </iframe>
    `;

    dialog.fields_dict.payment_iframe.$wrapper.html(iframe_html);

    // Listen for payment completion
    window.addEventListener('message', function(event) {
      if(event.data && event.data.payment_status) {
        dialog.hide();
        if(me.on_success && event.data.payment_status === 'success') {
          me.on_success(event.data);
        } else if(me.on_failure) {
          me.on_failure(event.data);
        }
      }
    });
  }

  /**
   * Check payment status
   */
  check_status(integration_request_name) {
    return new Promise(function(resolve, reject) {
      frappe.call({
        method: "payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings.check_payment_status",
        args: {
          integration_request_name: integration_request_name
        },
        callback: function(r) {
          if(r.message && r.message.success) {
            resolve(r.message);
          } else {
            reject(r.message ? r.message.error : "Failed to check status");
          }
        },
        error: function(err) {
          reject(err);
        }
      });
    });
  }
};

/**
 * Helper function to create Easebuzz payment
 * 
 * @param {Object} payment_details - Payment details
 * @param {Function} on_success - Success callback
 * @param {Function} on_failure - Failure callback
 * @param {Boolean} use_iframe - Whether to use iframe (default: false)
 */
frappe.easebuzz_payment = function(payment_details, on_success, on_failure, use_iframe) {
  var checkout = new frappe.checkout.easebuzz({
    payment_details: payment_details,
    on_success: on_success,
    on_failure: on_failure,
    use_iframe: use_iframe || false
  });

  return checkout.init();
};
