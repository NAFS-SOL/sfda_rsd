# sfda_rsd/sfda_rsd/api/rsd_api.py
"""
API endpoints and ERPNext document event handlers for SFDA RSD integration.

Whitelisted methods provide manual control from the desk UI.
Doc event handlers automatically enqueue RSD notifications on submit.

Pharmacy-focused: Accept, PharmacySale, Deactivate, Return, Transfer, Dispatch.
Manufacturer operations (Supply, Import, Export) are available but not auto-triggered.
"""
import frappe
from frappe.utils import now_datetime


# ---------------------------------------------------------------------------
# Helper: Enqueue RSD notification for async processing
# ---------------------------------------------------------------------------

def _enqueue_rsd_notification(service_name, operation, params,
							  reference_doctype=None, reference_name=None):
	"""Create an RSD Notification Queue entry for background processing."""
	settings = frappe.get_single("RSD Settings")
	if not settings.enabled:
		return

	queue_entry = frappe.get_doc({
		"doctype": "RSD Notification Queue",
		"service_name": service_name,
		"operation": operation,
		"parameters": frappe.as_json(params),
		"status": "Pending",
		"retry_count": 0,
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
	})
	queue_entry.insert(ignore_permissions=True)
	frappe.db.commit()


def _is_rsd_tracked(item_code):
	"""Check if an item is flagged for SFDA RSD tracking."""
	return frappe.db.get_value("Item", item_code, "custom_is_rsd_tracked")


def _get_item_rsd_info(item_code):
	"""Get GTIN and serial tracking mode for an item."""
	return frappe.db.get_value(
		"Item", item_code,
		["custom_gtin", "has_serial_no", "has_batch_no"],
		as_dict=True,
	)


def _build_product_entries(item, gtin):
	"""Build SFDA product entries from a doc item.

	Returns list of product dicts for serial items, or a single batch entry.
	If serial_no is present, returns one entry per serial number.
	If only batch_no is present, returns one batch-level entry with quantity.
	"""
	products = []
	if item.serial_no:
		for sn in item.serial_no.strip().split("\n"):
			sn = sn.strip()
			if sn:
				prod = {"GTIN": gtin, "SN": sn}
				if item.batch_no:
					prod["BN"] = item.batch_no
				products.append(prod)
	return products


# ---------------------------------------------------------------------------
# Whitelisted API endpoints (manual operations from desk)
# ---------------------------------------------------------------------------

# -- Pharmacy core operations --

@frappe.whitelist()
def accept_product(gtin, serial_number, sender_gln):
	"""Manually accept a received product."""
	from sfda_rsd.sfda_rsd.connectors.services.accept_service import accept_product as _accept
	return _accept(gtin, serial_number, sender_gln)


@frappe.whitelist()
def accept_by_batch(gtin, batch_number, sender_gln, quantity):
	"""Accept products by batch number."""
	from sfda_rsd.sfda_rsd.connectors.services.accept_service import accept_by_batch as _accept
	return _accept(gtin, batch_number, sender_gln, int(quantity))


@frappe.whitelist()
def accept_dispatch(notification_id):
	"""Accept all units in a dispatch notification."""
	from sfda_rsd.sfda_rsd.connectors.services.accept_service import accept_dispatch as _accept
	return _accept(notification_id)


@frappe.whitelist()
def pharmacy_sale(products, to_gln="0000000000000", prescription_id=None,
				  prescription_date=None):
	"""Record a pharmacy sale."""
	if isinstance(products, str):
		products = frappe.parse_json(products)
	from sfda_rsd.sfda_rsd.connectors.services.pharmacy_sale_service import pharmacy_sale as _sale
	return _sale(products, to_gln, prescription_id, prescription_date)


@frappe.whitelist()
def pharmacy_sale_cancel(products, to_gln="0000000000000", prescription_id=None):
	"""Cancel a pharmacy sale."""
	if isinstance(products, str):
		products = frappe.parse_json(products)
	from sfda_rsd.sfda_rsd.connectors.services.pharmacy_sale_service import pharmacy_sale_cancel as _cancel
	return _cancel(products, to_gln, prescription_id)


@frappe.whitelist()
def deactivate_product(gtin, serial_number, deactivation_reason, explanation=None):
	"""Deactivate a product (damage, recall, etc.)."""
	from sfda_rsd.sfda_rsd.connectors.services.deactivate_service import deactivate_product as _deactivate
	return _deactivate(gtin, serial_number, deactivation_reason, explanation)


@frappe.whitelist()
def deactivate_cancel(gtin, serial_number):
	"""Cancel a deactivation."""
	from sfda_rsd.sfda_rsd.connectors.services.deactivate_service import deactivate_cancel as _cancel
	return _cancel(gtin, serial_number)


@frappe.whitelist()
def return_product(gtin, serial_number, receiver_gln):
	"""Return a product to sender."""
	from sfda_rsd.sfda_rsd.connectors.services.return_service import return_product as _return
	return _return(gtin, serial_number, receiver_gln)


@frappe.whitelist()
def return_by_batch(gtin, batch_number, receiver_gln, quantity):
	"""Return products by batch number."""
	from sfda_rsd.sfda_rsd.connectors.services.return_service import return_by_batch as _return
	return _return(gtin, batch_number, receiver_gln, int(quantity))


@frappe.whitelist()
def transfer_product(gtin, serial_number, receiver_gln):
	"""Transfer between same-type stakeholders (pharmacy-to-pharmacy)."""
	from sfda_rsd.sfda_rsd.connectors.services.transfer_service import transfer_product as _transfer
	return _transfer(gtin, serial_number, receiver_gln)


@frappe.whitelist()
def transfer_by_batch(gtin, batch_number, receiver_gln, quantity):
	"""Transfer products by batch number."""
	from sfda_rsd.sfda_rsd.connectors.services.transfer_service import transfer_by_batch as _transfer
	return _transfer(gtin, batch_number, receiver_gln, int(quantity))


@frappe.whitelist()
def dispatch_product(gtin, serial_number, receiver_gln):
	"""Manually dispatch a product."""
	from sfda_rsd.sfda_rsd.connectors.services.dispatch_service import dispatch_product as _dispatch
	return _dispatch(gtin, serial_number, receiver_gln)


@frappe.whitelist()
def dispatch_by_batch(gtin, batch_number, receiver_gln, quantity):
	"""Dispatch products by batch number."""
	from sfda_rsd.sfda_rsd.connectors.services.dispatch_service import dispatch_by_batch as _dispatch
	return _dispatch(gtin, batch_number, receiver_gln, int(quantity))


# -- Query operations --

@frappe.whitelist()
def check_status(gtin, serial_number):
	"""Query the current status of a drug unit."""
	from sfda_rsd.sfda_rsd.connectors.services.query_service import check_status as _check
	return _check(gtin, serial_number)


@frappe.whitelist()
def get_drug_list():
	"""Fetch the SFDA drug list."""
	from sfda_rsd.sfda_rsd.connectors.services.query_service import get_drug_list as _get
	return _get()


@frappe.whitelist()
def get_stakeholder_list():
	"""Fetch the SFDA stakeholder list."""
	from sfda_rsd.sfda_rsd.connectors.services.query_service import get_stakeholder_list as _get
	return _get()


@frappe.whitelist()
def get_error_codes(error_code=None):
	"""Fetch SFDA error code descriptions."""
	from sfda_rsd.sfda_rsd.connectors.services.query_service import get_error_codes as _get
	return _get(error_code)


@frappe.whitelist()
def retry_failed():
	"""Manually trigger retry of failed notifications."""
	from sfda_rsd.sfda_rsd.connectors.rsd_connector import retry_failed_notifications
	retry_failed_notifications()
	return {"status": "ok", "message": "Retry triggered"}


# ---------------------------------------------------------------------------
# ERPNext Document Event Handlers
# ---------------------------------------------------------------------------

def on_stock_entry_submit(doc, method):
	"""Handle Stock Entry submit -- Material Issue = Deactivation only.

	Manufacture (Supply) is a manufacturer operation and is not auto-triggered.
	"""
	settings = frappe.get_single("RSD Settings")
	if not settings.enabled:
		return

	if doc.purpose != "Material Issue":
		return

	for item in doc.items:
		if not _is_rsd_tracked(item.item_code):
			continue

		info = _get_item_rsd_info(item.item_code)
		if not info or not info.custom_gtin:
			continue

		gtin = info.custom_gtin

		if item.serial_no:
			# Serial-level deactivation
			products = _build_product_entries(item, gtin)
			for prod in products:
				_enqueue_rsd_notification(
					service_name="DeactivationService",
					operation="DeactivationServiceRequest",
					params={
						"DR": "DAMAGED",
						"PRODUCTLIST": {"PRODUCT": [prod]},
					},
					reference_doctype="Stock Entry",
					reference_name=doc.name,
				)


def on_purchase_receipt_submit(doc, method):
	"""Handle Purchase Receipt submit -- Accept incoming drugs from supplier."""
	settings = frappe.get_single("RSD Settings")
	if not settings.enabled:
		return

	supplier_gln = frappe.db.get_value("Supplier", doc.supplier, "custom_gln")
	if not supplier_gln:
		return

	for item in doc.items:
		if not _is_rsd_tracked(item.item_code):
			continue

		info = _get_item_rsd_info(item.item_code)
		if not info or not info.custom_gtin:
			continue

		gtin = info.custom_gtin

		if item.serial_no:
			# Serial-level accept
			products = _build_product_entries(item, gtin)
			_enqueue_rsd_notification(
				service_name="AcceptService",
				operation="AcceptServiceRequest",
				params={
					"FROMGLN": supplier_gln,
					"PRODUCTLIST": {"PRODUCT": products},
				},
				reference_doctype="Purchase Receipt",
				reference_name=doc.name,
			)
		elif item.batch_no and info.has_batch_no:
			# Batch-level accept
			product = {
				"GTIN": gtin,
				"BN": item.batch_no,
				"QUANTITY": int(item.qty),
			}
			_enqueue_rsd_notification(
				service_name="AcceptBatchService",
				operation="AcceptBatchServiceRequest",
				params={
					"FROMGLN": supplier_gln,
					"PRODUCTLIST": {"PRODUCT": [product]},
				},
				reference_doctype="Purchase Receipt",
				reference_name=doc.name,
			)


def on_sales_invoice_submit(doc, method):
	"""Handle Sales Invoice submit -- Pharmacy Sale for retail invoices.

	If customer has no GLN = end consumer -> Pharmacy Sale.
	If customer has GLN = B2B (handled by Delivery Note dispatch).
	Triggered by both standard ERPNext flow and POS sales.
	"""
	settings = frappe.get_single("RSD Settings")
	if not settings.enabled:
		return

	customer_gln = frappe.db.get_value("Customer", doc.customer, "custom_gln")

	# Only pharmacy sale for end consumers (no GLN)
	if customer_gln:
		return

	to_gln = getattr(settings, "pharmacy_sale_togln", None) or "0000000000000"
	products = []

	for item in doc.items:
		if not _is_rsd_tracked(item.item_code):
			continue

		info = _get_item_rsd_info(item.item_code)
		if not info or not info.custom_gtin:
			continue

		gtin = info.custom_gtin

		if item.serial_no:
			for entry in _build_product_entries(item, gtin):
				products.append(entry)

	if products:
		_enqueue_rsd_notification(
			service_name="PharmacySaleService",
			operation="PharmacySaleServiceRequest",
			params={
				"TOGLN": to_gln,
				"PRODUCTLIST": {"PRODUCT": products},
			},
			reference_doctype="Sales Invoice",
			reference_name=doc.name,
		)


def on_delivery_note_submit(doc, method):
	"""Handle Delivery Note submit -- Dispatch products to another stakeholder.

	Only dispatches to customers with a GLN (B2B).
	"""
	settings = frappe.get_single("RSD Settings")
	if not settings.enabled:
		return

	customer_gln = frappe.db.get_value("Customer", doc.customer, "custom_gln")
	if not customer_gln:
		return

	for item in doc.items:
		if not _is_rsd_tracked(item.item_code):
			continue

		info = _get_item_rsd_info(item.item_code)
		if not info or not info.custom_gtin:
			continue

		gtin = info.custom_gtin

		if item.serial_no:
			# Serial-level dispatch
			products = _build_product_entries(item, gtin)
			_enqueue_rsd_notification(
				service_name="DispatchService",
				operation="DispatchServiceRequest",
				params={
					"TOGLN": customer_gln,
					"PRODUCTLIST": {"PRODUCT": products},
				},
				reference_doctype="Delivery Note",
				reference_name=doc.name,
			)
		elif item.batch_no and info.has_batch_no:
			# Batch-level dispatch
			product = {
				"GTIN": gtin,
				"BN": item.batch_no,
				"QUANTITY": int(item.qty),
			}
			_enqueue_rsd_notification(
				service_name="DispatchBatchService",
				operation="DispatchBatchServiceRequest",
				params={
					"TOGLN": customer_gln,
					"PRODUCTLIST": {"PRODUCT": [product]},
				},
				reference_doctype="Delivery Note",
				reference_name=doc.name,
			)
