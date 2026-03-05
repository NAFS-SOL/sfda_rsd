# sfda_rsd/config/sfda_rsd.py
from frappe import _


def get_data():
	return [
		{
			"label": _("SFDA RSD"),
			"icon": "fa fa-medkit",
			"items": [
				{
					"type": "doctype",
					"name": "RSD Settings",
					"label": _("RSD Settings"),
					"description": _("Configure SFDA RSD integration credentials and options"),
				},
				{
					"type": "doctype",
					"name": "RSD Transaction Log",
					"label": _("Transaction Log"),
					"description": _("View SOAP request/response logs"),
				},
				{
					"type": "doctype",
					"name": "RSD Notification Queue",
					"label": _("Notification Queue"),
					"description": _("Pending and failed RSD notifications"),
				},
				{
					"type": "doctype",
					"name": "RSD Drug Unit",
					"label": _("Drug Units"),
					"description": _("Track individual drug unit status"),
				},
			],
		},
	]
