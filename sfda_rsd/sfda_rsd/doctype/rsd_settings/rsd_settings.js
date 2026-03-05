// Copyright (c) 2026, NAFS and contributors
// For license information, please see license.txt

frappe.ui.form.on("RSD Settings", {
	refresh(frm) {
		if (frm.doc.enabled) {
			frm.add_custom_button(__("Test Connection"), function () {
				frappe.call({
					method:
						"sfda_rsd.sfda_rsd.doctype.rsd_settings.rsd_settings.test_rsd_connection",
					freeze: true,
					freeze_message: __("Testing connection to SFDA..."),
					callback: function (r) {
						if (!r.message) {
							frappe.msgprint(__("No response from test."));
							return;
						}
						show_test_results(r.message);
					},
					error: function (r) {
						frappe.msgprint({
							title: __("Connection Test Failed"),
							indicator: "red",
							message: r.message || __("An error occurred while testing the connection."),
						});
					},
				});
			}).addClass("btn-primary");
		}
	},
});

function show_test_results(results) {
	let html = `<div style="padding: 10px;">`;
	html += `<p><strong>Environment:</strong> ${results.environment}</p>`;
	html += `<p><strong>Base URL:</strong> ${results.base_url}</p>`;

	if (results.wsdl_url) {
		html += `<p><strong>WSDL URL:</strong> <code style="font-size: 12px;">${results.wsdl_url}</code></p>`;
	}

	html += `<hr><table class="table table-bordered" style="margin-top: 10px;">`;
	html += `<thead><tr><th>Step</th><th>Status</th><th>Details</th></tr></thead><tbody>`;

	(results.steps || []).forEach(function (step) {
		let badge =
			step.status === "Pass"
				? '<span class="indicator-pill green">Pass</span>'
				: '<span class="indicator-pill red">Fail</span>';
		html += `<tr><td>${step.step}</td><td>${badge}</td><td>${step.message}</td></tr>`;
	});

	html += `</tbody></table></div>`;

	let indicator = results.overall === "Pass" ? "green" : "red";
	let title =
		results.overall === "Pass"
			? __("Connection Test Passed")
			: __("Connection Test Failed");

	frappe.msgprint({
		title: title,
		indicator: indicator,
		message: html,
	});
}
