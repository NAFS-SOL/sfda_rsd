# sfda_rsd/connectors/services/pts_service.py
"""SFDA DTTS Package Transfer services (bulk dispatch/receive).

Service URLs (per DTTS-ISD.PACKAGETRANSFER-1.0.2):
  PackageUpload:   {base}/ws/PackageUploadService/PackageUploadService?wsdl
  PackageDownload: {base}/ws/PackageDownloadService/PackageDownloadService?wsdl
  PackageQuery:    {base}/ws/PackageQueryService/PackageQueryService?wsdl
"""
from sfda_rsd.sfda_rsd.connectors.rsd_connector import RSDConnector


def package_upload(receiver_gln, file_data):
	"""Upload a file with product data for bulk dispatch (aggregation).

	Args:
		receiver_gln: Destination GLN (TOGLN)
		file_data: Base64-encoded zip file content (FILE)
	"""
	connector = RSDConnector()
	return connector.call_service(
		"PackageUploadService",
		"PackageUploadServiceRequest",
		{"TOGLN": receiver_gln, "FILE": file_data},
	)


def package_download(transfer_id):
	"""Download a product file sent to this stakeholder.

	Args:
		transfer_id: Transfer ID from package query
	"""
	connector = RSDConnector()
	return connector.call_service(
		"PackageDownloadService",
		"PackageDownloadServiceRequest",
		{"TRANSFERID": transfer_id},
	)


def package_query(from_gln=None, to_gln=None, get_all=False,
				  start_date=None, end_date=None):
	"""Check available packages for download.

	Args:
		from_gln: Filter by sender GLN
		to_gln: Filter by receiver GLN
		get_all: Return all packages (true/false)
		start_date: Filter start date
		end_date: Filter end date
	"""
	connector = RSDConnector()
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
