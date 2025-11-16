// Cashfree Checkout JavaScript

frappe.ready(function() {
	// Get data from template
	var payment_session_id = "{{ payment_session_id }}";
	var cf_order_id = "{{ cf_order_id }}";
	var order_id = "{{ order_id }}";
	var token = "{{ token }}";
	var reference_doctype = "{{ reference_doctype }}";
	var reference_docname = "{{ reference_docname }}";
	var environment = "{{ environment }}";
	
	// Check if we have required data
	if (!payment_session_id || !order_id) {
		frappe.msgprint({
			title: __("Error"),
			message: __("Missing payment session information. Please try again."),
			indicator: "red"
		});
		return;
	}
	
	// Hide loading, show processing
	$('.cashfree-loading').addClass('hidden');
	$('.cashfree-processing').removeClass('hidden');
	
	// Initialize Cashfree SDK
	var cashfree;
	
	// Determine environment
	var cashfreeEnv = environment.toLowerCase() === 'production' ? 'production' : 'sandbox';
	
	// Initialize Cashfree
	cashfree = Cashfree({
		mode: cashfreeEnv
	});
	
	// Checkout options
	var checkoutOptions = {
		paymentSessionId: payment_session_id,
		redirectTarget: "_self"
	};
	
	// Start checkout
	cashfree.checkout(checkoutOptions).then(function(result) {
		if (result.error) {
			// Payment failed
			console.error("Payment Error:", result.error);
			$('.cashfree-processing').addClass('hidden');
			
			frappe.msgprint({
				title: __("Payment Failed"),
				message: result.error.message || __("Payment could not be processed. Please try again."),
				indicator: "red"
			});
			
			// Redirect to payment failed page
			setTimeout(function() {
				window.location.href = "/payment-failed";
			}, 3000);
		} 
		else if (result.redirect) {
			// Payment requires redirect (shouldn't happen with redirectTarget: "_self")
			console.log("Redirect required:", result.redirectUrl);
		}
	}).catch(function(error) {
		// Error in checkout
		console.error("Checkout Error:", error);
		$('.cashfree-processing').addClass('hidden');
		
		frappe.msgprint({
			title: __("Error"),
			message: __("An error occurred during checkout. Please try again."),
			indicator: "red"
		});
		
		// Redirect to payment failed page
		setTimeout(function() {
			window.location.href = "/payment-failed";
		}, 3000);
	});
	
	// Note: Cashfree's checkout handles the payment flow and redirects automatically
	// based on the return_url configured in the order
	// We don't need to manually call make_payment as the webhook will handle status updates
});
