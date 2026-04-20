import frappe


def sync_gtin_to_barcodes(doc, method=None):
	gtin = (doc.get("custom_gtin") or "").strip()
	if not gtin:
		return

	for row in (doc.get("barcodes") or []):
		if (row.barcode or "").strip() == gtin:
			return

	doc.append("barcodes", {"barcode": gtin})
