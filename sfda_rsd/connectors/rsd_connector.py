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
	"""Core SOAP client for SFDA RSD (DTTS) integration.

	Usage:
		connector = RSDConnector()
		response = connector.call_service("AcceptService", "AcceptServiceRequest", {
			"FROMGLN": "6281100000123",
			"PRODUCTLIST": {"PRODUCT": [{"GTIN": "06281100000123", "SN": "ABC123"}]},
		})
	"""

	def __init__(self):
		self.settings = frappe.get_single("RSD Settings")
		if not self.settings.enabled:
			frappe.throw("RSD Integration is not enabled. Enable it in RSD Settings.")

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
			session.verify = True
			session.timeout = self.timeout

			transport = Transport(session=session, timeout=self.timeout)

			settings = Settings(
				strict=False,
				xml_huge_tree=True,
				extra_http_headers={"Content-Type": "application/soap+xml; charset=utf-8"},
			)

			wsse = UsernameToken(self.username, self.password, use_digest=False)

			client = Client(
				wsdl=wsdl_url,
				wsse=wsse,
				transport=transport,
				settings=settings,
				plugins=[self.history],
			)

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
			operation = getattr(client.service, operation_name)
			response = operation(**params)

			request_xml = self._serialize_xml(self.history.last_sent)
			response_xml = self._serialize_xml(self.history.last_received)

			# Parse response codes from SFDA response
			rc_results = self._parse_response_codes(response)
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
			error_message = str(e)
			frappe.log_error(
				message=f"RSD Error: {e}\n\n{traceback.format_exc()}",
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
				gtin = getattr(prod, "GTIN", "") or ""
				sn = getattr(prod, "SN", "") or ""
				bn = getattr(prod, "BN", "") or ""
				rc = str(getattr(prod, "RC", ""))

				if rc in SFDA_SUCCESS_CODES:
					result["success_products"].append({"GTIN": gtin, "SN": sn, "BN": bn})
				else:
					result["has_errors"] = True
					errors.append(f"GTIN={gtin} SN={sn} RC={rc}")
					result["failed_products"].append({"GTIN": gtin, "SN": sn, "RC": rc})

			if errors:
				result["error_summary"] = "; ".join(errors[:5])

		except Exception as e:
			frappe.log_error(f"Failed to parse RSD response codes: {e}")

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
	"""Scheduled job: retry failed RSD notifications from the queue."""
	settings = frappe.get_single("RSD Settings")
	if not settings.enabled:
		return

	max_retries = settings.max_retries or 3

	queue_entries = frappe.get_all(
		"RSD Notification Queue",
		filters={"status": ["in", ["Failed", "Pending"]], "retry_count": ["<", max_retries]},
		fields=["name", "service_name", "operation", "parameters"],
		order_by="creation asc",
		limit=50,
	)

	if not queue_entries:
		return

	connector = RSDConnector()

	for entry in queue_entries:
		try:
			frappe.db.set_value(
				"RSD Notification Queue", entry.name, "status", "Processing"
			)
			params = frappe.parse_json(entry.parameters)
			connector.call_service(entry.service_name, entry.operation, params)
			frappe.db.set_value(
				"RSD Notification Queue", entry.name, "status", "Completed"
			)
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
