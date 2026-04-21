# sfda_rsd/connectors/services/transfer_service.py
"""SFDA DTTS Transfer services (pharmacy-to-pharmacy or center-to-center only)."""
from sfda_rsd.connectors.rsd_connector import RSDConnector


def transfer_product(branch, gtin, serial_number, receiver_gln, batch_number=None, expiry_date=None):
	"""Transfer between same-type stakeholders (pharmacy-to-pharmacy only)."""
	connector = RSDConnector(branch=branch)
	product = {"GTIN": gtin, "SN": serial_number}
	if batch_number:
		product["BN"] = batch_number
	if expiry_date:
		product["XD"] = expiry_date

	return connector.call_service(
		"TransferService",
		"TransferServiceRequest",
		{"TOGLN": receiver_gln, "PRODUCTLIST": {"PRODUCT": [product]}},
	)


def transfer_by_batch(branch, gtin, batch_number, receiver_gln, quantity, expiry_date=None):
	"""Transfer products by batch number."""
	connector = RSDConnector(branch=branch)
	product = {"GTIN": gtin, "BN": batch_number, "QUANTITY": int(quantity)}
	if expiry_date:
		product["XD"] = expiry_date

	return connector.call_service(
		"TransferBatchService",
		"TransferBatchServiceRequest",
		{"TOGLN": receiver_gln, "PRODUCTLIST": {"PRODUCT": [product]}},
	)


def transfer_cancel(branch, gtin, serial_number, receiver_gln, batch_number=None, expiry_date=None):
	"""Cancel a transfer (by serial number)."""
	connector = RSDConnector(branch=branch)
	product = {"GTIN": gtin, "SN": serial_number}
	if batch_number:
		product["BN"] = batch_number
	if expiry_date:
		product["XD"] = expiry_date

	return connector.call_service(
		"TransferCancelService",
		"TransferCancelServiceRequest",
		{"TOGLN": receiver_gln, "PRODUCTLIST": {"PRODUCT": [product]}},
	)


def transfer_cancel_by_batch(branch, gtin, batch_number, receiver_gln, quantity, expiry_date=None):
	"""Cancel a transfer by batch number."""
	connector = RSDConnector(branch=branch)
	product = {"GTIN": gtin, "BN": batch_number, "QUANTITY": int(quantity)}
	if expiry_date:
		product["XD"] = expiry_date

	return connector.call_service(
		"TransferCancelBatchService",
		"TransferCancelBatchServiceRequest",
		{"TOGLN": receiver_gln, "PRODUCTLIST": {"PRODUCT": [product]}},
	)
