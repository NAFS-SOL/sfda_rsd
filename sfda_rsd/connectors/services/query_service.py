# sfda_rsd/connectors/services/query_service.py
"""SFDA DTTS Query/Reference services.

Service URLs:
  CheckStatus:     {base}/ws/CheckStatusService/CheckStatusService?wsdl
  DrugList:        {base}/ws/DrugListService/DrugListService?wsdl
  StakeholderList: {base}/ws/StakeholderListService/StakeholderListService?wsdl
  CityList:        {base}/ws/CityListService/CityListService?wsdl
  CountryList:     {base}/ws/CountryListService/CountryListService?wsdl
  ErrorCodeList:   {base}/ws/ErrorCodeListService/ErrorCodeListService?wsdl
  DispatchDetail:  {base}/ws/DispatchDetailService/DispatchDetailService?wsdl
"""
import frappe
from sfda_rsd.connectors.rsd_connector import RSDConnector


def check_status(gtin, serial_number, batch_number=None, expiry_date=None):
	"""Query the current status and ownership of a drug unit."""
	connector = RSDConnector()
	product = {"GTIN": gtin, "SN": serial_number}
	if batch_number:
		product["BN"] = batch_number
	if expiry_date:
		product["XD"] = expiry_date

	return connector.call_service(
		"CheckStatusService",
		"CheckStatusServiceRequest",
		{"PRODUCTLIST": {"PRODUCT": [product]}},
	)


def get_drug_list(drug_status="-1"):
	"""Retrieve drugs registered in the SFDA system.

	DRUGSTATUS LOV per DTTS-DEF-1.0.2:
	  "-1" = ALL (default — full catalog)
	   "0" = PASSIVE
	   "1" = ACTIVE
	"""
	connector = RSDConnector()
	return connector.call_service(
		"DrugListService",
		"DrugListServiceRequest",
		{"DRUGSTATUS": str(drug_status)},
	)


def get_stakeholder_list():
	"""Retrieve all stakeholders registered in the system."""
	connector = RSDConnector()
	return connector.call_service(
		"StakeholderListService", "StakeholderListServiceRequest", {}
	)


def get_city_list():
	"""Retrieve all cities and regions."""
	connector = RSDConnector()
	return connector.call_service(
		"CityListService", "CityListServiceRequest", {}
	)


def get_country_list():
	"""Retrieve country codes (required for Export operations)."""
	connector = RSDConnector()
	return connector.call_service(
		"CountryListService", "CountryListServiceRequest", {}
	)


def get_error_codes(error_code=None):
	"""Retrieve error code descriptions."""
	connector = RSDConnector()
	params = {}
	if error_code:
		params["ERRORCODE"] = error_code
	return connector.call_service(
		"ErrorCodeListService", "ErrorCodeListServiceRequest", params
	)


def get_dispatch_detail(notification_id):
	"""Query the contents of a dispatch notification."""
	connector = RSDConnector()
	return connector.call_service(
		"DispatchDetailService",
		"DispatchDetailServiceRequest",
		{"NOTIFICATIONID": notification_id},
	)


def sync_drug_list():
	"""Scheduled job: sync SFDA drug list to local database."""
	try:
		drugs = get_drug_list()
		frappe.logger().info(f"Synced {len(drugs) if drugs else 0} drugs from SFDA")
	except Exception as e:
		frappe.log_error(f"Drug list sync failed: {e}", "RSD Drug Sync Error")
