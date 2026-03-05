app_name = "sfda_rsd"
app_title = "SFDA RSD"
app_publisher = "NAFS"
app_description = "SFDA RSD Drug Track & Trace (DTTS) Integration for ERPNext"
app_email = "nafs@zidwell.com.sa"
app_license = "mit"

required_apps = ["erpnext"]

after_migrate = ["sfda_rsd.setup.after_migrate"]

# Document Events
# ---------------
# Pharmacy-focused doc events:
# - Stock Entry (Material Issue only) -> Deactivation
# - Purchase Receipt -> Accept (receiving from distributor)
# - Sales Invoice -> Pharmacy Sale (retail to consumer, also triggered by POS)
# - Delivery Note -> Dispatch (B2B to another pharmacy/entity)
#
# NOTE: Supply/Import/Export are manufacturer/warehouse operations and are
# not triggered automatically. They can be called manually via API if needed.

doc_events = {
	"Stock Entry": {
		"on_submit": "sfda_rsd.sfda_rsd.api.rsd_api.on_stock_entry_submit",
	},
	"Purchase Receipt": {
		"on_submit": "sfda_rsd.sfda_rsd.api.rsd_api.on_purchase_receipt_submit",
	},
	"Sales Invoice": {
		"on_submit": "sfda_rsd.sfda_rsd.api.rsd_api.on_sales_invoice_submit",
	},
	"Delivery Note": {
		"on_submit": "sfda_rsd.sfda_rsd.api.rsd_api.on_delivery_note_submit",
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"cron": {
		"*/15 * * * *": [
			"sfda_rsd.tasks.retry_failed_notifications",
		],
	},
	"daily": [
		"sfda_rsd.tasks.sync_drug_list",
	],
}
