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
# Branch resolution helpers
# ---------------------------------------------------------------------------

def _resolve_branch(doc):
	"""Resolve the branch for a transactional doc.

	Parent `branch` field for Purchase Receipt / Sales Invoice / Delivery Note.
	First item row's `branch` for Stock Entry (no parent branch field).
	Returns branch name (str) or None.
	"""
	if doc.doctype in ("Purchase Receipt", "Sales Invoice", "Delivery Note"):
		return doc.get("branch")
	if doc.doctype == "Stock Entry":
		for item in (doc.get("items") or []):
			b = item.get("branch")
			if b:
				return b
	return None


def _get_branch_settings(branch):
	"""Return the enabled RSD Settings doc for a branch, or None."""
	if not branch:
		return None
	name = frappe.db.get_value("RSD Settings", {"branch": branch, "enabled": 1}, "name")
	return frappe.get_doc("RSD Settings", name) if name else None


def _skip_rsd(doc, reason):
	"""Mark a document as Not Applicable for RSD and log the reason once.

	Called when a submitted doc has no branch, or its branch has no RSD
	Settings configured, or its settings record has enabled=0.
	"""
	try:
		frappe.db.set_value(doc.doctype, doc.name, {
			"custom_rsd_status": "Not Applicable",
		}, update_modified=False)
	except Exception:
		pass
	frappe.logger().info(
		f"RSD: skipped {doc.doctype} {doc.name} — {reason}"
	)


# ---------------------------------------------------------------------------
# Helper: Enqueue RSD notification for async processing
# ---------------------------------------------------------------------------

def _enqueue_rsd_notification(service_name, operation, params, branch,
							  reference_doctype=None, reference_name=None):
	"""Create an RSD Notification Queue entry for background processing.

	Requires branch; resolves RSD Settings for that branch. If no enabled
	config exists for the branch, silently returns None — caller should have
	already marked the source doc Not Applicable via _skip_rsd.
	"""
	settings = _get_branch_settings(branch)
	if not settings:
		return None

	queue_entry = frappe.get_doc({
		"doctype": "RSD Notification Queue",
		"branch": branch,
		"service_name": service_name,
		"operation": operation,
		"parameters": frappe.as_json(params),
		"status": "Pending",
		"retry_count": 0,
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
	})
	queue_entry.insert(ignore_permissions=True)

	# Update RSD status on the source document
	if reference_doctype and reference_name:
		try:
			frappe.db.set_value(reference_doctype, reference_name, {
				"custom_rsd_status": "Pending",
				"custom_rsd_notification": queue_entry.name,
			}, update_modified=False)
		except Exception:
			pass  # field may not exist on all doctypes

	frappe.db.commit()
	return queue_entry.name


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

	Returns list of product dicts for serial items.
	Always includes BN and XD when batch_no is available.
	"""
	products = []
	if item.serial_no:
		for sn in item.serial_no.strip().split("\n"):
			sn = sn.strip()
			if sn:
				prod = {"GTIN": gtin, "SN": sn}
				if item.batch_no:
					prod["BN"] = item.batch_no
					expiry = frappe.db.get_value("Batch", item.batch_no, "expiry_date")
					if expiry:
						prod["XD"] = str(expiry)
				products.append(prod)
	return products


def _build_serial_product(gtin, sn, batch_no=None):
	"""Build a single serial-level product dict with BN and XD."""
	prod = {"GTIN": gtin, "SN": sn}
	if batch_no:
		prod["BN"] = batch_no
		expiry = frappe.db.get_value("Batch", batch_no, "expiry_date")
		if expiry:
			prod["XD"] = str(expiry)
	return prod


def _get_item_batch_no(item):
	"""Get batch_no from item, falling back to Serial and Batch Bundle.

	ERPNext clears batch_no on cancellation, but the linked
	Serial and Batch Bundle still has the original batch info.
	"""
	if item.batch_no:
		return item.batch_no

	# Fallback: look up from Serial and Batch Bundle via voucher_detail_no
	bundle_name = frappe.db.get_value(
		"Serial and Batch Bundle",
		{"voucher_detail_no": item.name, "item_code": item.item_code},
		"name",
	)
	if bundle_name:
		batch = frappe.db.get_value(
			"Serial and Batch Entry",
			{"parent": bundle_name},
			"batch_no",
		)
		if batch:
			return batch

	return None


# ---------------------------------------------------------------------------
# Whitelisted API endpoints (manual operations from desk)
# ---------------------------------------------------------------------------

# -- Pharmacy core operations --

@frappe.whitelist()
def accept_product(branch, gtin, serial_number, sender_gln):
	"""Manually accept a received product."""
	from sfda_rsd.connectors.services.accept_service import accept_product as _accept
	return _accept(branch, gtin, serial_number, sender_gln)


@frappe.whitelist()
def accept_by_batch(branch, gtin, batch_number, sender_gln, quantity):
	"""Accept products by batch number."""
	from sfda_rsd.connectors.services.accept_service import accept_by_batch as _accept
	return _accept(branch, gtin, batch_number, sender_gln, int(quantity))


@frappe.whitelist()
def accept_dispatch(branch, notification_id):
	"""Accept all units in a dispatch notification."""
	from sfda_rsd.connectors.services.accept_service import accept_dispatch as _accept
	return _accept(branch, notification_id)


@frappe.whitelist()
def pharmacy_sale(branch, products, to_gln="0000000000000", prescription_id=None,
				  prescription_date=None):
	"""Record a pharmacy sale."""
	if isinstance(products, str):
		products = frappe.parse_json(products)
	from sfda_rsd.connectors.services.pharmacy_sale_service import pharmacy_sale as _sale
	return _sale(branch, products, to_gln, prescription_id, prescription_date)


@frappe.whitelist()
def pharmacy_sale_cancel(branch, products, to_gln="0000000000000", prescription_id=None):
	"""Cancel a pharmacy sale."""
	if isinstance(products, str):
		products = frappe.parse_json(products)
	from sfda_rsd.connectors.services.pharmacy_sale_service import pharmacy_sale_cancel as _cancel
	return _cancel(branch, products, to_gln, prescription_id)


@frappe.whitelist()
def deactivate_product(branch, gtin, serial_number, deactivation_reason, explanation=None):
	"""Deactivate a product (damage, recall, etc.)."""
	from sfda_rsd.connectors.services.deactivate_service import deactivate_product as _deactivate
	return _deactivate(branch, gtin, serial_number, deactivation_reason, explanation)


@frappe.whitelist()
def deactivate_cancel(branch, gtin, serial_number):
	"""Cancel a deactivation."""
	from sfda_rsd.connectors.services.deactivate_service import deactivate_cancel as _cancel
	return _cancel(branch, gtin, serial_number)


@frappe.whitelist()
def return_product(branch, gtin, serial_number, receiver_gln):
	"""Return a product to sender."""
	from sfda_rsd.connectors.services.return_service import return_product as _return
	return _return(branch, gtin, serial_number, receiver_gln)


@frappe.whitelist()
def return_by_batch(branch, gtin, batch_number, receiver_gln, quantity):
	"""Return products by batch number."""
	from sfda_rsd.connectors.services.return_service import return_by_batch as _return
	return _return(branch, gtin, batch_number, receiver_gln, int(quantity))


@frappe.whitelist()
def transfer_product(branch, gtin, serial_number, receiver_gln):
	"""Transfer between same-type stakeholders (pharmacy-to-pharmacy)."""
	from sfda_rsd.connectors.services.transfer_service import transfer_product as _transfer
	return _transfer(branch, gtin, serial_number, receiver_gln)


@frappe.whitelist()
def transfer_by_batch(branch, gtin, batch_number, receiver_gln, quantity):
	"""Transfer products by batch number."""
	from sfda_rsd.connectors.services.transfer_service import transfer_by_batch as _transfer
	return _transfer(branch, gtin, batch_number, receiver_gln, int(quantity))


@frappe.whitelist()
def dispatch_product(branch, gtin, serial_number, receiver_gln):
	"""Manually dispatch a product."""
	from sfda_rsd.connectors.services.dispatch_service import dispatch_product as _dispatch
	return _dispatch(branch, gtin, serial_number, receiver_gln)


@frappe.whitelist()
def dispatch_by_batch(branch, gtin, batch_number, receiver_gln, quantity):
	"""Dispatch products by batch number."""
	from sfda_rsd.connectors.services.dispatch_service import dispatch_by_batch as _dispatch
	return _dispatch(branch, gtin, batch_number, receiver_gln, int(quantity))


# -- Query operations --

@frappe.whitelist()
def check_status(branch, gtin, serial_number):
	"""Query the current status of a drug unit."""
	from sfda_rsd.connectors.services.query_service import check_status as _check
	return _check(branch, gtin, serial_number)


@frappe.whitelist()
def get_drug_list(branch, drug_status="-1"):
	"""Fetch the SFDA drug list. drug_status: "-1"=ALL, "0"=PASSIVE, "1"=ACTIVE."""
	from sfda_rsd.connectors.services.query_service import get_drug_list as _get
	return _get(branch=branch, drug_status=drug_status)


@frappe.whitelist()
def debug_wsdl_schema(branch, service_name="DrugListService"):
	"""Introspect a service's WSDL and return its operations and input types.

	Diagnostic only — reveals required elements and enum values for any
	SFDA service. Scoped to a specific branch's credentials.
	"""
	from sfda_rsd.connectors.rsd_connector import RSDConnector

	connector = RSDConnector(branch=branch)
	client = connector._get_client(service_name)

	result = {"service": service_name, "operations": {}}
	try:
		for op_name, op in client.service._binding._operations.items():
			entry = {}
			try:
				entry["input"] = str(op.input.signature(schema=client.wsdl.types))
			except Exception as e:
				entry["input_error"] = str(e)
			try:
				entry["output"] = str(op.output.signature(schema=client.wsdl.types))
			except Exception as e:
				entry["output_error"] = str(e)
			result["operations"][op_name] = entry
	except Exception as e:
		result["error"] = str(e)

	types_dump = []
	try:
		for t in client.wsdl.types.types:
			try:
				qn = getattr(t, "qname", None)
				if qn is None:
					continue
				sig = str(t.signature(schema=client.wsdl.types)) if hasattr(t, "signature") else str(t)
				types_dump.append({"name": str(qn), "signature": sig})
			except Exception:
				continue
		result["types"] = types_dump
	except Exception as e:
		result["types_error"] = str(e)

	return result


@frappe.whitelist()
def enqueue_sfda_drug_sync(branch, drug_status="-1"):
	"""Queue a background job to sync the SFDA drug list for a branch.

	The worker fetches the SFDA catalog using the branch's credentials,
	cross-references every local Item by custom_gtin, writes an xlsx to the
	File store, and publishes a realtime event when the file is ready.
	"""
	if not branch:
		frappe.throw("Branch is required")
	if not frappe.has_permission("Item", "read"):
		frappe.throw("You don't have permission to read Items")
	# Fail fast if the branch has no enabled settings
	if not _get_branch_settings(branch):
		frappe.throw(f"No enabled RSD Settings for branch '{branch}'")

	frappe.enqueue(
		"sfda_rsd.sfda_rsd.api.rsd_api._run_sfda_drug_sync",
		queue="long",
		timeout=1500,
		user=frappe.session.user,
		branch=branch,
		drug_status=str(drug_status),
	)
	return {"status": "queued"}


def _parse_drug_list_response(response):
	"""Parse SFDA DrugList SOAP response into a {gtin: drug_name} dict.

	The DrugListService response schema is not documented here, so walk the
	zeep-serialized object looking for any node containing a GTIN plus a
	name-like sibling. Falls back to re-parsing the raw XML from the latest
	RSD Transaction Log if the zeep walk yields nothing.
	"""
	from zeep.helpers import serialize_object

	NAME_KEYS = {"DRUGNAME", "PRODUCTNAME", "NAME", "TRADENAME", "PRODUCTDESC"}
	drugs_map = {}

	def walk(node):
		if isinstance(node, dict):
			gtin = node.get("GTIN") or node.get("gtin")
			if gtin:
				name = ""
				for key, val in node.items():
					if str(key).upper() in NAME_KEYS and val is not None:
						name = str(val)
						break
				drugs_map[str(gtin).strip()] = name
				return
			for val in node.values():
				walk(val)
		elif isinstance(node, (list, tuple)):
			for item in node:
				walk(item)

	try:
		data = serialize_object(response) if response is not None else None
		walk(data)
	except Exception as e:
		frappe.log_error(f"Drug list zeep parse failed: {e}", "SFDA Drug Sync")

	if not drugs_map:
		try:
			from lxml import etree
			log = frappe.get_all(
				"RSD Transaction Log",
				filters={"service_name": "DrugListService"},
				fields=["response_xml"],
				order_by="creation desc",
				limit=1,
			)
			if log and log[0].response_xml:
				root = etree.fromstring(log[0].response_xml.encode("utf-8"))
				for drug in root.findall(".//{*}DRUG"):
					gtin_text = drug.findtext("{*}GTIN") or drug.findtext("GTIN")
					if not gtin_text:
						continue
					name = ""
					for child in drug:
						tag = etree.QName(child).localname.upper()
						if tag in NAME_KEYS and child.text:
							name = child.text.strip()
							break
					drugs_map[gtin_text.strip()] = name
		except Exception as e:
			frappe.log_error(f"Drug list XML fallback parse failed: {e}", "SFDA Drug Sync")

	return drugs_map


def _run_sfda_drug_sync(user, branch, drug_status="-1"):
	"""Background worker: fetch SFDA drug list for a branch, build Excel, attach as File."""
	from frappe.utils.xlsxutils import make_xlsx
	from sfda_rsd.connectors.services.query_service import get_drug_list as _get_drug_list

	try:
		response = _get_drug_list(branch=branch, drug_status=drug_status)
		sfda_map = _parse_drug_list_response(response)

		items = frappe.get_all(
			"Item",
			filters={"disabled": 0},
			fields=["item_code", "item_name", "custom_gtin", "custom_is_rsd_tracked"],
			order_by="item_code asc",
		)

		rows = [["Item Code", "Item Name", "GTIN", "Found in SFDA", "SFDA Drug Name", "Currently Tracked"]]
		matched = 0
		for it in items:
			gtin = (it.get("custom_gtin") or "").strip()
			if not gtin:
				found, sfda_name = "No GTIN", ""
			elif gtin in sfda_map:
				found, sfda_name = "Yes", sfda_map[gtin]
				matched += 1
			else:
				found, sfda_name = "No", ""
			rows.append([
				it.get("item_code") or "",
				it.get("item_name") or "",
				gtin,
				found,
				sfda_name,
				"Yes" if it.get("custom_is_rsd_tracked") else "No",
			])

		xlsx = make_xlsx(rows, "SFDA Drug Sync")

		ts = now_datetime().strftime("%Y%m%d_%H%M%S")
		file_doc = frappe.new_doc("File")
		file_doc.file_name = f"sfda_drug_sync_{ts}.xlsx"
		file_doc.content = xlsx.getvalue()
		file_doc.is_private = 1
		file_doc.save(ignore_permissions=True)
		frappe.db.commit()

		frappe.publish_realtime(
			"sfda_drug_sync_ready",
			{
				"branch": branch,
				"file_url": file_doc.file_url,
				"file_name": file_doc.file_name,
				"matched": matched,
				"total": len(items),
				"sfda_count": len(sfda_map),
			},
			user=user,
		)
	except Exception as e:
		frappe.log_error(
			message=f"SFDA Drug Sync failed: {e}\n\n{frappe.get_traceback()}",
			title="SFDA Drug Sync Error",
		)
		frappe.publish_realtime(
			"sfda_drug_sync_failed",
			{"error": str(e)[:500]},
			user=user,
		)


@frappe.whitelist()
def get_stakeholder_list(branch):
	"""Fetch the SFDA stakeholder list for a branch."""
	from sfda_rsd.connectors.services.query_service import get_stakeholder_list as _get
	return _get(branch)


@frappe.whitelist()
def get_error_codes(branch, error_code=None):
	"""Fetch SFDA error code descriptions for a branch."""
	from sfda_rsd.connectors.services.query_service import get_error_codes as _get
	return _get(branch, error_code)


@frappe.whitelist()
def retry_failed():
	"""Manually trigger retry of failed notifications."""
	from sfda_rsd.connectors.rsd_connector import retry_failed_notifications
	retry_failed_notifications()
	return {"status": "ok", "message": "Retry triggered"}


@frappe.whitelist()
def manual_rsd_trigger(doctype, docname):
	"""Manually send RSD notification immediately (not queued).

	Builds the same params as the on_submit handler, then calls the
	SOAP service directly via RSDConnector (scoped to the doc's branch)
	and returns the result.
	"""
	if doctype not in ("Purchase Receipt", "Sales Invoice", "Delivery Note", "Stock Entry"):
		frappe.throw("Invalid doctype for RSD trigger")

	doc = frappe.get_doc(doctype, docname)
	if doc.docstatus != 1:
		frappe.throw("Document must be submitted")

	branch = _resolve_branch(doc)
	if not branch:
		frappe.throw(f"Cannot resolve branch for {doctype} {docname}")

	settings = _get_branch_settings(branch)
	if not settings:
		frappe.throw(f"No enabled RSD Settings for branch '{branch}'")

	from sfda_rsd.connectors.rsd_connector import RSDConnector
	connector = RSDConnector(branch=branch)
	results = []

	if doctype == "Purchase Receipt":
		supplier_gln = frappe.db.get_value("Supplier", doc.supplier, "custom_gln")
		if not supplier_gln:
			frappe.throw("Supplier has no GLN set")

		is_return = doc.get("is_return") or False

		for item in doc.items:
			if not _is_rsd_tracked(item.item_code):
				continue
			info = _get_item_rsd_info(item.item_code)
			if not info or not info.custom_gtin:
				continue

			gtin = info.custom_gtin
			qty = abs(int(item.qty))

			if is_return:
				# Purchase Return → Return to supplier
				if item.serial_no:
					products = _build_product_entries(item, gtin)
					resp = connector.call_service(
						"ReturnService", "ReturnServiceRequest",
						{"TOGLN": supplier_gln, "PRODUCTLIST": {"PRODUCT": products}},
					)
					results.append({"service": "ReturnService", "response": str(resp)})
				elif item.batch_no and info.has_batch_no:
					product = {"GTIN": gtin, "BN": item.batch_no, "QUANTITY": qty}
					expiry = frappe.db.get_value("Batch", item.batch_no, "expiry_date")
					if expiry:
						product["XD"] = str(expiry)
					resp = connector.call_service(
						"ReturnBatchService", "ReturnBatchServiceRequest",
						{"TOGLN": supplier_gln, "PRODUCTLIST": {"PRODUCT": [product]}},
					)
					results.append({"service": "ReturnBatchService", "response": str(resp)})
			else:
				# Normal receipt → Accept
				if item.serial_no:
					products = _build_product_entries(item, gtin)
					resp = connector.call_service(
						"AcceptService", "AcceptServiceRequest",
						{"FROMGLN": supplier_gln, "PRODUCTLIST": {"PRODUCT": products}},
					)
					results.append({"service": "AcceptService", "response": str(resp)})
				elif item.batch_no and info.has_batch_no:
					product = {"GTIN": gtin, "BN": item.batch_no, "QUANTITY": qty}
					expiry = frappe.db.get_value("Batch", item.batch_no, "expiry_date")
					if expiry:
						product["XD"] = str(expiry)
					resp = connector.call_service(
						"AcceptBatchService", "AcceptBatchServiceRequest",
						{"FROMGLN": supplier_gln, "PRODUCTLIST": {"PRODUCT": [product]}},
					)
					results.append({"service": "AcceptBatchService", "response": str(resp)})

	elif doctype == "Sales Invoice":
		customer_gln = frappe.db.get_value("Customer", doc.customer, "custom_gln")
		is_consumer = not customer_gln or customer_gln == "0000000000000"
		is_return = doc.get("is_return") or False

		products = []
		for item in doc.items:
			if not _is_rsd_tracked(item.item_code):
				continue
			info = _get_item_rsd_info(item.item_code)
			if not info or not info.custom_gtin:
				continue
			gtin = info.custom_gtin
			batch_no = item.batch_no
			if not batch_no and is_return and doc.get("return_against"):
				batch_no = frappe.db.get_value(
					"Sales Invoice Item",
					{"parent": doc.return_against, "item_code": item.item_code},
					"batch_no",
				)
			serial_data = item.serial_no or getattr(item, "custom_rsd_serial_no", None) or ""
			for sn in serial_data.strip().split("\n"):
				sn = sn.strip()
				if sn:
					prod = _build_serial_product(gtin, sn, batch_no)
					products.append(prod)

		if products:
			if is_consumer:
				# Consumer → PharmacySale / PharmacySaleCancel
				to_gln = getattr(settings, "pharmacy_sale_togln", None) or "0000000000000"
				if is_return:
					original_invoice = doc.get("return_against") or doc.name
					resp = connector.call_service(
						"PharmacySaleCancelService", "PharmacySaleCancelServiceRequest",
						{"TOGLN": to_gln, "PRODUCTLIST": {"PRODUCT": products}, "PRESCRIPTIONID": original_invoice},
					)
					results.append({"service": "PharmacySaleCancelService", "response": str(resp)})
				else:
					resp = connector.call_service(
						"PharmacySaleService", "PharmacySaleServiceRequest",
						{"TOGLN": to_gln, "PRODUCTLIST": {"PRODUCT": products}, "PRESCRIPTIONID": doc.name, "PRESCRIPTIONDATE": str(doc.posting_date)},
					)
					results.append({"service": "PharmacySaleService", "response": str(resp)})
			else:
				# B2B → Transfer / TransferCancel
				if is_return:
					resp = connector.call_service(
						"TransferCancelService", "TransferCancelServiceRequest",
						{"TOGLN": customer_gln, "PRODUCTLIST": {"PRODUCT": products}},
					)
					results.append({"service": "TransferCancelService", "response": str(resp)})
				else:
					resp = connector.call_service(
						"TransferService", "TransferServiceRequest",
						{"TOGLN": customer_gln, "PRODUCTLIST": {"PRODUCT": products}},
					)
					results.append({"service": "TransferService", "response": str(resp)})

	elif doctype == "Delivery Note":
		customer_gln = frappe.db.get_value("Customer", doc.customer, "custom_gln")
		if not customer_gln:
			frappe.throw("Customer has no GLN set — Transfer requires B2B customer")

		is_return = doc.get("is_return") or False

		for item in doc.items:
			if not _is_rsd_tracked(item.item_code):
				continue
			info = _get_item_rsd_info(item.item_code)
			if not info or not info.custom_gtin:
				continue

			gtin = info.custom_gtin
			qty = abs(int(item.qty))

			if is_return:
				# DN Return → TransferCancel
				if item.serial_no:
					products = _build_product_entries(item, gtin)
					resp = connector.call_service(
						"TransferCancelService", "TransferCancelServiceRequest",
						{"TOGLN": customer_gln, "PRODUCTLIST": {"PRODUCT": products}},
					)
					results.append({"service": "TransferCancelService", "response": str(resp)})
				elif item.batch_no and info.has_batch_no:
					product = {"GTIN": gtin, "BN": item.batch_no, "QUANTITY": qty}
					expiry = frappe.db.get_value("Batch", item.batch_no, "expiry_date")
					if expiry:
						product["XD"] = str(expiry)
					resp = connector.call_service(
						"TransferCancelBatchService", "TransferCancelBatchServiceRequest",
						{"TOGLN": customer_gln, "PRODUCTLIST": {"PRODUCT": [product]}},
					)
					results.append({"service": "TransferCancelBatchService", "response": str(resp)})
			else:
				# Normal DN → Transfer
				if item.serial_no:
					products = _build_product_entries(item, gtin)
					resp = connector.call_service(
						"TransferService", "TransferServiceRequest",
						{"TOGLN": customer_gln, "PRODUCTLIST": {"PRODUCT": products}},
					)
					results.append({"service": "TransferService", "response": str(resp)})
				elif item.batch_no and info.has_batch_no:
					product = {"GTIN": gtin, "BN": item.batch_no, "QUANTITY": qty}
					expiry = frappe.db.get_value("Batch", item.batch_no, "expiry_date")
					if expiry:
						product["XD"] = str(expiry)
					resp = connector.call_service(
						"TransferBatchService", "TransferBatchServiceRequest",
						{"TOGLN": customer_gln, "PRODUCTLIST": {"PRODUCT": [product]}},
					)
					results.append({"service": "TransferBatchService", "response": str(resp)})

	elif doctype == "Stock Entry":
		if doc.purpose != "Material Issue":
			frappe.throw("Only Material Issue Stock Entries trigger RSD Deactivation")
		for item in doc.items:
			if not _is_rsd_tracked(item.item_code):
				continue
			info = _get_item_rsd_info(item.item_code)
			if not info or not info.custom_gtin:
				continue

			gtin = info.custom_gtin
			dr = (doc.get("custom_rsd_deactivation_reason") or "30").split(" ")[0]
			serial_data = item.serial_no or getattr(item, "custom_rsd_serial_no", None) or ""
			for sn in serial_data.strip().split("\n"):
				sn = sn.strip()
				if not sn:
					continue
				prod = _build_serial_product(gtin, sn, item.batch_no)
				params = {"DR": dr, "EXPLANATION": doc.get("remarks") or dr, "PRODUCTLIST": {"PRODUCT": [prod]}}
				resp = connector.call_service(
					"DeactivationService", "DeactivationServiceRequest", params,
				)
				results.append({"service": "DeactivationService", "response": str(resp)})

	# Check the latest transaction log to determine actual status
	has_error = False
	error_detail = ""
	if results:
		latest_log = frappe.get_all(
			"RSD Transaction Log",
			filters={"service_name": ["in", [r["service"] for r in results]]},
			fields=["status", "error_message"],
			order_by="creation desc",
			limit=1,
		)
		if latest_log and latest_log[0].status == "Error":
			has_error = True
			error_detail = latest_log[0].error_message or ""

	status = "Failed" if has_error else ("Sent" if results else "Not Applicable")
	try:
		frappe.db.set_value(doctype, docname, "custom_rsd_status", status, update_modified=False)
	except Exception:
		pass

	frappe.db.commit()

	if has_error:
		return {"status": "error", "message": error_detail or "SFDA returned an error", "results": results}
	return {"status": "ok", "message": "RSD notification sent successfully", "results": results}


# ---------------------------------------------------------------------------
# ERPNext Document Event Handlers
# ---------------------------------------------------------------------------

def on_stock_entry_submit(doc, method):
	"""Router for Stock Entry submit.

	Material Issue → Deactivation notification.
	Material Transfer (Across Branch, different GLNs) → Transfer notification.
	"""
	if doc.purpose not in ("Material Issue", "Material Transfer"):
		return

	branch = _resolve_branch(doc)
	settings = _get_branch_settings(branch)
	if not settings:
		_skip_rsd(doc, f"no enabled RSD Settings for branch '{branch}'" if branch else "no branch resolvable")
		return

	if doc.purpose == "Material Issue":
		_handle_se_deactivation(doc, branch)
	else:  # Material Transfer
		_handle_se_transfer(doc, branch, settings, cancel=False)


def _handle_se_deactivation(doc, branch):
	"""Emit DeactivationService notifications for a Material Issue Stock Entry.

	Deactivation requires serial numbers (no batch variant exists in SFDA).
	Uses serial_no or custom_rsd_serial_no as fallback.
	"""
	dr = (doc.get("custom_rsd_deactivation_reason") or "30").split(" ")[0]

	for item in doc.items:
		if not _is_rsd_tracked(item.item_code):
			continue

		info = _get_item_rsd_info(item.item_code)
		if not info or not info.custom_gtin:
			continue

		gtin = info.custom_gtin

		# Get serial numbers: standard field or RSD custom field
		serial_data = item.serial_no or getattr(item, "custom_rsd_serial_no", None) or ""
		if not serial_data.strip():
			continue

		for sn in serial_data.strip().split("\n"):
			sn = sn.strip()
			if not sn:
				continue
			prod = _build_serial_product(gtin, sn, item.batch_no)

			params = {
				"DR": dr,
				"EXPLANATION": doc.get("remarks") or dr,
				"PRODUCTLIST": {"PRODUCT": [prod]},
			}

			_enqueue_rsd_notification(
				branch=branch,
				service_name="DeactivationService",
				operation="DeactivationServiceRequest",
				params=params,
				reference_doctype="Stock Entry",
				reference_name=doc.name,
			)


def _handle_se_transfer(doc, source_branch, source_settings, cancel):
	"""Emit TransferService / TransferCancelService for a Material Transfer Stock Entry.

	Skips if:
	  - Transfer scope is not "Across Branch" (intra-branch moves need no RSD)
	  - Target branch is unset
	  - Target branch has no enabled RSD Settings / GLN
	  - Source and target branches share the same stakeholder GLN
	"""
	scope = doc.get("custom_rsd_transfer_scope")
	if scope != "Across Branch":
		_skip_rsd(doc, f"transfer scope is '{scope or 'Within Branch'}' — no SFDA notification")
		return

	target_branch = doc.get("custom_rsd_target_branch")
	if not target_branch:
		_skip_rsd(doc, "across-branch transfer without target branch set")
		return

	target_settings = _get_branch_settings(target_branch)
	if not target_settings or not target_settings.stakeholder_gln:
		_skip_rsd(doc, f"target branch '{target_branch}' has no enabled RSD Settings or GLN")
		return

	if source_settings.stakeholder_gln == target_settings.stakeholder_gln:
		_skip_rsd(doc, f"source and target branch share GLN '{source_settings.stakeholder_gln}' — no notification needed")
		return

	to_gln = target_settings.stakeholder_gln
	serial_svc = "TransferCancelService" if cancel else "TransferService"
	batch_svc = "TransferCancelBatchService" if cancel else "TransferBatchService"

	for item in doc.items:
		if not _is_rsd_tracked(item.item_code):
			continue
		info = _get_item_rsd_info(item.item_code)
		if not info or not info.custom_gtin:
			continue
		gtin = info.custom_gtin
		qty = abs(int(item.qty))

		if item.serial_no:
			products = _build_product_entries(item, gtin)
			_enqueue_rsd_notification(
				branch=source_branch,
				service_name=serial_svc,
				operation=f"{serial_svc}Request",
				params={"TOGLN": to_gln, "PRODUCTLIST": {"PRODUCT": products}},
				reference_doctype="Stock Entry",
				reference_name=doc.name,
			)
		elif item.batch_no and info.has_batch_no:
			product = {"GTIN": gtin, "BN": item.batch_no, "QUANTITY": qty}
			expiry = frappe.db.get_value("Batch", item.batch_no, "expiry_date")
			if expiry:
				product["XD"] = str(expiry)
			_enqueue_rsd_notification(
				branch=source_branch,
				service_name=batch_svc,
				operation=f"{batch_svc}Request",
				params={"TOGLN": to_gln, "PRODUCTLIST": {"PRODUCT": [product]}},
				reference_doctype="Stock Entry",
				reference_name=doc.name,
			)


def on_purchase_receipt_submit(doc, method):
	"""Handle Purchase Receipt submit.

	Normal receipt → AcceptService (receiving from supplier)
	Purchase Return (is_return=1) → ReturnBatchService (returning to supplier)
	"""
	branch = _resolve_branch(doc)
	settings = _get_branch_settings(branch)
	if not settings:
		_skip_rsd(doc, f"no enabled RSD Settings for branch '{branch}'" if branch else "no branch resolvable")
		return

	supplier_gln = frappe.db.get_value("Supplier", doc.supplier, "custom_gln")
	if not supplier_gln:
		return

	is_return = doc.get("is_return") or False

	for item in doc.items:
		if not _is_rsd_tracked(item.item_code):
			continue

		info = _get_item_rsd_info(item.item_code)
		if not info or not info.custom_gtin:
			continue

		gtin = info.custom_gtin
		qty = abs(int(item.qty))  # Always positive for SFDA

		if is_return:
			# Purchase Return → Return to supplier
			if item.serial_no:
				products = _build_product_entries(item, gtin)
				_enqueue_rsd_notification(
					branch=branch,
					service_name="ReturnService",
					operation="ReturnServiceRequest",
					params={
						"TOGLN": supplier_gln,
						"PRODUCTLIST": {"PRODUCT": products},
					},
					reference_doctype="Purchase Receipt",
					reference_name=doc.name,
				)
			elif item.batch_no and info.has_batch_no:
				product = {"GTIN": gtin, "BN": item.batch_no, "QUANTITY": qty}
				expiry = frappe.db.get_value("Batch", item.batch_no, "expiry_date")
				if expiry:
					product["XD"] = str(expiry)
				_enqueue_rsd_notification(
					branch=branch,
					service_name="ReturnBatchService",
					operation="ReturnBatchServiceRequest",
					params={
						"TOGLN": supplier_gln,
						"PRODUCTLIST": {"PRODUCT": [product]},
					},
					reference_doctype="Purchase Receipt",
					reference_name=doc.name,
				)
		else:
			# Normal receipt → Accept from supplier
			if item.serial_no:
				products = _build_product_entries(item, gtin)
				_enqueue_rsd_notification(
					branch=branch,
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
				product = {"GTIN": gtin, "BN": item.batch_no, "QUANTITY": qty}
				expiry = frappe.db.get_value("Batch", item.batch_no, "expiry_date")
				if expiry:
					product["XD"] = str(expiry)
				_enqueue_rsd_notification(
					branch=branch,
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
	"""Handle Sales Invoice submit.

	Consumer sale (no GLN or GLN=0000000000000) → PharmacySale / PharmacySaleCancel
	B2B sale (customer has real GLN) → Transfer / TransferCancel
	"""
	branch = _resolve_branch(doc)
	settings = _get_branch_settings(branch)
	if not settings:
		_skip_rsd(doc, f"no enabled RSD Settings for branch '{branch}'" if branch else "no branch resolvable")
		return

	customer_gln = frappe.db.get_value("Customer", doc.customer, "custom_gln")
	is_consumer = not customer_gln or customer_gln == "0000000000000"
	is_return = doc.get("is_return") or False

	products = []
	for item in doc.items:
		if not _is_rsd_tracked(item.item_code):
			continue

		info = _get_item_rsd_info(item.item_code)
		if not info or not info.custom_gtin:
			continue

		gtin = info.custom_gtin

		# Get batch_no — may be empty on return items
		batch_no = item.batch_no
		if not batch_no and is_return and doc.get("return_against"):
			batch_no = frappe.db.get_value(
				"Sales Invoice Item",
				{"parent": doc.return_against, "item_code": item.item_code},
				"batch_no",
			)

		# Use standard serial_no for serialized items,
		# fall back to custom_rsd_serial_no for batch-only items (GS1 scanned)
		serial_data = item.serial_no or getattr(item, "custom_rsd_serial_no", None) or ""
		if serial_data.strip():
			for sn in serial_data.strip().split("\n"):
				sn = sn.strip()
				if sn:
					prod = _build_serial_product(gtin, sn, batch_no)
					products.append(prod)
		elif not is_consumer and batch_no:
			# B2B Transfer: batch-only items (no serial) → batch-level transfer
			prod = {"GTIN": gtin, "BN": batch_no, "QUANTITY": abs(int(item.qty))}
			expiry = frappe.db.get_value("Batch", batch_no, "expiry_date")
			if expiry:
				prod["XD"] = str(expiry)
			products.append(prod)

	if not products:
		return

	if is_consumer:
		# Consumer sale → PharmacySale / PharmacySaleCancel
		to_gln = getattr(settings, "pharmacy_sale_togln", None) or "0000000000000"
		if is_return:
			original_invoice = doc.get("return_against") or doc.name
			_enqueue_rsd_notification(
				branch=branch,
				service_name="PharmacySaleCancelService",
				operation="PharmacySaleCancelServiceRequest",
				params={
					"TOGLN": to_gln,
					"PRODUCTLIST": {"PRODUCT": products},
					"PRESCRIPTIONID": original_invoice,
				},
				reference_doctype="Sales Invoice",
				reference_name=doc.name,
			)
		else:
			_enqueue_rsd_notification(
				branch=branch,
				service_name="PharmacySaleService",
				operation="PharmacySaleServiceRequest",
				params={
					"TOGLN": to_gln,
					"PRODUCTLIST": {"PRODUCT": products},
					"PRESCRIPTIONID": doc.name,
					"PRESCRIPTIONDATE": str(doc.posting_date),
				},
				reference_doctype="Sales Invoice",
				reference_name=doc.name,
			)
	else:
		# B2B sale → Transfer / TransferCancel
		# Split products into serial (has SN) and batch (has QUANTITY) groups
		serial_products = [p for p in products if p.get("SN")]
		batch_products = [p for p in products if p.get("QUANTITY")]

		if is_return:
			if serial_products:
				_enqueue_rsd_notification(
					branch=branch,
					service_name="TransferCancelService",
					operation="TransferCancelServiceRequest",
					params={"TOGLN": customer_gln, "PRODUCTLIST": {"PRODUCT": serial_products}},
					reference_doctype="Sales Invoice",
					reference_name=doc.name,
				)
			for bp in batch_products:
				_enqueue_rsd_notification(
					branch=branch,
					service_name="TransferCancelBatchService",
					operation="TransferCancelBatchServiceRequest",
					params={"TOGLN": customer_gln, "PRODUCTLIST": {"PRODUCT": [bp]}},
					reference_doctype="Sales Invoice",
					reference_name=doc.name,
				)
		else:
			if serial_products:
				_enqueue_rsd_notification(
					branch=branch,
					service_name="TransferService",
					operation="TransferServiceRequest",
					params={"TOGLN": customer_gln, "PRODUCTLIST": {"PRODUCT": serial_products}},
					reference_doctype="Sales Invoice",
					reference_name=doc.name,
				)
			for bp in batch_products:
				_enqueue_rsd_notification(
					branch=branch,
					service_name="TransferBatchService",
					operation="TransferBatchServiceRequest",
					params={"TOGLN": customer_gln, "PRODUCTLIST": {"PRODUCT": [bp]}},
					reference_doctype="Sales Invoice",
					reference_name=doc.name,
				)


def on_delivery_note_submit(doc, method):
	"""Handle Delivery Note submit -- Transfer products to another pharmacy.

	Only transfers to customers with a GLN (B2B).
	Normal DN → TransferService / TransferBatchService
	Return DN → TransferCancelService / TransferCancelBatchService
	"""
	branch = _resolve_branch(doc)
	settings = _get_branch_settings(branch)
	if not settings:
		_skip_rsd(doc, f"no enabled RSD Settings for branch '{branch}'" if branch else "no branch resolvable")
		return

	customer_gln = frappe.db.get_value("Customer", doc.customer, "custom_gln")
	if not customer_gln:
		return

	is_return = doc.get("is_return") or False

	for item in doc.items:
		if not _is_rsd_tracked(item.item_code):
			continue

		info = _get_item_rsd_info(item.item_code)
		if not info or not info.custom_gtin:
			continue

		gtin = info.custom_gtin
		qty = abs(int(item.qty))

		if is_return:
			# Delivery Return → TransferCancel
			if item.serial_no:
				products = _build_product_entries(item, gtin)
				_enqueue_rsd_notification(
					branch=branch,
					service_name="TransferCancelService",
					operation="TransferCancelServiceRequest",
					params={
						"TOGLN": customer_gln,
						"PRODUCTLIST": {"PRODUCT": products},
					},
					reference_doctype="Delivery Note",
					reference_name=doc.name,
				)
			elif item.batch_no and info.has_batch_no:
				product = {"GTIN": gtin, "BN": item.batch_no, "QUANTITY": qty}
				expiry = frappe.db.get_value("Batch", item.batch_no, "expiry_date")
				if expiry:
					product["XD"] = str(expiry)
				_enqueue_rsd_notification(
					branch=branch,
					service_name="TransferCancelBatchService",
					operation="TransferCancelBatchServiceRequest",
					params={
						"TOGLN": customer_gln,
						"PRODUCTLIST": {"PRODUCT": [product]},
					},
					reference_doctype="Delivery Note",
					reference_name=doc.name,
				)
		else:
			# Normal DN → Transfer
			if item.serial_no:
				products = _build_product_entries(item, gtin)
				_enqueue_rsd_notification(
					branch=branch,
					service_name="TransferService",
					operation="TransferServiceRequest",
					params={
						"TOGLN": customer_gln,
						"PRODUCTLIST": {"PRODUCT": products},
					},
					reference_doctype="Delivery Note",
					reference_name=doc.name,
				)
			elif item.batch_no and info.has_batch_no:
				product = {
					"GTIN": gtin,
					"BN": item.batch_no,
					"QUANTITY": qty,
				}
				expiry = frappe.db.get_value("Batch", item.batch_no, "expiry_date")
				if expiry:
					product["XD"] = str(expiry)
				_enqueue_rsd_notification(
					branch=branch,
					service_name="TransferBatchService",
					operation="TransferBatchServiceRequest",
					params={
						"TOGLN": customer_gln,
						"PRODUCTLIST": {"PRODUCT": [product]},
					},
					reference_doctype="Delivery Note",
					reference_name=doc.name,
				)


# ---------------------------------------------------------------------------
# on_cancel Handlers — reverse the on_submit operation
# ---------------------------------------------------------------------------

def on_stock_entry_cancel(doc, method):
	"""Router for Stock Entry cancel.

	Material Issue → DeactivationCancelService.
	Material Transfer (Across Branch, different GLNs) → TransferCancelService.
	"""
	if doc.purpose not in ("Material Issue", "Material Transfer"):
		return
	branch = _resolve_branch(doc)
	settings = _get_branch_settings(branch)
	if not settings:
		_skip_rsd(doc, f"no enabled RSD Settings for branch '{branch}'" if branch else "no branch resolvable")
		return

	if doc.purpose == "Material Issue":
		_handle_se_deactivation_cancel(doc, branch)
	else:  # Material Transfer
		_handle_se_transfer(doc, branch, settings, cancel=True)


def _handle_se_deactivation_cancel(doc, branch):
	"""Emit DeactivationCancelService notifications for a cancelled Material Issue."""
	for item in doc.items:
		if not _is_rsd_tracked(item.item_code):
			continue
		info = _get_item_rsd_info(item.item_code)
		if not info or not info.custom_gtin:
			continue

		gtin = info.custom_gtin
		batch_no = _get_item_batch_no(item)
		serial_data = item.serial_no or getattr(item, "custom_rsd_serial_no", None) or ""
		for sn in serial_data.strip().split("\n"):
			sn = sn.strip()
			if not sn:
				continue
			prod = _build_serial_product(gtin, sn, batch_no)
			_enqueue_rsd_notification(
				branch=branch,
				service_name="DeactivationCancelService",
				operation="DeactivationCancelServiceRequest",
				params={"PRODUCTLIST": {"PRODUCT": [prod]}},
				reference_doctype="Stock Entry",
				reference_name=doc.name,
			)


def on_purchase_receipt_cancel(doc, method):
	"""Cancel PR: normal → Return (reverse accept). Return → Accept (reverse return)."""
	branch = _resolve_branch(doc)
	settings = _get_branch_settings(branch)
	if not settings:
		_skip_rsd(doc, f"no enabled RSD Settings for branch '{branch}'" if branch else "no branch resolvable")
		return

	supplier_gln = frappe.db.get_value("Supplier", doc.supplier, "custom_gln")
	if not supplier_gln:
		return

	was_return = doc.get("is_return") or False

	for item in doc.items:
		if not _is_rsd_tracked(item.item_code):
			continue
		info = _get_item_rsd_info(item.item_code)
		if not info or not info.custom_gtin:
			continue

		gtin = info.custom_gtin
		qty = abs(int(item.qty))
		batch_no = _get_item_batch_no(item)

		if was_return:
			if item.serial_no:
				products = _build_product_entries(item, gtin)
				_enqueue_rsd_notification(
					branch=branch,
					service_name="AcceptService", operation="AcceptServiceRequest",
					params={"FROMGLN": supplier_gln, "PRODUCTLIST": {"PRODUCT": products}},
					reference_doctype="Purchase Receipt", reference_name=doc.name)
			elif batch_no and info.has_batch_no:
				product = {"GTIN": gtin, "BN": batch_no, "QUANTITY": qty}
				expiry = frappe.db.get_value("Batch", batch_no, "expiry_date")
				if expiry:
					product["XD"] = str(expiry)
				_enqueue_rsd_notification(
					branch=branch,
					service_name="AcceptBatchService", operation="AcceptBatchServiceRequest",
					params={"FROMGLN": supplier_gln, "PRODUCTLIST": {"PRODUCT": [product]}},
					reference_doctype="Purchase Receipt", reference_name=doc.name)
		else:
			if item.serial_no:
				products = _build_product_entries(item, gtin)
				_enqueue_rsd_notification(
					branch=branch,
					service_name="ReturnService", operation="ReturnServiceRequest",
					params={"TOGLN": supplier_gln, "PRODUCTLIST": {"PRODUCT": products}},
					reference_doctype="Purchase Receipt", reference_name=doc.name)
			elif batch_no and info.has_batch_no:
				product = {"GTIN": gtin, "BN": batch_no, "QUANTITY": qty}
				expiry = frappe.db.get_value("Batch", batch_no, "expiry_date")
				if expiry:
					product["XD"] = str(expiry)
				_enqueue_rsd_notification(
					branch=branch,
					service_name="ReturnBatchService", operation="ReturnBatchServiceRequest",
					params={"TOGLN": supplier_gln, "PRODUCTLIST": {"PRODUCT": [product]}},
					reference_doctype="Purchase Receipt", reference_name=doc.name)


def on_sales_invoice_cancel(doc, method):
	"""Cancel SI: consumer normal → SaleCancel. Consumer return → Sale. B2B normal → TransferCancel. B2B return → Transfer."""
	branch = _resolve_branch(doc)
	settings = _get_branch_settings(branch)
	if not settings:
		_skip_rsd(doc, f"no enabled RSD Settings for branch '{branch}'" if branch else "no branch resolvable")
		return

	customer_gln = frappe.db.get_value("Customer", doc.customer, "custom_gln")
	is_consumer = not customer_gln or customer_gln == "0000000000000"
	was_return = doc.get("is_return") or False

	products = []
	for item in doc.items:
		if not _is_rsd_tracked(item.item_code):
			continue
		info = _get_item_rsd_info(item.item_code)
		if not info or not info.custom_gtin:
			continue
		gtin = info.custom_gtin
		batch_no = item.batch_no
		if not batch_no and was_return and doc.get("return_against"):
			batch_no = frappe.db.get_value("Sales Invoice Item",
				{"parent": doc.return_against, "item_code": item.item_code}, "batch_no")

		serial_data = item.serial_no or getattr(item, "custom_rsd_serial_no", None) or ""
		if serial_data.strip():
			for sn in serial_data.strip().split("\n"):
				sn = sn.strip()
				if sn:
					prod = _build_serial_product(gtin, sn, batch_no)
					products.append(prod)
		elif not is_consumer and batch_no:
			prod = {"GTIN": gtin, "BN": batch_no, "QUANTITY": abs(int(item.qty))}
			expiry = frappe.db.get_value("Batch", batch_no, "expiry_date")
			if expiry:
				prod["XD"] = str(expiry)
			products.append(prod)

	if not products:
		return

	if is_consumer:
		to_gln = getattr(settings, "pharmacy_sale_togln", None) or "0000000000000"
		if was_return:
			_enqueue_rsd_notification(
				branch=branch,
				service_name="PharmacySaleService", operation="PharmacySaleServiceRequest",
				params={"TOGLN": to_gln, "PRODUCTLIST": {"PRODUCT": products},
						"PRESCRIPTIONID": doc.name, "PRESCRIPTIONDATE": str(doc.posting_date)},
				reference_doctype="Sales Invoice", reference_name=doc.name)
		else:
			_enqueue_rsd_notification(
				branch=branch,
				service_name="PharmacySaleCancelService", operation="PharmacySaleCancelServiceRequest",
				params={"TOGLN": to_gln, "PRODUCTLIST": {"PRODUCT": products},
						"PRESCRIPTIONID": doc.name},
				reference_doctype="Sales Invoice", reference_name=doc.name)
	else:
		serial_prods = [p for p in products if p.get("SN")]
		batch_prods = [p for p in products if p.get("QUANTITY")]
		if was_return:
			if serial_prods:
				_enqueue_rsd_notification(
					branch=branch,
					service_name="TransferService", operation="TransferServiceRequest",
					params={"TOGLN": customer_gln, "PRODUCTLIST": {"PRODUCT": serial_prods}},
					reference_doctype="Sales Invoice", reference_name=doc.name)
			for bp in batch_prods:
				_enqueue_rsd_notification(
					branch=branch,
					service_name="TransferBatchService", operation="TransferBatchServiceRequest",
					params={"TOGLN": customer_gln, "PRODUCTLIST": {"PRODUCT": [bp]}},
					reference_doctype="Sales Invoice", reference_name=doc.name)
		else:
			if serial_prods:
				_enqueue_rsd_notification(
					branch=branch,
					service_name="TransferCancelService", operation="TransferCancelServiceRequest",
					params={"TOGLN": customer_gln, "PRODUCTLIST": {"PRODUCT": serial_prods}},
					reference_doctype="Sales Invoice", reference_name=doc.name)
			for bp in batch_prods:
				_enqueue_rsd_notification(
					branch=branch,
					service_name="TransferCancelBatchService", operation="TransferCancelBatchServiceRequest",
					params={"TOGLN": customer_gln, "PRODUCTLIST": {"PRODUCT": [bp]}},
					reference_doctype="Sales Invoice", reference_name=doc.name)


def on_delivery_note_cancel(doc, method):
	"""Cancel DN: normal → TransferCancel. Return → Transfer."""
	branch = _resolve_branch(doc)
	settings = _get_branch_settings(branch)
	if not settings:
		_skip_rsd(doc, f"no enabled RSD Settings for branch '{branch}'" if branch else "no branch resolvable")
		return

	customer_gln = frappe.db.get_value("Customer", doc.customer, "custom_gln")
	if not customer_gln:
		return

	was_return = doc.get("is_return") or False

	for item in doc.items:
		if not _is_rsd_tracked(item.item_code):
			continue
		info = _get_item_rsd_info(item.item_code)
		if not info or not info.custom_gtin:
			continue

		gtin = info.custom_gtin
		qty = abs(int(item.qty))
		batch_no = _get_item_batch_no(item)

		if was_return:
			if item.serial_no:
				products = _build_product_entries(item, gtin)
				_enqueue_rsd_notification(
					branch=branch,
					service_name="TransferService", operation="TransferServiceRequest",
					params={"TOGLN": customer_gln, "PRODUCTLIST": {"PRODUCT": products}},
					reference_doctype="Delivery Note", reference_name=doc.name)
			elif batch_no and info.has_batch_no:
				product = {"GTIN": gtin, "BN": batch_no, "QUANTITY": qty}
				expiry = frappe.db.get_value("Batch", batch_no, "expiry_date")
				if expiry:
					product["XD"] = str(expiry)
				_enqueue_rsd_notification(
					branch=branch,
					service_name="TransferBatchService", operation="TransferBatchServiceRequest",
					params={"TOGLN": customer_gln, "PRODUCTLIST": {"PRODUCT": [product]}},
					reference_doctype="Delivery Note", reference_name=doc.name)
		else:
			if item.serial_no:
				products = _build_product_entries(item, gtin)
				_enqueue_rsd_notification(
					branch=branch,
					service_name="TransferCancelService", operation="TransferCancelServiceRequest",
					params={"TOGLN": customer_gln, "PRODUCTLIST": {"PRODUCT": products}},
					reference_doctype="Delivery Note", reference_name=doc.name)
			elif batch_no and info.has_batch_no:
				product = {"GTIN": gtin, "BN": batch_no, "QUANTITY": qty}
				expiry = frappe.db.get_value("Batch", batch_no, "expiry_date")
				if expiry:
					product["XD"] = str(expiry)
				_enqueue_rsd_notification(
					branch=branch,
					service_name="TransferCancelBatchService", operation="TransferCancelBatchServiceRequest",
					params={"TOGLN": customer_gln, "PRODUCTLIST": {"PRODUCT": [product]}},
					reference_doctype="Delivery Note", reference_name=doc.name)
