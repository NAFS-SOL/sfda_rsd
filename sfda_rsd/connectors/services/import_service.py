# sfda_rsd/connectors/services/import_service.py
"""SFDA DTTS Import services (warehouse/manufacturer operation).

Service URLs (per DTTS-ISD.IMPORT-1.0.2):
  Import:       {base}/ws/ImportService/ImportService?wsdl
  ImportCancel: {base}/ws/ImportCancelService/ImportCancelService?wsdl

NOTE: Import is a warehouse/manufacturer operation. Retained for completeness.
"""
from sfda_rsd.sfda_rsd.connectors.rsd_connector import RSDConnector


def import_product(gtin, serial_numbers, batch_number, expiry_date,
				   manufacturing_date=None):
	"""Register imported products into the system.

	Args:
		gtin: Global Trade Item Number
		serial_numbers: List of serial numbers (SNREQUESTLIST)
		batch_number: Batch/Lot number
		expiry_date: Expiry date (YYYY-MM-DD)
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
		"ImportService", "ImportServiceRequest", params
	)


def import_cancel(gtin, serial_number, batch_number=None, expiry_date=None):
	"""Cancel an import."""
	connector = RSDConnector()
	product = {"GTIN": gtin, "SN": serial_number}
	if batch_number:
		product["BN"] = batch_number
	if expiry_date:
		product["XD"] = expiry_date

	return connector.call_service(
		"ImportCancelService",
		"ImportCancelServiceRequest",
		{"PRODUCTLIST": {"PRODUCT": [product]}},
	)
