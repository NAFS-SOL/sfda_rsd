# sfda_rsd/connectors/services/consume_service.py
"""SFDA DTTS Consume services (hospitals/consumption centers)."""
from sfda_rsd.connectors.rsd_connector import RSDConnector


def consume_product(branch, gtin, serial_number, batch_number=None, expiry_date=None):
	"""Mark a drug as consumed for patient treatment."""
	connector = RSDConnector(branch=branch)
	product = {"GTIN": gtin, "SN": serial_number}
	if batch_number:
		product["BN"] = batch_number
	if expiry_date:
		product["XD"] = expiry_date

	return connector.call_service(
		"ConsumeService",
		"ConsumeServiceRequest",
		{"PRODUCTLIST": {"PRODUCT": [product]}},
	)


def consume_cancel(branch, gtin, serial_number, batch_number=None, expiry_date=None):
	"""Cancel a consume operation."""
	connector = RSDConnector(branch=branch)
	product = {"GTIN": gtin, "SN": serial_number}
	if batch_number:
		product["BN"] = batch_number
	if expiry_date:
		product["XD"] = expiry_date

	return connector.call_service(
		"ConsumeCancelService",
		"ConsumeCancelServiceRequest",
		{"PRODUCTLIST": {"PRODUCT": [product]}},
	)
