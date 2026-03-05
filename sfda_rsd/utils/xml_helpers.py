# sfda_rsd/utils/xml_helpers.py
from lxml import etree


def extract_error_from_response(response_xml):
	"""Extract error details from an SFDA RSD SOAP response.

	The response typically contains a status code and list of products
	with individual success/error status.
	"""
	if not response_xml:
		return {"error": "Empty response"}

	try:
		root = etree.fromstring(
			response_xml.encode("utf-8") if isinstance(response_xml, str) else response_xml
		)

		# Look for common error patterns in RSD responses
		# Adjust XPath based on actual ISD response schema
		errors = []
		for elem in root.iter():
			if "ErrorCode" in elem.tag or "errorCode" in elem.tag:
				errors.append({
					"code": elem.text,
					"description": elem.getnext().text if elem.getnext() is not None else "",
				})

		return errors if errors else None
	except Exception as e:
		return {"parse_error": str(e)}
