import frappe


def check_app_permission():
	"""Fuer add_to_apps_screen in hooks.py: wer die App-Kachel bzw. das
	App-Symbol im Desk sehen darf."""
	if frappe.session.user == "Administrator":
		return True
	roles = frappe.get_roles()
	return any(
		role in roles
		for role in ("System Manager", "Projects Manager", "Projects User", "Accounts User", "Employee")
	)
