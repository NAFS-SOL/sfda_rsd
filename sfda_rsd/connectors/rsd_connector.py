# sfda_rsd/connectors/rsd_connector.py
import frappe
from frappe.utils import now_datetime
from lxml import etree
import zeep
from zeep import Client, Settings
from zeep.transports import Transport
from zeep.wsse.username import UsernameToken
from zeep.plugins import HistoryPlugin
from requests import Session
import traceback

from sfda_rsd.connectors.error_codes import get_error_description


# Response codes that indicate success per SFDA DTTS documentation
SFDA_SUCCESS_CODES = {"00000", "10201"}

# Maps service names to Drug Unit status values
SERVICE_STATUS_MAP = {
	"AcceptService": "Accepted",
	"AcceptBatchService": "Accepted",
	"PharmacySaleService": "Sold",
	"PharmacySaleCancelService": "Accepted",
	"DeactivationService": "Deactivated",
	"DeactivationCancelService": "Accepted",
	"DispatchService": "Dispatched",
	"DispatchBatchService": "Dispatched",
	"DispatchCancelService": "Accepted",
	"ReturnService": "Returned",
	"ReturnBatchService": "Returned",
	"TransferService": "Dispatched",
	"TransferBatchService": "Dispatched",
	"TransferCancelService": "Accepted",
	"SupplyService": "Supplied",
	"ExportService": "Exported",
	"ConsumeService": "Consumed",
}


class RSDConnector:
	"""Core SOAP client for SFDA RSD (DTTS) integration, scoped to a single branch.

	Usage:
		connector = RSDConnector(branch="Jeddah Main")
		response = connector.call_service("AcceptService", "AcceptServiceRequest", {
			"FROMGLN": "6281100000123",
			"PRODUCTLIST": {"PRODUCT": [{"GTIN": "06281100000123", "SN": "ABC123"}]},
		})
	"""

	def __init__(self, branch):
		if not branch:
			frappe.throw("Branch is required to instantiate RSDConnector")

		settings_name = frappe.db.get_value("RSD Settings", {"branch": branch}, "name")
		if not settings_name:
			frappe.throw(f"No RSD Settings configured for branch '{branch}'")

		self.settings = frappe.get_doc("RSD Settings", settings_name)
		if not self.settings.enabled:
			frappe.throw(f"RSD Integration is not enabled for branch '{branch}'.")

		self.branch = branch
		self.username = self.settings.username
		self.password = self.settings.get_password("password")
		self.gln = self.settings.stakeholder_gln
		self.timeout = self.settings.timeout_seconds or 60
		self.max_retries = self.settings.max_retries or 3
		self.history = HistoryPlugin()
		self._clients = {}

	def _get_client(self, service_name):
		"""Create or retrieve cached zeep SOAP client for a service."""
		if service_name not in self._clients:
			wsdl_url = self.settings.get_wsdl_url(service_name)

			session = Session()
			session.auth = (self.username, self.password)
			session.verify = True
			session.timeout = self.timeout

			transport = Transport(session=session, timeout=self.timeout)

			settings = Settings(
				strict=False,
				xml_huge_tree=True,
				extra_http_headers={"Content-Type": "application/soap+xml; charset=utf-8"},
			)

			wsse = UsernameToken(self.username, self.password, use_digest=False)

			# Fetch WSDL with explicit auth — some SFDA endpoints reject
			# standard HTTP Basic Auth but accept credentials in the URL session
			import requests
			from requests.auth import HTTPBasicAuth
			try:
				wsdl_response = requests.get(
					wsdl_url,
					auth=HTTPBasicAuth(self.username, self.password),
					timeout=self.timeout,
					verify=True,
				)
				wsdl_response.raise_for_status()
			except requests.exceptions.HTTPError:
				# Fallback: try without auth (some services may be open)
				wsdl_response = requests.get(wsdl_url, timeout=self.timeout, verify=True)
				wsdl_response.raise_for_status()

			# Parse WSDL from downloaded content instead of URL
			from io import BytesIO
			client = Client(
				wsdl=BytesIO(wsdl_response.content),
				wsse=wsse,
				transport=transport,
				settings=settings,
				plugins=[self.history],
			)
			# Set the WSDL URL as the service address (zeep needs this for actual SOAP calls)
			base_url = self.settings.get_base_url()
			service_url = f"{base_url}/ws/{service_name}/{service_name}"
			client.service._binding_options["address"] = service_url

			self._clients[service_name] = client

		return self._clients[service_name]

	def call_service(self, service_name, operation_name, params, log=True):
		"""Execute a SOAP operation and return the response.

		Args:
			service_name: WSDL service name, e.g. "AcceptService"
			operation_name: Operation/method name, e.g. "AcceptServiceRequest"
			params: Parameters for the SOAP operation (PRODUCTLIST structure)
			log: Whether to log the transaction

		Returns:
			dict: Parsed response from SFDA including per-product RC codes
		"""
		client = self._get_client(service_name)

		response = None
		request_xml = ""
		response_xml = ""
		status = "Success"
		error_message = ""

		try:
			# Try the requested operation name first; if not found,
			# auto-discover the first available operation in the WSDL
			# (most SFDA services expose exactly one operation).
			if hasattr(client.service, operation_name):
				operation = getattr(client.service, operation_name)
			else:
				available_ops = list(client.service._binding._operations.keys())
				if available_ops:
					operation = getattr(client.service, available_ops[0])
					frappe.logger().info(
						f"RSD: Operation '{operation_name}' not found in {service_name}. "
						f"Using '{available_ops[0]}' instead."
					)
				else:
					frappe.throw(f"No operations found in WSDL for {service_name}")
			response = operation(**params)

			request_xml = self._serialize_xml(self.history.last_sent)
			response_xml = self._serialize_xml(self.history.last_received)

			# Parse response codes from raw XML (reliable for all services)
			rc_results = self._parse_response_codes_from_xml(response_xml)
			if rc_results.get("has_errors"):
				status = "Error"
				error_message = rc_results.get("error_summary", "Some products failed")

			# Update Drug Unit status for successful products
			if rc_results.get("success_products"):
				self._update_drug_units(service_name, rc_results["success_products"])

		except zeep.exceptions.Fault as fault:
			status = "Error"
			error_message = str(fault)
			request_xml = self._serialize_xml(self.history.last_sent)
			response_xml = self._serialize_xml(self.history.last_received)
			frappe.log_error(
				message=f"SOAP Fault: {fault}\n\n{traceback.format_exc()}",
				title=f"RSD {operation_name} Error",
			)

		except Exception as e:
			status = "Error"
			raw_error = str(e)
			request_xml = self._serialize_xml(self.history.last_sent)
			response_xml = self._serialize_xml(self.history.last_received)

			# zeep raises an opaque "'NoneType' object has no attribute 'getroottree'"
			# when SFDA returns an empty / non-XML body. Translate that to something
			# actionable — the raw message tells the user nothing about the cause.
			if "getroottree" in raw_error or not (response_xml or "").strip():
				error_message = (
					f"SFDA returned an empty response for {service_name}. "
					"The service may not be available for this stakeholder in the "
					"current environment. Contact SFDA support (Tracking.drug@sfda.gov.sa) "
					"quoting the RSD Transaction Log entry."
				)
			else:
				error_message = raw_error

			frappe.log_error(
				message=f"RSD Error: {raw_error}\n\n{traceback.format_exc()}",
				title=f"RSD {operation_name} Error",
			)

		finally:
			if log and self.settings.log_xml:
				self._log_transaction(
					service_name=service_name,
					operation=operation_name,
					request_xml=request_xml,
					response_xml=response_xml,
					status=status,
					error_message=error_message,
					params=params,
				)

		if status == "Error" and not response:
			frappe.throw(f"RSD {operation_name} failed: {error_message}")

		return response

	def _parse_response_codes(self, response):
		"""Parse per-product RC (Response Code) from SFDA response.

		SFDA returns RC per product in the PRODUCTLIST.
		Success codes: 00000, 10201.
		"""
		result = {
			"has_errors": False,
			"success_products": [],
			"failed_products": [],
			"error_summary": "",
		}

		if not response:
			return result

		try:
			# Response may be a zeep object; try to access PRODUCTLIST
			product_list = None

			if hasattr(response, "PRODUCTLIST"):
				product_list = response.PRODUCTLIST
			elif isinstance(response, dict) and "PRODUCTLIST" in response:
				product_list = response["PRODUCTLIST"]

			# Also check for SNRESPONSELIST (Supply/Import services)
			if not product_list and hasattr(response, "SNRESPONSELIST"):
				sn_list = response.SNRESPONSELIST
				if sn_list:
					for sn_resp in (sn_list if isinstance(sn_list, list) else [sn_list]):
						sn = getattr(sn_resp, "SN", None)
						rc = str(getattr(sn_resp, "RC", ""))
						gtin = getattr(response, "GTIN", "")
						if rc in SFDA_SUCCESS_CODES:
							result["success_products"].append({"GTIN": gtin, "SN": sn})
						else:
							result["has_errors"] = True
							result["failed_products"].append({"SN": sn, "RC": rc})
				return result

			if not product_list:
				return result

			products = product_list if isinstance(product_list, list) else [product_list]
			# Sometimes PRODUCTLIST contains PRODUCT as nested
			if hasattr(products[0], "PRODUCT") if products else False:
				products = products[0].PRODUCT
				if not isinstance(products, list):
					products = [products]

			errors = []
			for prod in products:
				gtin = str(getattr(prod, "GTIN", "") or "")
				sn = str(getattr(prod, "SN", "") or "")
				bn = str(getattr(prod, "BN", "") or "")
				# RC can be nested or accessed via dict — try multiple ways
				rc = getattr(prod, "RC", None)
				if rc is None and isinstance(prod, dict):
					rc = prod.get("RC")
				if rc is None and hasattr(prod, "__dict__"):
					# Try accessing as dict keys for zeep objects
					try:
						rc = prod["RC"]
					except (KeyError, TypeError):
						pass
				rc = str(rc) if rc is not None else ""

				if rc in SFDA_SUCCESS_CODES:
					result["success_products"].append({"GTIN": gtin, "SN": sn, "BN": bn})
				else:
					result["has_errors"] = True
					errors.append(f"GTIN={gtin} BN={bn} SN={sn} RC={rc}")
					result["failed_products"].append({"GTIN": gtin, "SN": sn, "BN": bn, "RC": rc})

			if errors:
				result["error_summary"] = "; ".join(errors[:5])

		except Exception as e:
			frappe.log_error(f"Failed to parse RSD response codes: {e}")

		return result

	def _parse_response_codes_from_xml(self, response_xml):
		"""Fallback: parse RC codes directly from response XML string.

		Used when zeep's object model can't access RC attributes (batch services).
		"""
		result = {
			"has_errors": False,
			"success_products": [],
			"failed_products": [],
			"error_summary": "",
		}
		try:
			root = etree.fromstring(response_xml.encode("utf-8") if isinstance(response_xml, str) else response_xml)
			products = root.findall(".//{*}PRODUCT")
			errors = []
			for prod in products:
				gtin = (prod.findtext("{*}GTIN") or prod.findtext("GTIN") or "").strip()
				sn = (prod.findtext("{*}SN") or prod.findtext("SN") or "").strip()
				bn = (prod.findtext("{*}BN") or prod.findtext("BN") or "").strip()
				rc = (prod.findtext("{*}RC") or prod.findtext("RC") or "").strip()

				if rc in SFDA_SUCCESS_CODES:
					result["success_products"].append({"GTIN": gtin, "SN": sn, "BN": bn})
				else:
					result["has_errors"] = True
					desc = get_error_description(rc)
					errors.append(f"GTIN={gtin} BN={bn} SN={sn} RC={rc}: {desc}")
					result["failed_products"].append({"GTIN": gtin, "SN": sn, "BN": bn, "RC": rc, "description": desc})
			if errors:
				result["error_summary"] = "; ".join(errors[:5])
		except Exception as e:
			frappe.log_error(f"Failed to parse RSD response XML: {e}")
		return result

	def _update_drug_units(self, service_name, success_products):
		"""Update RSD Drug Unit status after successful SFDA notifications."""
		new_status = SERVICE_STATUS_MAP.get(service_name)
		if not new_status:
			return

		now = now_datetime()
		for prod in success_products:
			gtin = prod.get("GTIN")
			sn = prod.get("SN")
			if not gtin or not sn:
				continue

			try:
				existing = frappe.db.get_value(
					"RSD Drug Unit",
					{"gtin": gtin, "serial_number": sn},
					"name",
				)
				if existing:
					frappe.db.set_value("RSD Drug Unit", existing, {
						"status": new_status,
						"last_notification_type": service_name,
						"last_notification_at": now,
						"current_holder_gln": self.gln,
					})
				else:
					# Create new drug unit entry
					du = frappe.get_doc({
						"doctype": "RSD Drug Unit",
						"gtin": gtin,
						"serial_number": sn,
						"batch_number": prod.get("BN", ""),
						"status": new_status,
						"last_notification_type": service_name,
						"last_notification_at": now,
						"current_holder_gln": self.gln,
					})
					du.insert(ignore_permissions=True)
			except Exception as e:
				frappe.log_error(f"Failed to update RSD Drug Unit: {e}")

		frappe.db.commit()

	def _serialize_xml(self, envelope):
		"""Convert zeep history envelope to pretty-printed XML string."""
		try:
			if envelope and hasattr(envelope, "get"):
				return etree.tostring(
					envelope.get("envelope"),
					pretty_print=True,
					encoding="unicode",
				)
			elif envelope:
				return etree.tostring(envelope, pretty_print=True, encoding="unicode")
		except Exception:
			return str(envelope) if envelope else ""
		return ""

	def _log_transaction(
		self, service_name, operation, request_xml, response_xml, status, error_message, params
	):
		"""Create an RSD Transaction Log entry."""
		try:
			log = frappe.get_doc({
				"doctype": "RSD Transaction Log",
				"branch": self.branch,
				"service_name": service_name,
				"operation": operation,
				"request_xml": request_xml,
				"response_xml": response_xml,
				"status": status,
				"error_message": error_message,
				"parameters": frappe.as_json(params),
				"timestamp": now_datetime(),
				"stakeholder_gln": self.gln,
			})
			log.insert(ignore_permissions=True)
			frappe.db.commit()
		except Exception as e:
			frappe.log_error(f"Failed to log RSD transaction: {e}")


def retry_failed_notifications():
	"""Scheduled job: retry failed RSD notifications from the queue.

	Per-branch: each queue entry carries its own `branch`. We load that branch's
	RSD Settings to instantiate the connector. Entries without a branch, or
	whose branch config is missing/disabled, are marked Failed without retry.
	"""
	queue_entries = frappe.get_all(
		"RSD Notification Queue",
		filters={"status": ["in", ["Failed", "Pending"]]},
		fields=["name", "branch", "service_name", "operation", "parameters", "retry_count"],
		order_by="creation asc",
		limit=50,
	)

	if not queue_entries:
		return

	# Cache connectors per branch so we don't re-fetch settings for every entry
	connectors = {}

	def _get_connector(branch):
		if branch not in connectors:
			connectors[branch] = RSDConnector(branch=branch)
		return connectors[branch]

	for entry in queue_entries:
		# Entries without branch can't be retried — mark Failed and move on
		if not entry.branch:
			frappe.db.set_value("RSD Notification Queue", entry.name, {
				"status": "Failed",
				"last_error": "Queue entry has no branch; cannot resolve credentials",
			})
			continue

		# Fetch per-branch max_retries via the settings record
		settings_name = frappe.db.get_value("RSD Settings", {"branch": entry.branch}, "name")
		if not settings_name:
			frappe.db.set_value("RSD Notification Queue", entry.name, {
				"status": "Failed",
				"last_error": f"No RSD Settings for branch '{entry.branch}'",
			})
			continue
		branch_settings = frappe.db.get_value(
			"RSD Settings", settings_name,
			["enabled", "max_retries"], as_dict=True
		)
		if not branch_settings.enabled:
			frappe.db.set_value("RSD Notification Queue", entry.name, {
				"status": "Failed",
				"last_error": f"RSD disabled for branch '{entry.branch}'",
			})
			continue
		max_retries = branch_settings.max_retries or 3
		if (entry.retry_count or 0) >= max_retries:
			continue

		try:
			connector = _get_connector(entry.branch)

			frappe.db.set_value(
				"RSD Notification Queue", entry.name, "status", "Processing"
			)
			params = frappe.parse_json(entry.parameters)
			connector.call_service(entry.service_name, entry.operation, params)

			# Check the transaction log for this branch/service to see if SFDA returned errors
			latest_log = frappe.get_all(
				"RSD Transaction Log",
				filters={"service_name": entry.service_name, "branch": entry.branch},
				fields=["status", "error_message"],
				order_by="creation desc",
				limit=1,
			)
			if latest_log and latest_log[0].status == "Error":
				retry_count = frappe.db.get_value(
					"RSD Notification Queue", entry.name, "retry_count"
				) or 0
				frappe.db.set_value("RSD Notification Queue", entry.name, {
					"status": "Failed",
					"retry_count": retry_count + 1,
					"last_error": latest_log[0].error_message or "SFDA returned error RC",
				})
			else:
				frappe.db.set_value(
					"RSD Notification Queue", entry.name, "status", "Completed"
				)

			# Update RSD status on the source document
			ref_dt = frappe.db.get_value("RSD Notification Queue", entry.name, "reference_doctype")
			ref_dn = frappe.db.get_value("RSD Notification Queue", entry.name, "reference_name")
			if ref_dt and ref_dn:
				new_status = "Failed" if (latest_log and latest_log[0].status == "Error") else "Sent"
				try:
					frappe.db.set_value(ref_dt, ref_dn, "custom_rsd_status", new_status, update_modified=False)
				except Exception:
					pass

		except Exception:
			retry_count = frappe.db.get_value(
				"RSD Notification Queue", entry.name, "retry_count"
			) or 0
			frappe.db.set_value("RSD Notification Queue", entry.name, {
				"status": "Failed",
				"retry_count": retry_count + 1,
				"last_error": frappe.get_traceback()[:2000],
			})

	frappe.db.commit()
