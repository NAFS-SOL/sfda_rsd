# sfda_rsd/connectors/services/supply_service.py
"""SFDA DTTS Supply services (manufacturer operation - disabled for pharmacy).

Service URLs (per DTTS-ISD.SUPPLY-1.0.2):
  Supply:       {base}/ws/SupplyService/SupplyService?wsdl
  SupplyCancel: {base}/ws/SupplyCancelService/SupplyCancelService?wsdl

NOTE: Supply is a manufacturer-only operation. Pharmacies do not supply products.
These functions are retained for completeness but are not triggered by doc events.
"""
import frappe
from sfda_rsd.sfda_rsd.connectors.rsd_connector import RSDConnector


def supply_product(gtin, serial_numbers, batch_number, expiry_date,
				   manufacturing_date=None):
	"""Notify SFDA that products have been manufactured/supplied.

	Args:
		gtin: 14-digit Global Trade Item Number
		serial_numbers: List of serial numbers (SNREQUESTLIST)
		batch_number: Batch/Lot number
		expiry_date: Expiry date in YYYY-MM-DD format
		manufacturing_date: Optional manufacturing date
	"""
	connector = RSDConnector()
	params = {
		"GTIN": gtin,
		"BN": batch_number,
		"XD": expiry_date,
		"SNREQUESTLIST": {"SN": serial_numbers},
	}

	if manufacturing_date:
		params["MD"] = manufacturing_date

	return connector.call_service(
		"SupplyService", "SupplyServiceRequest", params
	)


def supply_cancel(gtin, serial_number, batch_number=None, expiry_date=None):
	"""Cancel a previously supplied product."""
	connector = RSDConnector()
	product = {"GTIN": gtin, "SN": serial_number}
	if batch_number:
		product["BN"] = batch_number
	if expiry_date:
		product["XD"] = expiry_date

	return connector.call_service(
		"SupplyCancelService",
		"SupplyCancelServiceRequest",
		{"PRODUCTLIST": {"PRODUCT": [product]}},
	)


def bulk_supply(gtin, serial_numbers, batch_number, expiry_date,
				manufacturing_date=None):
	"""Supply multiple serial numbers for the same GTIN/batch in one call.

	The SFDA SupplyService accepts SNREQUESTLIST with multiple SN entries.
	"""
	return supply_product(
		gtin=gtin,
		serial_numbers=serial_numbers,
		batch_number=batch_number,
		expiry_date=expiry_date,
		manufacturing_date=manufacturing_date,
	)
