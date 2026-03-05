# sfda_rsd/connectors/services/dispatch_service.py
"""SFDA DTTS Dispatch services.

Service URLs (per DTTS-ISD.DISPATCH-1.0.2):
  Dispatch:             {base}/ws/DispatchService/DispatchService?wsdl
  DispatchBatch:        {base}/ws/DispatchBatchService/DispatchBatchService?wsdl
  DispatchCancel:       {base}/ws/DispatchCancelService/DispatchCancelService?wsdl
  DispatchCancelBatch:  {base}/ws/DispatchCancelBatchService/DispatchCancelBatchService?wsdl
"""
from sfda_rsd.sfda_rsd.connectors.rsd_connector import RSDConnector


def dispatch_product(gtin, serial_number, receiver_gln, batch_number=None, expiry_date=None):
	"""Dispatch a product to another stakeholder (by serial number).

	Args:
		gtin: Global Trade Item Number
		serial_number: Serial Number of the unit
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
		"DispatchService",
		"DispatchServiceRequest",
		{"TOGLN": receiver_gln, "PRODUCTLIST": {"PRODUCT": [product]}},
	)


def dispatch_products_bulk(products, receiver_gln):
	"""Dispatch multiple products to a receiver in a single SOAP call.

	SFDA supports PRODUCTLIST with multiple PRODUCT entries.

	Args:
		products: List of dicts with keys: gtin, serial_number, batch_number (opt), expiry_date (opt)
		receiver_gln: Destination GLN (TOGLN)
	"""
	connector = RSDConnector()
	product_list = []
	for p in products:
		prod = {"GTIN": p["gtin"], "SN": p["serial_number"]}
		if p.get("batch_number"):
			prod["BN"] = p["batch_number"]
		if p.get("expiry_date"):
			prod["XD"] = p["expiry_date"]
		product_list.append(prod)

	return connector.call_service(
		"DispatchService",
		"DispatchServiceRequest",
		{"TOGLN": receiver_gln, "PRODUCTLIST": {"PRODUCT": product_list}},
	)


def dispatch_by_batch(gtin, batch_number, receiver_gln, quantity, expiry_date=None):
	"""Dispatch products by batch number."""
	connector = RSDConnector()
	product = {"GTIN": gtin, "BN": batch_number, "QUANTITY": quantity}
	if expiry_date:
		product["XD"] = expiry_date

	return connector.call_service(
		"DispatchBatchService",
		"DispatchBatchServiceRequest",
		{"TOGLN": receiver_gln, "PRODUCTLIST": {"PRODUCT": [product]}},
	)


def dispatch_cancel(gtin, serial_number, receiver_gln, batch_number=None, expiry_date=None):
	"""Cancel a dispatch operation (by serial number)."""
	connector = RSDConnector()
	product = {"GTIN": gtin, "SN": serial_number}
	if batch_number:
		product["BN"] = batch_number
	if expiry_date:
		product["XD"] = expiry_date

	return connector.call_service(
		"DispatchCancelService",
		"DispatchCancelServiceRequest",
		{"TOGLN": receiver_gln, "PRODUCTLIST": {"PRODUCT": [product]}},
	)


def dispatch_cancel_by_batch(gtin, batch_number, receiver_gln, quantity, expiry_date=None):
	"""Cancel a dispatch by batch number."""
	connector = RSDConnector()
	product = {"GTIN": gtin, "BN": batch_number, "QUANTITY": quantity}
	if expiry_date:
		product["XD"] = expiry_date

	return connector.call_service(
		"DispatchCancelBatchService",
		"DispatchCancelBatchServiceRequest",
		{"TOGLN": receiver_gln, "PRODUCTLIST": {"PRODUCT": [product]}},
	)
