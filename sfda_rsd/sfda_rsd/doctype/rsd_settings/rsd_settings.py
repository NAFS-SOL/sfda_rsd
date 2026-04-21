# sfda_rsd/sfda_rsd/doctype/rsd_settings/rsd_settings.py
import frappe
from frappe.model.document import Document


class RSDSettings(Document):
	"""Per-branch RSD configuration. One record per Branch."""

	def validate(self):
		if not self.branch:
			frappe.throw("Branch is required")
		if self.enabled and not self.username:
			frappe.throw("DTTS Username is required when RSD is enabled")
		if self.enabled and not self.password:
			frappe.throw("DTTS Password is required when RSD is enabled")
		if self.enabled and not self.stakeholder_gln:
			frappe.throw("Stakeholder GLN is required when RSD is enabled")
		if self.stakeholder_gln and len(self.stakeholder_gln) != 13:
			frappe.throw("Stakeholder GLN must be exactly 13 digits")
		if self.pharmacy_sale_togln and len(self.pharmacy_sale_togln) != 13:
			frappe.throw("Pharmacy Sale TOGLN must be exactly 13 digits")

	def get_base_url(self):
		if self.environment == "Test":
			return "https://tandttest.sfda.gov.sa"
		return "https://rsd.sfda.gov.sa"

	def get_wsdl_url(self, service_name):
		"""Construct WSDL URL for a given service.

		SFDA pattern: {base}/ws/{ServiceName}/{ServiceName}?wsdl
		Example: https://rsd.sfda.gov.sa/ws/AcceptService/AcceptService?wsdl
		"""
		base = self.get_base_url()
		return f"{base}/ws/{service_name}/{service_name}?wsdl"


@frappe.whitelist()
def test_rsd_connection(branch):
	"""Test SFDA RSD connection for a specific branch using zeep SOAP client.

	Tests three things in sequence:
	1. Network connectivity — can we reach the SFDA server?
	2. WSDL fetch — can zeep download and parse the WSDL (with auth)?
	3. SOAP call — can we execute a read-only ErrorCodeList request?
	"""
	if not branch:
		frappe.throw("Branch is required")

	settings_name = frappe.db.get_value("RSD Settings", {"branch": branch}, "name")
	if not settings_name:
		frappe.throw(f"No RSD Settings configured for branch '{branch}'")
	settings = frappe.get_doc("RSD Settings", settings_name)

	if not settings.enabled:
		frappe.throw(f"RSD Integration is not enabled for branch '{branch}'. Enable it first.")

	results = {
		"branch": branch,
		"environment": settings.environment,
		"base_url": settings.get_base_url(),
		"wsdl_url": settings.get_wsdl_url("ErrorCodeListService"),
		"steps": [],
	}

	# Step 1: Test basic network connectivity to the SFDA server
	import requests
	try:
		resp = requests.get(
			settings.get_base_url(),
			timeout=settings.timeout_seconds or 30,
			allow_redirects=True,
		)
		results["steps"].append({
			"step": "Network Connectivity",
			"status": "Pass",
			"message": f"Server reachable at {settings.get_base_url()} (HTTP {resp.status_code})",
		})
	except requests.exceptions.ConnectionError:
		results["steps"].append({
			"step": "Network Connectivity",
			"status": "Fail",
			"message": f"Cannot connect to {settings.get_base_url()}. Check network/firewall.",
		})
		results["overall"] = "Fail"
		return results
	except requests.exceptions.Timeout:
		results["steps"].append({
			"step": "Network Connectivity",
			"status": "Fail",
			"message": f"Connection timed out after {settings.timeout_seconds}s.",
		})
		results["overall"] = "Fail"
		return results

	# Step 2 & 3: Test WSDL fetch + SOAP call via zeep (zeep handles auth for WSDL fetch)
	try:
		from sfda_rsd.connectors.rsd_connector import RSDConnector
		connector = RSDConnector(branch=branch)

		# _get_client fetches and parses the WSDL (with WS-Security credentials)
		client = connector._get_client("ErrorCodeListService")
		results["steps"].append({
			"step": "WSDL Fetch",
			"status": "Pass",
			"message": f"WSDL loaded and parsed successfully",
		})
	except Exception as e:
		error_msg = str(e)
		if "ConnectionError" in error_msg or "Timeout" in error_msg:
			msg = f"Cannot fetch WSDL: {error_msg}"
		elif "401" in error_msg or "403" in error_msg:
			msg = f"Authentication failed fetching WSDL. Check username/password. Error: {error_msg}"
		else:
			msg = f"Failed to load WSDL: {error_msg}"
		results["steps"].append({
			"step": "WSDL Fetch",
			"status": "Fail",
			"message": msg,
		})
		results["overall"] = "Fail"
		return results

	# Step 3: Execute a read-only SOAP call to verify credentials work end-to-end
	try:
		response = connector.call_service(
			"ErrorCodeListService",
			"ErrorCodeListServiceRequest",
			{},
			log=False,
		)
		if response is not None:
			results["steps"].append({
				"step": "SOAP Call",
				"status": "Pass",
				"message": "Credentials accepted. SOAP call returned successfully.",
			})
		else:
			results["steps"].append({
				"step": "SOAP Call",
				"status": "Fail",
				"message": "SOAP call returned empty response.",
			})
			results["overall"] = "Fail"
			return results
	except Exception as e:
		error_msg = str(e)
		if "Authentication" in error_msg or "security" in error_msg.lower() or "401" in error_msg:
			msg = f"Authentication failed. Check username/password. Error: {error_msg}"
		else:
			msg = f"SOAP call failed: {error_msg}"
		results["steps"].append({
			"step": "SOAP Call",
			"status": "Fail",
			"message": msg,
		})
		results["overall"] = "Fail"
		return results

	results["overall"] = "Pass"
	return results
