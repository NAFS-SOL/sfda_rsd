# sfda_rsd/connectors/services/query_service.py
"""SFDA DTTS Query/Reference services."""
import frappe
from sfda_rsd.connectors.rsd_connector import RSDConnector


def check_status(branch, gtin, serial_number, batch_number=None, expiry_date=None):
	"""Query the current status and ownership of a drug unit."""
	connector = RSDConnector(branch=branch)
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


def get_drug_list(branch, drug_status="-1"):
	"""Retrieve drugs registered in the SFDA system.

	DRUGSTATUS LOV per DTTS-DEF-1.0.2:
	  "-1" = ALL (default — full catalog)
	   "0" = PASSIVE
	   "1" = ACTIVE
	"""
	connector = RSDConnector(branch=branch)
	return connector.call_service(
		"DrugListService",
		"DrugListServiceRequest",
		{"DRUGSTATUS": str(drug_status)},
	)


def get_stakeholder_list(branch):
	"""Retrieve all stakeholders registered in the system."""
	connector = RSDConnector(branch=branch)
	return connector.call_service(
		"StakeholderListService", "StakeholderListServiceRequest", {}
	)


def get_city_list(branch):
	"""Retrieve all cities and regions."""
	connector = RSDConnector(branch=branch)
	return connector.call_service(
		"CityListService", "CityListServiceRequest", {}
	)


def get_country_list(branch):
	"""Retrieve country codes (required for Export operations)."""
	connector = RSDConnector(branch=branch)
	return connector.call_service(
		"CountryListService", "CountryListServiceRequest", {}
	)


def get_error_codes(branch, error_code=None):
	"""Retrieve error code descriptions."""
	connector = RSDConnector(branch=branch)
	params = {}
	if error_code:
		params["ERRORCODE"] = error_code
	return connector.call_service(
		"ErrorCodeListService", "ErrorCodeListServiceRequest", params
	)


def get_dispatch_detail(branch, notification_id):
	"""Query the contents of a dispatch notification."""
	connector = RSDConnector(branch=branch)
	return connector.call_service(
		"DispatchDetailService",
		"DispatchDetailServiceRequest",
		{"NOTIFICATIONID": notification_id},
	)


def sync_drug_list():
	"""Scheduled job: sync SFDA drug list for every enabled branch.

	Iterates every enabled RSD Settings record and fetches its drug list.
	No-op if there are zero enabled branches.
	"""
	branches = frappe.get_all(
		"RSD Settings",
		filters={"enabled": 1},
		fields=["branch"],
	)
	if not branches:
		return
	for row in branches:
		try:
			drugs = get_drug_list(branch=row.branch)
			frappe.logger().info(
				f"Synced {len(drugs) if drugs else 0} drugs from SFDA for branch {row.branch}"
			)
		except Exception as e:
			frappe.log_error(
				f"Drug list sync failed for branch {row.branch}: {e}",
				"RSD Drug Sync Error",
			)
