import frappe
from erpnext.projects.doctype.timesheet.timesheet import OverlapError
from frappe import _
from frappe.utils import get_datetime, getdate, nowdate

from zeit_projekt.zeit_projekt.billing import (
	add_rows_to_sales_order,
	as_administrator,
	check_sales_order,
	price_rows,
	remove_rows_from_sales_order,
)


def before_submit(doc, method=None):
	"""Legt ein Timesheet an, bucht es und verknuepft es - im selben Request
	wie das Buchen des Site Visit selbst. Serverseitig, damit kein zweiter
	Request und damit kein Zeitfenster fuer "has been modified after you have
	opened it" entsteht (gleiche Begruendung wie
	zeit_projekt.zeit_projekt.sales_order.before_submit).

	customer/activity_type/sales_order/to_time sind absichtlich nicht reqd im
	Feld - ein Entwurf mit nur laufendem Timer waere sonst nicht speicherbar.
	Deshalb hier explizit vor dem Buchen geprueft."""
	if doc.timesheet:
		return

	if not doc.customer:
		frappe.throw(_("Please select a Customer before submitting."))
	if not doc.activity_type:
		frappe.throw(_("Please select an Activity Type before submitting."))
	if not doc.sales_order:
		frappe.throw(_("Please select a Sales Order before submitting."))
	if not doc.to_time:
		frappe.throw(_("Please enter an end time before submitting."))

	if get_datetime(doc.to_time) <= get_datetime(doc.from_time):
		frappe.throw(_("End time must be after the start time."))

	check_sales_order(doc.sales_order, doc.customer)

	# Die Berechtigung ist die auf den Site Visit selbst: die Rolle "Employee"
	# darf Zeitblaetter in ERPNext anlegen, aber nicht buchen, und "Projects
	# Manager" hat gar keine Zeitblatt-Rechte (fuer das Stornieren).
	ts = frappe.get_doc(
		{
			"doctype": "Timesheet",
			"employee": doc.employee,
			"company": doc.company,
			"customer": doc.customer,
			"parent_project": doc.project or None,
			"time_logs": [
				{
					"activity_type": doc.activity_type,
					"from_time": doc.from_time,
					"to_time": doc.to_time,
					"project": doc.project or None,
					"description": doc.description or doc.name,
					"is_billable": 1,
				}
			],
		}
	)
	ts.flags.ignore_permissions = True
	ts.insert()
	try:
		ts.submit()
	except OverlapError:
		frappe.throw(
			_("This time range overlaps an existing time entry for {0}.").format(doc.employee),
			title=_("Overlapping Time"),
		)

	doc.timesheet = ts.name
	frappe.msgprint(
		_("Timesheet {0} created and submitted.").format(f"<b>{ts.name}</b>"),
		indicator="green",
		alert=True,
	)

	_sync_extra_items_to_sales_order(doc)


def _sync_extra_items_to_sales_order(doc):
	"""Noch nicht uebernommene Zusatzartikel in den verknuepften Auftrag
	uebernehmen. Zeilen mit added_to_order=1 stecken bereits in einem ueber
	create_sales_order() angelegten Auftrag. Jede Zeile merkt sich die
	erzeugte Auftragsposition (sales_order_item) fuer das Stornieren."""
	pending = [row for row in doc.extra_items if not row.added_to_order]
	if not pending:
		return

	rows = [
		{"item_code": row.item_code, "qty": row.qty, "uom": row.uom, "description": _item_description(doc, row)}
		for row in pending
	]
	new_items = add_rows_to_sales_order(doc.sales_order, doc.customer, rows)

	for row, so_item in zip(pending, new_items, strict=True):
		row.added_to_order = 1
		row.sales_order_item = so_item


def _item_description(doc, row):
	"""Eindeutig je Zeile: ERPNext lehnt sonst gleiche Artikel mit gleicher
	Beschreibung im selben Auftrag ab, solange Mehrfachartikel in den
	Verkaufseinstellungen aus sind."""
	item_name = row.item_name or frappe.db.get_value("Item", row.item_code, "item_name") or row.item_code
	return _("{0} (Site Visit {1}, row {2})").format(item_name, doc.name, row.idx)


@frappe.whitelist()
def create_sales_order(site_visit, po_no=None):
	"""Fuer den "Neuer Auftrag"-Dialog: legt einen Auftrag (Entwurf) mit den
	eingetragenen Zusatzartikeln an und verknuepft ihn. Kunde, Firma, Projekt
	und Artikel kommen ausschliesslich aus dem gespeicherten Site Visit, die
	Preise aus ERPNext - der Aufrufer kann nichts davon frei vorgeben. Buchen
	bleibt Sache des Vertriebs."""
	doc = frappe.get_doc("Site Visit", site_visit)
	doc.check_permission("write")

	if doc.docstatus != 0:
		frappe.throw(_("Only draft Site Visits can create a Sales Order."))
	if doc.sales_order:
		frappe.throw(_("This Site Visit is already linked to Sales Order {0}.").format(doc.sales_order))
	if not doc.customer:
		frappe.throw(_("Please select a Customer first."))

	pending = [row for row in doc.extra_items if not row.added_to_order]
	if not pending:
		frappe.throw(_("Add at least one item before creating a new Sales Order."))

	delivery_date = max(getdate(doc.date or nowdate()), getdate(nowdate()))
	rows = [
		{"item_code": row.item_code, "qty": row.qty, "uom": row.uom, "description": _item_description(doc, row)}
		for row in pending
	]

	with as_administrator():
		so = frappe.new_doc("Sales Order")
		so.update(
			{
				"customer": doc.customer,
				"company": doc.company,
				"project": doc.project or None,
				"po_no": po_no or None,
				"transaction_date": nowdate(),
				"delivery_date": delivery_date,
			}
		)
		for row in price_rows(so, rows):
			so.append("items", row)
		so.insert()

	for row in pending:
		row.added_to_order = 1
	doc.sales_order = so.name
	doc.save()
	return so.name


def on_cancel(doc, method=None):
	"""Nimmt die beim Buchen in den Auftrag uebernommenen Zusatzartikel wieder
	heraus und storniert das verknuepfte Timesheet, sofern es noch nicht
	fakturiert wurde. Zeilen, die ueber create_sales_order() in den Auftrag
	kamen, bleiben dort (sie waren schon vor dem Buchen Teil des Auftrags)."""
	ts = frappe.get_doc("Timesheet", doc.timesheet) if doc.timesheet else None
	if ts and ts.docstatus == 1:
		for row in ts.time_logs:
			if row.sales_invoice:
				frappe.throw(
					_("Timesheet {0} was already invoiced on {1} and can no longer be cancelled.").format(
						ts.name, row.sales_invoice
					)
				)

	synced = [row for row in doc.extra_items if row.sales_order_item]
	remove_rows_from_sales_order(doc.sales_order, [row.sales_order_item for row in synced])
	for row in synced:
		# Damit ein berichtigter Site Visit diese Zeilen beim erneuten Buchen
		# wieder uebernimmt (added_to_order wird beim Berichtigen mitkopiert).
		frappe.db.set_value("Site Visit Item", row.name, {"added_to_order": 0, "sales_order_item": None})

	if ts and ts.docstatus == 1:
		ts.flags.ignore_permissions = True
		ts.cancel()


def check_app_permission():
	"""Fuer add_to_apps_screen in hooks.py: wer die App-Kachel im Desk sehen darf."""
	if frappe.session.user == "Administrator":
		return True
	roles = frappe.get_roles()
	return any(role in roles for role in ("System Manager", "Projects Manager", "Employee"))

