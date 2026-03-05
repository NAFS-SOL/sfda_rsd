# sfda_rsd/connectors/services/consume_service.py
"""SFDA DTTS Consume services (hospitals/consumption centers).

Service URLs (per DTTS-ISD.CONSUME-1.0.3):
  Consume:       {base}/ws/ConsumeService/ConsumeService?wsdl
  ConsumeCancel: {base}/ws/ConsumeCancelService/ConsumeCancelService?wsdl
"""
from sfda_rsd.sfda_rsd.connectors.rsd_connector import RSDConnector


def consume_product(gtin, serial_number, batch_number=None, expiry_date=None):
	"""Mark a drug as consumed for patient treatment.

	Used by hospitals and consumption centers.
	"""
	connector = RSDConnector()
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


def consume_cancel(gtin, serial_number, batch_number=None, expiry_date=None):
	"""Cancel a consume operation."""
	connector = RSDConnector()
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
