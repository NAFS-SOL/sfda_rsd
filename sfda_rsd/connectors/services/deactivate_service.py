# sfda_rsd/connectors/services/deactivate_service.py
"""SFDA DTTS Deactivation services.

Service URLs (per DTTS-ISD.DEACTIVATE-1.0.3):
  Deactivation:       {base}/ws/DeactivationService/DeactivationService?wsdl
  DeactivationCancel: {base}/ws/DeactivationCancelService/DeactivationCancelService?wsdl
"""
from sfda_rsd.sfda_rsd.connectors.rsd_connector import RSDConnector


def deactivate_product(gtin, serial_number, deactivation_reason, explanation=None,
					   batch_number=None, expiry_date=None):
	"""Remove a product from the system (broken, expired, recalled, etc.).

	Args:
		gtin: Global Trade Item Number
		serial_number: Serial Number
		deactivation_reason: DR code (reason for deactivation)
		explanation: Optional text explanation
		batch_number: Optional batch number
		expiry_date: Optional expiry date
	"""
	connector = RSDConnector()
	product = {"GTIN": gtin, "SN": serial_number}
	if batch_number:
		product["BN"] = batch_number
	if expiry_date:
		product["XD"] = expiry_date

	params = {
		"DR": deactivation_reason,
		"PRODUCTLIST": {"PRODUCT": [product]},
	}
	if explanation:
		params["EXPLANATION"] = explanation

	return connector.call_service(
		"DeactivationService", "DeactivationServiceRequest", params
	)


def deactivate_cancel(gtin, serial_number, batch_number=None, expiry_date=None):
	"""Cancel a deactivation."""
	connector = RSDConnector()
	product = {"GTIN": gtin, "SN": serial_number}
	if batch_number:
		product["BN"] = batch_number
	if expiry_date:
		product["XD"] = expiry_date

	return connector.call_service(
		"DeactivationCancelService",
		"DeactivationCancelServiceRequest",
		{"PRODUCTLIST": {"PRODUCT": [product]}},
	)
