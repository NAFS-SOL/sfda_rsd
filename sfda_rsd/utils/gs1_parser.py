# sfda_rsd/utils/gs1_parser.py
import re


def parse_gs1_datamatrix(barcode_data):
	"""Parse a GS1 DataMatrix barcode string into its components.

	GS1 Application Identifiers used in SFDA:
	(01) = GTIN (14 digits)
	(21) = Serial Number (variable length)
	(17) = Expiry Date (YYMMDD)
	(10) = Batch/Lot Number (variable length)

	Args:
		barcode_data (str): Raw scanned barcode data (with or without FNC1/GS separators)

	Returns:
		dict: Parsed components {gtin, serial_number, expiry_date, batch_number}
	"""
	# Remove any leading FNC1 character (often ]d2 or similar)
	data = re.sub(r"^(\]d2|\]C1|\x1d)", "", barcode_data)

	result = {
		"gtin": None,
		"serial_number": None,
		"expiry_date": None,
		"batch_number": None,
	}

	# Pattern: AI(01) GTIN is always 14 digits (fixed length)
	gtin_match = re.search(r"01(\d{14})", data)
	if gtin_match:
		result["gtin"] = gtin_match.group(1)

	# Pattern: AI(21) Serial Number (variable length, ends at GS or end)
	sn_match = re.search(r"21([^\x1d]+)", data)
	if sn_match:
		result["serial_number"] = sn_match.group(1)

	# Pattern: AI(17) Expiry Date (6 digits YYMMDD, fixed length)
	xd_match = re.search(r"17(\d{6})", data)
	if xd_match:
		yymmdd = xd_match.group(1)
		yy = int(yymmdd[:2])
		mm = yymmdd[2:4]
		dd = yymmdd[4:6]
		year = 2000 + yy  # Assumes 20xx century
		result["expiry_date"] = f"{year}-{mm}-{dd}"

	# Pattern: AI(10) Batch Number (variable length, ends at GS or end)
	bn_match = re.search(r"10([^\x1d]+)", data)
	if bn_match:
		result["batch_number"] = bn_match.group(1)

	return result


def validate_gtin(gtin):
	"""Validate a GTIN-14 check digit."""
	if not gtin or len(gtin) != 14 or not gtin.isdigit():
		return False

	digits = [int(d) for d in gtin]
	total = sum(d * (3 if i % 2 else 1) for i, d in enumerate(digits[:-1]))
	check = (10 - (total % 10)) % 10
	return check == digits[-1]
