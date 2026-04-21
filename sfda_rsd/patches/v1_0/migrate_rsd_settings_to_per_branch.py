# sfda_rsd/patches/v1_0/migrate_rsd_settings_to_per_branch.py
"""Patch: RSD Settings singleton → per-branch doctype.

The `RSD Settings` doctype changed from singleton to a regular doctype
keyed by Branch. Old singleton row (if any) cannot be reused because the
new doctype requires a branch value.

This patch:
  1. Logs the old singleton values to the Error Log (WARNING) so the
	 admin can re-enter them per branch.
  2. Drops any `RSD Notification Queue` rows without a branch, since
	 the new retry job can't reconstruct credentials for them.
  3. Does NOT create any new RSD Settings records — user decided
	 (during plan approval) to recreate branch records manually.
"""
import frappe


def execute():
	# 1. Read and log any pre-existing singleton data
	try:
		old = frappe.db.sql(
			"""SELECT field, value FROM `tabSingles`
			   WHERE doctype = 'RSD Settings'""",
			as_dict=True,
		)
		if old:
			dump = {row["field"]: row["value"] for row in old}
			# Mask password in the dump
			if "password" in dump:
				dump["password"] = "<redacted>"
			frappe.log_error(
				message=(
					"RSD Settings is now per-branch. "
					"The old singleton values below were preserved for reference — "
					"recreate RSD Settings records per Branch with these credentials "
					"(or updated ones).\n\n"
					+ frappe.as_json(dump, indent=2)
				),
				title="RSD Settings migration — old singleton values",
			)
			# Clear the old singleton rows so Frappe doesn't try to hydrate them
			frappe.db.sql("DELETE FROM `tabSingles` WHERE doctype = 'RSD Settings'")
	except Exception as e:
		frappe.log_error(
			message=f"Failed to capture old RSD Settings singleton: {e}",
			title="RSD Settings migration",
		)

	# 2. Drop queue entries that have no branch (unreplayable)
	try:
		deleted = frappe.db.sql(
			"""DELETE FROM `tabRSD Notification Queue`
			   WHERE branch IS NULL OR branch = ''"""
		)
		if deleted:
			frappe.logger().info(
				"RSD migration: purged queue entries without branch"
			)
	except Exception:
		# Queue table may not have the branch column yet on very old setups
		pass

	frappe.db.commit()
