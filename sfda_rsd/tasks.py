# sfda_rsd/tasks.py
"""
Scheduler task wrappers called by hooks.py scheduler_events.
"""
import frappe


def retry_failed_notifications():
	"""Every 15 minutes: retry failed RSD notification queue entries."""
	from sfda_rsd.connectors.rsd_connector import retry_failed_notifications as _retry
	_retry()


def sync_drug_list():
	"""Daily: sync SFDA drug list to local database."""
	from sfda_rsd.connectors.services.query_service import sync_drug_list as _sync
	_sync()
