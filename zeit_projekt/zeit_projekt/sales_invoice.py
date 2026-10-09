import frappe
from frappe import _
from frappe.utils import getdate


@frappe.whitelist()
def get_billable_time_logs(customer, project=None, from_time=None, to_time=None, sales_order=None):
	"""Fuer den Zeitimport der Ausgangsrechnung: offene Zeitbuchungen und
	abzurechnende Fahrt-Kilometer des Rechnungskunden.

	Zeiten wie ERPNexts get_projectwise_timesheet_data (inkl. dessen
	Rechtepruefung), aber nur die des Rechnungskunden: Kunde des Projekts der
	Zeitbuchung, sonst Kunde des Zeitblatts. Zeiten ganz ohne Kunde werden
	nicht uebernommen, nur gezaehlt. Mit sales_order nur Zeiten und Fahrten
	dieses Auftrags (Feld custom_sales_order, gesetzt von Kundeneinsatz und
	Fahrt)."""
	from erpnext.projects.doctype.timesheet.timesheet import get_projectwise_timesheet_data

	if not customer:
		frappe.throw(_("Bitte zuerst den Kunden der Rechnung wählen."))

	rows = get_projectwise_timesheet_data(project=project or None, from_time=from_time, to_time=to_time) or []
	customer_of = _row_customers(rows)
	passend = [row for row in rows if customer_of.get(row.name) == customer]
	uebersprungen = len(rows) - len(passend)
	_set_sales_orders(passend)
	if sales_order:
		passend = [row for row in passend if row.custom_sales_order == sales_order]

	return {
		"rows": passend,
		"skipped": uebersprungen,
		"kilometers": _open_kilometers(customer, project, from_time, to_time, sales_order),
	}


def _set_sales_orders(rows):
	"""Auftrag je Zeitbuchung. sales_order nur bei gebuchtem Auftrag - die
	Rechnung uebernimmt ihn in ihre Position (Feld sales_order), und ERPNext
	vergleicht dabei Kunde, Firma, Projekt und Waehrung mit dem Auftrag. Das
	Projekt des Auftrags (so_project) prueft das Formular gegen das der
	Rechnung."""
	if not rows:
		return
	auftrag_of = dict(
		frappe.get_all(
			"Timesheet Detail",
			filters={"name": ["in", [r.name for r in rows]]},
			fields=["name", "custom_sales_order"],
			as_list=True,
		)
	)
	auftraege = {a for a in auftrag_of.values() if a}
	info = (
		{
			a.name: a
			for a in frappe.get_all(
				"Sales Order", filters={"name": ["in", list(auftraege)]}, fields=["name", "docstatus", "project"]
			)
		}
		if auftraege
		else {}
	)
	for row in rows:
		row.custom_sales_order = auftrag_of.get(row.name)
		so = info.get(row.custom_sales_order)
		row.sales_order = so.name if so and so.docstatus == 1 else None
		row.so_project = so.project if so else None


def _row_customers(rows):
	"""Timesheet-Detail-Name -> Kunde (Projektkunde vor Zeitblattkunde)."""
	if not rows:
		return {}
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
		dict(frappe.get_all("Project", filters={"name": ["in", projects]}, fields=["name", "customer"], as_list=True))
		if projects
		else {}
	)
	return {
		r.name: project_customer.get(detail_project.get(r.name)) or timesheet_customer.get(r.time_sheet)
		for r in rows
	}


def _open_kilometers(customer, project, from_time, to_time, sales_order=None):
	"""Gebuchte Fahrten des Kunden mit "Kilometer abrechnen", die noch in
	keiner gebuchten Rechnung stehen."""
	from zeit_projekt.fahrtenbuch.fahrtenbuch import positionstext

	filters = {
		"docstatus": 1,
		"bill_km": 1,
		"distance_km": [">", 0],
		"customer": customer,
		"km_sales_invoice": ["is", "not set"],
	}
	if project:
		filters["project"] = project
	if sales_order:
		filters["sales_order"] = sales_order
	if from_time and to_time:
		filters["date"] = ["between", [getdate(from_time), getdate(to_time)]]

	fahrten = frappe.get_list(
		"Fahrt",
		filters=filters,
		fields=["name", "date", "distance_km", "km_item", "start_location", "end_location", "project"],
		order_by="date asc",
	)
	for fahrt in fahrten:
		fahrt.description = positionstext(fahrt, _("Kilometer"))
	return fahrten


def validate(doc, method=None):
	"""Jede Fahrt darf nur einmal abgerechnet werden und muss zum Kunden der
	Rechnung gehoeren."""
	gesehen = set()
	for item in doc.items:
		if not item.get("custom_fahrt"):
			continue
		fahrt = frappe.db.get_value(
			"Fahrt", item.custom_fahrt, ["docstatus", "customer", "km_sales_invoice"], as_dict=True
		)
		if not fahrt or fahrt.docstatus != 1:
			frappe.throw(_("Zeile {0}: Fahrt {1} ist nicht gebucht.").format(item.idx, item.custom_fahrt))
		if fahrt.customer != doc.customer:
			frappe.throw(
				_("Zeile {0}: Fahrt {1} gehört zum Kunden {2}.").format(item.idx, item.custom_fahrt, fahrt.customer)
			)
		if fahrt.km_sales_invoice and fahrt.km_sales_invoice != doc.name:
			frappe.throw(
				_("Zeile {0}: Die Kilometer der Fahrt {1} wurden bereits in {2} abgerechnet.").format(
					item.idx, item.custom_fahrt, fahrt.km_sales_invoice
				)
			)
		if item.custom_fahrt in gesehen:
			frappe.throw(_("Zeile {0}: Fahrt {1} steht doppelt in der Rechnung.").format(item.idx, item.custom_fahrt))
		gesehen.add(item.custom_fahrt)


def on_submit(doc, method=None):
	for item in doc.items:
		if item.get("custom_fahrt"):
			frappe.db.set_value("Fahrt", item.custom_fahrt, "km_sales_invoice", doc.name)


def on_cancel(doc, method=None):
	for name in frappe.get_all("Fahrt", filters={"km_sales_invoice": doc.name}, pluck="name"):
		frappe.db.set_value("Fahrt", name, "km_sales_invoice", None)
