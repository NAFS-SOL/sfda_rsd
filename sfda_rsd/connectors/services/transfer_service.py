# sfda_rsd/connectors/services/transfer_service.py
"""SFDA DTTS Transfer services (pharmacy-to-pharmacy or center-to-center only).

Service URLs (per DTTS-ISD.TRANSFER-1.0.2):
  Transfer:             {base}/ws/TransferService/TransferService?wsdl
  TransferBatch:        {base}/ws/TransferBatchService/TransferBatchService?wsdl
  TransferCancel:       {base}/ws/TransferCancelService/TransferCancelService?wsdl
  TransferCancelBatch:  {base}/ws/TransferCancelBatchService/TransferCancelBatchService?wsdl
"""
from sfda_rsd.sfda_rsd.connectors.rsd_connector import RSDConnector


def transfer_product(gtin, serial_number, receiver_gln, batch_number=None, expiry_date=None):
	"""Transfer between same-type stakeholders (pharmacy-to-pharmacy only).

	Args:
		gtin: Global Trade Item Number
		serial_number: Serial Number
		receiver_gln: GLN of the receiving stakeholder (TOGLN)
		batch_number: Optional batch number
		expiry_date: Optional expiry date
	"""
	connector = RSDConnector()
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


def transfer_by_batch(gtin, batch_number, receiver_gln, quantity, expiry_date=None):
	"""Transfer products by batch number."""
	connector = RSDConnector()
	product = {"GTIN": gtin, "BN": batch_number, "QUANTITY": quantity}
	if expiry_date:
		product["XD"] = expiry_date

	return connector.call_service(
		"TransferBatchService",
		"TransferBatchServiceRequest",
		{"TOGLN": receiver_gln, "PRODUCTLIST": {"PRODUCT": [product]}},
	)


def transfer_cancel(gtin, serial_number, receiver_gln, batch_number=None, expiry_date=None):
	"""Cancel a transfer (by serial number)."""
	connector = RSDConnector()
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


def transfer_cancel_by_batch(gtin, batch_number, receiver_gln, quantity, expiry_date=None):
	"""Cancel a transfer by batch number."""
	connector = RSDConnector()
	product = {"GTIN": gtin, "BN": batch_number, "QUANTITY": quantity}
	if expiry_date:
		product["XD"] = expiry_date

	return connector.call_service(
		"TransferCancelBatchService",
		"TransferCancelBatchServiceRequest",
		{"TOGLN": receiver_gln, "PRODUCTLIST": {"PRODUCT": [product]}},
	)
