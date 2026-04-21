# sfda_rsd/connectors/services/supply_service.py
"""SFDA DTTS Supply services (manufacturer operation - retained for completeness)."""
from sfda_rsd.connectors.rsd_connector import RSDConnector


def supply_product(branch, gtin, serial_numbers, batch_number, expiry_date,
				   manufacturing_date=None):
	"""Notify SFDA that products have been manufactured/supplied."""
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
		"SupplyService", "SupplyServiceRequest", params
	)


def supply_cancel(branch, gtin, serial_number, batch_number=None, expiry_date=None):
	"""Cancel a previously supplied product."""
	connector = RSDConnector(branch=branch)
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


def bulk_supply(branch, gtin, serial_numbers, batch_number, expiry_date,
				manufacturing_date=None):
	"""Supply multiple serial numbers for the same GTIN/batch in one call."""
	return supply_product(
		branch=branch,
		gtin=gtin,
		serial_numbers=serial_numbers,
		batch_number=batch_number,
		expiry_date=expiry_date,
		manufacturing_date=manufacturing_date,
	)
