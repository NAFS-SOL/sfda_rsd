# sfda_rsd/connectors/services/accept_service.py
"""SFDA DTTS Accept services.

Service URLs (per DTTS-ISD.ACCEPT-1.0.2):
  Accept:      {base}/ws/AcceptService/AcceptService?wsdl
  AcceptBatch: {base}/ws/AcceptBatchService/AcceptBatchService?wsdl
"""
from sfda_rsd.connectors.rsd_connector import RSDConnector


def accept_product(branch, gtin, serial_number, sender_gln, batch_number=None, expiry_date=None):
	"""Accept a product dispatched to this stakeholder (by serial number).

	Args:
		gtin: Global Trade Item Number
		serial_number: Serial Number
		sender_gln: GLN of the sender (FROMGLN)
		batch_number: Optional batch number
		expiry_date: Optional expiry date (YYYY-MM-DD)
	"""
	connector = RSDConnector(branch=branch)
	product = {"GTIN": gtin, "SN": serial_number}
	if batch_number:
		product["BN"] = batch_number
	if expiry_date:
		product["XD"] = expiry_date

	return connector.call_service(
		"AcceptService",
		"AcceptServiceRequest",
		{"FROMGLN": sender_gln, "PRODUCTLIST": {"PRODUCT": [product]}},
	)


def accept_by_batch(branch, gtin, batch_number, sender_gln, quantity, expiry_date=None):
	"""Accept products by batch number."""
	connector = RSDConnector(branch=branch)
	product = {"GTIN": gtin, "BN": batch_number, "QUANTITY": quantity}
	if expiry_date:
		product["XD"] = expiry_date

	return connector.call_service(
		"AcceptBatchService",
		"AcceptBatchServiceRequest",
		{"FROMGLN": sender_gln, "PRODUCTLIST": {"PRODUCT": [product]}},
	)


def accept_dispatch(branch, notification_id):
	"""Accept ALL units in a dispatch notification at once."""
	connector = RSDConnector(branch=branch)
	return connector.call_service(
		"AcceptService",
		"AcceptServiceRequest",
		{"NOTIFICATIONID": notification_id},
	)


def accept_cancel(branch, gtin, serial_number, sender_gln, batch_number=None, expiry_date=None):
	"""Cancel an accept operation."""
	connector = RSDConnector(branch=branch)
	product = {"GTIN": gtin, "SN": serial_number}
	if batch_number:
		product["BN"] = batch_number
	if expiry_date:
		product["XD"] = expiry_date

	return connector.call_service(
		"AcceptService",
		"AcceptServiceRequest",
		{"FROMGLN": sender_gln, "PRODUCTLIST": {"PRODUCT": [product]}},
	)
