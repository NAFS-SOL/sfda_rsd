# sfda_rsd/setup.py
"""
Custom field definitions created after migrate.

Adds RSD-specific fields to standard ERPNext DocTypes:
- Item: GTIN and tracking toggle
- Supplier/Customer/Warehouse: GLN number
- Batch: RSD supplied flag
"""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def after_migrate():
	"""Entry point called by hooks.py after_migrate."""
	create_rsd_custom_fields()


def create_rsd_custom_fields():
	"""Create custom fields on standard ERPNext DocTypes for RSD integration."""
	custom_fields = {
		"Item": [
			{
				"fieldname": "custom_rsd_section",
				"fieldtype": "Section Break",
				"label": "SFDA RSD",
				"insert_after": "barcodes",
				"collapsible": 1,
			},
			{
				"fieldname": "custom_gtin",
				"fieldtype": "Data",
				"label": "GTIN (14-digit)",
				"insert_after": "custom_rsd_section",
				"length": 14,
				"description": "Global Trade Item Number for SFDA RSD tracking",
			},
			{
				"fieldname": "custom_is_rsd_tracked",
				"fieldtype": "Check",
				"label": "Track in SFDA RSD",
				"insert_after": "custom_gtin",
				"default": "0",
				"description": "Enable to automatically notify SFDA when this item is supplied, dispatched, or sold",
			},
		],
		"Supplier": [
			{
				"fieldname": "custom_gln",
				"fieldtype": "Data",
				"label": "GLN Number",
				"insert_after": "supplier_name",
				"length": 13,
				"description": "Global Location Number for SFDA RSD",
			},
		],
		"Customer": [
			{
				"fieldname": "custom_gln",
				"fieldtype": "Data",
				"label": "GLN Number",
				"insert_after": "customer_name",
				"length": 13,
				"description": "Global Location Number for SFDA RSD",
			},
		],
		"Warehouse": [
			{
				"fieldname": "custom_gln",
				"fieldtype": "Data",
				"label": "GLN Number",
				"insert_after": "warehouse_name",
				"length": 13,
				"description": "Global Location Number for SFDA RSD",
			},
		],
		"Batch": [
			{
				"fieldname": "custom_rsd_supplied",
				"fieldtype": "Check",
				"label": "Supplied to RSD",
				"insert_after": "batch_id",
				"default": "0",
				"read_only": 1,
				"description": "Automatically set when batch is notified to SFDA RSD",
			},
		],
	}
	create_custom_fields(custom_fields, update=True)
