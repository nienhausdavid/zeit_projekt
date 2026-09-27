import copy
from contextlib import contextmanager

import frappe
from erpnext.projects.doctype.timesheet.timesheet import OverlapError
from frappe import _
from frappe.utils import get_datetime


@contextmanager
def _as_administrator():
	"""Fuehrt den with-Block als Administrator aus - fuer Sales-Order-Schritte,
	auf die der Techniker (Employee) i. d. R. keine eigenen Rechte hat. Die
	eigentliche Berechtigungspruefung ist die auf den Site Visit selbst.

	frappe.set_user() leert lokal u. a. local.form_dict komplett - ohne
	Sicherung wuerde das den umgebenden Request (z. B. das Buchen des Site
	Visit selbst, das nach diesem Hook weiterlaeuft) seiner eigenen Parameter
	berauben. Deshalb hier explizit gesichert und danach wiederhergestellt."""
	current_user = frappe.session.user
	form_dict_backup = copy.deepcopy(frappe.local.form_dict)
	frappe.set_user("Administrator")
	try:
		yield
	finally:
		frappe.set_user(current_user)
		frappe.local.form_dict = form_dict_backup


def before_submit(doc, method=None):
	"""Legt ein Timesheet an, bucht es und verknuepft es - im selben Request
	wie das Buchen des Site Visit selbst. Serverseitig, damit kein zweiter
	Request und damit kein Zeitfenster fuer "has been modified after you have
	opened it" entsteht (gleiche Begruendung wie
	zeit_projekt.zeit_projekt.sales_order.before_submit).

	customer/activity_type/sales_order/to_time sind absichtlich nicht mehr
	reqd im Feld (siehe site_visit.json) - ein Entwurf mit nur laufendem
	Timer (from_time gesetzt, "Start Timer" speichert sofort, siehe
	site_visit.js) waere sonst gar nicht speicherbar. Deshalb hier explizit
	vor dem Buchen geprueft."""
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

	ts = frappe.get_doc(
		{
			"doctype": "Timesheet",
			"employee": doc.employee,
			"company": doc.company,
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
	"""Ungebuchte Zusatzartikel (Feld extra_items) in den verknuepften Auftrag
	uebernehmen - im selben Request wie das Buchen, aus demselben Grund wie
	die Timesheet-Erstellung oben. Bereits mit added_to_order=1 markierte
	Zeilen wurden schon ueber create_sales_order() unten in einen neu
	angelegten Auftrag aufgenommen und werden hier uebersprungen.

	Nutzt erpnext.controllers.accounts_controller.update_child_qty_rate -
	dieselbe Funktion, die auch der "Update Items"-Dialog im Auftrag selbst
	verwendet - statt den Auftrag hier von Hand zu veraendern: das uebernimmt
	auch bei bereits gebuchten Auftraegen korrekt Steuer-/Summenneuberechnung,
	Kreditlimitpruefung usw."""
	pending = [row for row in doc.extra_items if not row.added_to_order]
	if not pending:
		return

	from erpnext.controllers.accounts_controller import update_child_qty_rate

	so = frappe.get_doc("Sales Order", doc.sales_order)
	trans_items = []
	for row in so.items:
		item = row.as_dict()
		item["docname"] = row.name
		trans_items.append(item)
	for row in pending:
		trans_items.append({"item_code": row.item_code, "qty": row.qty, "uom": row.uom, "rate": row.rate})

	with _as_administrator():
		update_child_qty_rate("Sales Order", frappe.as_json(trans_items), so.name)

	for row in pending:
		row.added_to_order = 1


@frappe.whitelist()
def create_sales_order(customer, company, po_no=None, project=None, items=None):
	"""Fuer den "Neuer Auftrag"-Dialog im Site-Visit-Formular: legt einen
	Auftrag (Entwurf) mit den bereits eingetragenen Zusatzartikeln an, wenn
	fuer den Kunden noch keiner existiert. Laesst den Auftrag als Entwurf -
	Buchen bleibt Sache des Vertriebs, nicht des Technikers vor Ort."""
	if not frappe.has_permission("Site Visit", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	items = frappe.parse_json(items) if isinstance(items, str) else (items or [])
	if not items:
		frappe.throw(_("Add at least one item before creating a new Sales Order."))

	so = frappe.new_doc("Sales Order")
	so.customer = customer
	so.company = company
	so.project = project or None
	so.po_no = po_no or None
	for row in items:
		so.append(
			"items",
			{
				"item_code": row.get("item_code"),
				"qty": row.get("qty") or 1,
				"uom": row.get("uom"),
				"rate": row.get("rate"),
			},
		)

	with _as_administrator():
		so.set_missing_values()
		so.insert()

	return so.name


def on_cancel(doc, method=None):
	"""Storniert das verknuepfte Timesheet mit, sofern es noch nicht
	fakturiert wurde."""
	if not doc.timesheet:
		return

	ts = frappe.get_doc("Timesheet", doc.timesheet)
	if ts.docstatus != 1:
		return

	for row in ts.time_logs:
		if row.sales_invoice:
			frappe.throw(
				_("Timesheet {0} was already invoiced on {1} and can no longer be cancelled.").format(
					ts.name, row.sales_invoice
				)
			)

	ts.cancel()


def check_app_permission():
	"""Fuer add_to_apps_screen in hooks.py: wer die App-Kachel im Desk sehen darf."""
	if frappe.session.user == "Administrator":
		return True
	roles = frappe.get_roles()
	return any(role in roles for role in ("System Manager", "Projects Manager", "Employee"))


def force_chrome_pdf():
	"""Vor download_pdf/printview: erzwingt pdf_generator=chrome fuer alle
	Doctypes auf diesem Server.

	wkhtmltopdf (der Frappe-Standard) scheitert hier grundsaetzlich an jeder
	frisch gerenderten Druckvorlage - schon das von Frappe selbst
	eingebundene <link ...print.bundle...css> ist eine relative URL ohne
	Basis-Adresse, die wkhtmltopdf im from_string-Modus nicht aufloesen kann
	("ProtocolUnknownError"). Betroffen sind nicht nur Vorlagen mit Bildern:
	am 13.09.2026 reproduziert fuer Sales Order, Sales Invoice und Site
	Visit gleichermassen, per echtem HTTP-Request wie im Browser. Bereits
	vorhandene PDFs (z. B. an alten Rechnungen) stammen vermutlich noch aus
	der Frappe-Cloud-Migration und wurden nie auf diesem Server neu erzeugt
	- deshalb ist es vorher nicht aufgefallen.

	Normalerweise liest die App print_designer das pdf_generator-Feld des
	Print Format aus und setzt es genau so vor dem eigentlichen Request -
	print_designer ist auf diesem Server aber bewusst nicht installiert
	(kein version-16-Branch, Stabilitaetsbedenken laut INSTALL-APPS.md).
	Statt der riskanten App nur den konkret benoetigten Mechanismus selbst
	nachgebaut - hier bewusst ohne Doctype-Einschraenkung, weil der
	zugrundeliegende wkhtmltopdf-Fehler alle Doctypes betrifft, nicht nur
	Site Visit."""
	request = getattr(frappe.local, "request", None)
	if not request or request.path not in (
		"/api/method/frappe.utils.print_format.download_pdf",
		"/printview",
	):
		return
	frappe.local.form_dict.pdf_generator = "chrome"
