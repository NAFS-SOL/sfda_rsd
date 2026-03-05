# sfda_rsd/connectors/soap_builder.py
"""
Raw SOAP 1.2 envelope builder for SFDA RSD.
Use this if WSDLs are unavailable or if you need full control over XML.
"""
import requests
from lxml import etree

SOAP12_NS = "http://www.w3.org/2003/05/soap-envelope"
WSSE_NS = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"

NSMAP = {
	"soap": SOAP12_NS,
	"wsse": WSSE_NS,
}


def build_soap_envelope(username, password, body_xml):
	"""Build a SOAP 1.2 envelope with WS-Security UsernameToken.

	Args:
		username (str): DTTS username
		password (str): DTTS password
		body_xml (str): Inner XML body content

	Returns:
		str: Complete SOAP envelope XML string
	"""
	envelope = f"""<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="{SOAP12_NS}"
               xmlns:wsse="{WSSE_NS}">
    <soap:Header>
        <wsse:Security>
            <wsse:UsernameToken>
                <wsse:Username>{username}</wsse:Username>
                <wsse:Password>{password}</wsse:Password>
            </wsse:UsernameToken>
        </wsse:Security>
    </soap:Header>
    <soap:Body>
        {body_xml}
    </soap:Body>
</soap:Envelope>"""

	return envelope


def send_soap_request(endpoint_url, username, password, body_xml, timeout=60):
	"""Send a raw SOAP 1.2 request to SFDA RSD.

	Args:
		endpoint_url (str): Full service endpoint URL
		username (str): DTTS username
		password (str): DTTS password
		body_xml (str): The SOAP body XML content
		timeout (int): Request timeout in seconds

	Returns:
		tuple: (response_xml_string, status_code)
	"""
	envelope = build_soap_envelope(username, password, body_xml)

	headers = {
		"Content-Type": "application/soap+xml; charset=utf-8",
	}

	response = requests.post(
		endpoint_url,
		data=envelope.encode("utf-8"),
		headers=headers,
		timeout=timeout,
		verify=True,
	)

	return response.text, response.status_code


def parse_soap_response(response_xml):
	"""Parse SOAP response XML and extract the body content.

	Returns:
		lxml.etree.Element: Body element, or raises on SOAP fault
	"""
	root = etree.fromstring(response_xml.encode("utf-8"))
	ns = {"soap": SOAP12_NS}

	# Check for SOAP Fault
	fault = root.find(".//soap:Fault", ns)

	if fault is not None:
		fault_code = fault.findtext(
			".//soap:Code/soap:Value", default="Unknown", namespaces=ns
		)
		fault_reason = fault.findtext(
			".//soap:Reason/soap:Text", default="Unknown error", namespaces=ns
		)
		raise Exception(f"SOAP Fault [{fault_code}]: {fault_reason}")

	body = root.find("soap:Body", ns)
	return body
