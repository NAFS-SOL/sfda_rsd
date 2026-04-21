# sfda_rsd/connectors/services/pts_service.py
"""SFDA DTTS Package Transfer services (bulk dispatch/receive)."""
from sfda_rsd.connectors.rsd_connector import RSDConnector


def package_upload(branch, receiver_gln, file_data):
	"""Upload a file with product data for bulk dispatch (aggregation)."""
	connector = RSDConnector(branch=branch)
	return connector.call_service(
		"PackageUploadService",
		"PackageUploadServiceRequest",
		{"TOGLN": receiver_gln, "FILE": file_data},
	)


def package_download(branch, transfer_id):
	"""Download a product file sent to this stakeholder."""
	connector = RSDConnector(branch=branch)
	return connector.call_service(
		"PackageDownloadService",
		"PackageDownloadServiceRequest",
		{"TRANSFERID": transfer_id},
	)


def package_query(branch, from_gln=None, to_gln=None, get_all=False,
				  start_date=None, end_date=None):
	"""Check available packages for download."""
	connector = RSDConnector(branch=branch)
	params = {}
	if from_gln:
		params["FROMGLN"] = from_gln
	if to_gln:
		params["TOGLN"] = to_gln
	if get_all:
		params["GETALL"] = "true"
	if start_date:
		params["STARTDATE"] = start_date
	if end_date:
		params["ENDDATE"] = end_date

	return connector.call_service(
		"PackageQueryService",
		"PackageQueryServiceRequest",
		params,
	)
