# sfda_rsd/connectors/services/import_service.py
"""SFDA DTTS Import services (warehouse/manufacturer operation)."""
from sfda_rsd.connectors.rsd_connector import RSDConnector


def import_product(branch, gtin, serial_numbers, batch_number, expiry_date,
				   manufacturing_date=None):
	"""Register imported products into the system."""
	connector = RSDConnector(branch=branch)
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


def import_cancel(branch, gtin, serial_number, batch_number=None, expiry_date=None):
	"""Cancel an import."""
	connector = RSDConnector(branch=branch)
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
