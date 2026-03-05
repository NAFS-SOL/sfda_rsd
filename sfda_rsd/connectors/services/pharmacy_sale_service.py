# sfda_rsd/connectors/services/pharmacy_sale_service.py
"""SFDA DTTS Pharmacy Sale services.

Service URLs (per DTTS-ISD.PHARMACY_SALE-1.0.2):
  PharmacySale:       {base}/ws/PharmacySaleService/PharmacySaleService?wsdl
  PharmacySaleCancel: {base}/ws/PharmacySaleCancelService/PharmacySaleCancelService?wsdl
"""
from sfda_rsd.sfda_rsd.connectors.rsd_connector import RSDConnector


def pharmacy_sale(products, to_gln="0000000000000", prescription_id=None,
				  prescription_date=None, doctor_id=None, patient_national_id=None):
	"""Record a pharmacy sale of drugs to a patient.

	Args:
		products: List of dicts with keys: gtin, serial_number, batch_number (opt), expiry_date (opt)
		to_gln: GLN of reimbursement agency, or "0000000000000" for direct patient sale
		prescription_id: Prescription reference (None for OTC sales)
		prescription_date: Date of prescription (YYYY-MM-DD)
		doctor_id: Optional doctor identifier
		patient_national_id: Optional patient national ID
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

	params = {
		"TOGLN": to_gln,
		"PRODUCTLIST": {"PRODUCT": product_list},
	}

	if prescription_id:
		params["PRESCRIPTIONID"] = prescription_id
	if prescription_date:
		params["PRESCRIPTIONDATE"] = prescription_date
	if doctor_id:
		params["DOCTORID"] = doctor_id
	if patient_national_id:
		params["PATIENTNATIONALID"] = patient_national_id

	return connector.call_service(
		"PharmacySaleService", "PharmacySaleServiceRequest", params
	)


def pharmacy_sale_cancel(products, to_gln="0000000000000", prescription_id=None):
	"""Cancel a pharmacy sale."""
	connector = RSDConnector()

	product_list = []
	for p in products:
		prod = {"GTIN": p["gtin"], "SN": p["serial_number"]}
		if p.get("batch_number"):
			prod["BN"] = p["batch_number"]
		if p.get("expiry_date"):
			prod["XD"] = p["expiry_date"]
		product_list.append(prod)

	params = {
		"TOGLN": to_gln,
		"PRODUCTLIST": {"PRODUCT": product_list},
	}
	if prescription_id:
		params["PRESCRIPTIONID"] = prescription_id

	return connector.call_service(
		"PharmacySaleCancelService", "PharmacySaleCancelServiceRequest", params
	)
