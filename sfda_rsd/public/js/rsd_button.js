// Shared RSD button logic for Purchase Receipt and Sales Invoice
function addRsdButton(frm) {
	if (frm.doc.docstatus !== 1) return;

	var status = frm.doc.custom_rsd_status;
	// Show button if: Failed, Not Applicable, or no status set
	if (status === "Failed" || status === "Not Applicable" || !status) {
		frm.add_custom_button(__("Send to RSD"), function () {
			frappe.call({
				method: "sfda_rsd.sfda_rsd.api.rsd_api.manual_rsd_trigger",
				args: { doctype: frm.doctype, docname: frm.docname },
				freeze: true,
				freeze_message: __("Sending to SFDA RSD..."),
				callback: function (r) {
					if (r.message && r.message.status === "ok") {
						frappe.show_alert({ message: __("RSD notification sent successfully"), indicator: "green" });
						frm.reload_doc();
					} else if (r.message && r.message.status === "error") {
						frappe.msgprint({
							title: __("SFDA RSD Error"),
							message: r.message.message || __("SFDA returned an error"),
							indicator: "red",
						});
						frm.reload_doc();
					}
				},
			});
		}, __("SFDA RSD"));
	}

	// Show status indicator
	if (status === "Pending") {
		frm.dashboard.set_headline_alert(
			'<span class="indicator whitespace-nowrap orange">RSD: Pending</span>'
		);
	} else if (status === "Sent") {
		frm.dashboard.set_headline_alert(
			'<span class="indicator whitespace-nowrap green">RSD: Sent</span>'
		);
	} else if (status === "Failed") {
		frm.dashboard.set_headline_alert(
			'<span class="indicator whitespace-nowrap red">RSD: Failed</span>'
		);
	} else if (status === "Not Applicable") {
		frm.dashboard.set_headline_alert(
			'<span class="indicator whitespace-nowrap gray">RSD: Not Applicable</span>'
		);
	}
}

// Register for all RSD-related doctypes
frappe.ui.form.on("Purchase Receipt", { refresh: addRsdButton });
frappe.ui.form.on("Sales Invoice", { refresh: addRsdButton });
frappe.ui.form.on("Delivery Note", { refresh: addRsdButton });
frappe.ui.form.on("Stock Entry", { refresh: addRsdButton });
