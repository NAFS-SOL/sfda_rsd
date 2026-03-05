# sfda_rsd/connectors/services/return_service.py
"""SFDA DTTS Return services.

Service URLs (per DTTS-ISD.RETURN-1.0.2):
  Return:      {base}/ws/ReturnService/ReturnService?wsdl
  ReturnBatch: {base}/ws/ReturnBatchService/ReturnBatchService?wsdl
"""
from sfda_rsd.sfda_rsd.connectors.rsd_connector import RSDConnector


def return_product(gtin, serial_number, receiver_gln, batch_number=None, expiry_date=None):
	"""Return a product to the sender stakeholder.

	Args:
		gtin: Global Trade Item Number
		serial_number: Serial Number
		receiver_gln: GLN of the entity to return to (TOGLN)
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
		"ReturnService",
		"ReturnServiceRequest",
		{"TOGLN": receiver_gln, "PRODUCTLIST": {"PRODUCT": [product]}},
	)


def return_by_batch(gtin, batch_number, receiver_gln, quantity, expiry_date=None):
	"""Return products by batch number."""
	connector = RSDConnector()
	product = {"GTIN": gtin, "BN": batch_number, "QUANTITY": quantity}
	if expiry_date:
		product["XD"] = expiry_date

	return connector.call_service(
		"ReturnBatchService",
		"ReturnBatchServiceRequest",
		{"TOGLN": receiver_gln, "PRODUCTLIST": {"PRODUCT": [product]}},
	)
