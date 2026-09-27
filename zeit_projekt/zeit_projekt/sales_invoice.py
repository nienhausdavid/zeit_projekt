import frappe
from frappe import _


@frappe.whitelist()
def get_billable_time_logs(customer, project=None, from_time=None, to_time=None):
	"""Wie ERPNexts get_projectwise_timesheet_data (inkl. dessen
	Rechtepruefung), aber nur Zeiten des Rechnungskunden - ohne Projektfilter
	kamen sonst die offenen Zeiten aller Kunden in die Rechnung.

	Zuordnung: Kunde des Projekts der Zeitbuchung, sonst Kunde des
	Zeitblatts. Zeiten ganz ohne Kunde werden nicht uebernommen, nur gezaehlt."""
	from erpnext.projects.doctype.timesheet.timesheet import get_projectwise_timesheet_data

	if not customer:
		frappe.throw(_("Bitte zuerst den Kunden der Rechnung wählen."))

	rows = get_projectwise_timesheet_data(project=project or None, from_time=from_time, to_time=to_time)
	if not rows:
		return {"rows": [], "skipped": 0}

	detail_project = dict(
		frappe.get_all(
			"Timesheet Detail",
			filters={"name": ["in", [r.name for r in rows]]},
			fields=["name", "project"],
			as_list=True,
		)
	)
	timesheet_customer = dict(
		frappe.get_all(
			"Timesheet",
			filters={"name": ["in", list({r.time_sheet for r in rows})]},
			fields=["name", "customer"],
			as_list=True,
		)
	)
	projects = list({p for p in detail_project.values() if p})
	project_customer = (
		dict(
			frappe.get_all(
				"Project", filters={"name": ["in", projects]}, fields=["name", "customer"], as_list=True
			)
		)
		if projects
		else {}
	)

	passend = []
	for row in rows:
		row_customer = project_customer.get(detail_project.get(row.name)) or timesheet_customer.get(
			row.time_sheet
		)
		if row_customer == customer:
			passend.append(row)

	return {"rows": passend, "skipped": len(rows) - len(passend)}
