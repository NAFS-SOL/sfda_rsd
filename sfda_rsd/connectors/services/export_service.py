# sfda_rsd/connectors/services/export_service.py
"""SFDA DTTS Export services (manufacturer/warehouse operation)."""
from sfda_rsd.connectors.rsd_connector import RSDConnector


def export_product(branch, gtin, serial_number, country_code, batch_number=None, expiry_date=None):
	"""Export a product out of Saudi Arabia."""
	connector = RSDConnector(branch=branch)
	product = {"GTIN": gtin, "SN": serial_number}
	if batch_number:
		product["BN"] = batch_number
	if expiry_date:
		product["XD"] = expiry_date

	return connector.call_service(
		"ExportService",
		"ExportServiceRequest",
		{"COUNTRYCODE": country_code, "PRODUCTLIST": {"PRODUCT": [product]}},
	)


def export_cancel(branch, gtin, serial_number, batch_number=None, expiry_date=None):
	"""Cancel an export."""
	connector = RSDConnector(branch=branch)
	product = {"GTIN": gtin, "SN": serial_number}
	if batch_number:
		product["BN"] = batch_number
	if expiry_date:
		product["XD"] = expiry_date

	return connector.call_service(
		"ExportCancelService",
		"ExportCancelServiceRequest",
		{"PRODUCTLIST": {"PRODUCT": [product]}},
	)
