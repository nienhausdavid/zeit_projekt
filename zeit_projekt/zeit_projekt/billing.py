import copy
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import cint, flt

GESCHLOSSENE_STATUS = ("Closed", "Completed")
# Kopfdaten, die nicht in den temporaeren Preisberechnungs-Auftrag gehoeren
NICHT_KOPIEREN = ("name", "docstatus", "idx", "amended_from", "owner", "creation", "modified", "modified_by")


@contextmanager
def as_administrator():
	"""Techniker (Employee) haben i. d. R. keine Rechte auf Auftrag/Artikel -
	die eigentliche Berechtigungspruefung ist die auf Fahrt bzw. Site Visit.

	frappe.set_user() leert local.form_dict komplett; ohne Sicherung verloere
	der umgebende Request (z. B. das Buchen selbst) seine Parameter."""
	current_user = frappe.session.user
	form_dict_backup = copy.deepcopy(frappe.local.form_dict)
	frappe.set_user("Administrator")
	try:
		yield
	finally:
		frappe.set_user(current_user)
		frappe.local.form_dict = form_dict_backup


def create_timesheet(source, activity_type, from_time, to_time, *, customer, project=None,
		company=None, description=None, billing_hours=None):
	"""Legt ein abrechenbares Zeitblatt fuer eine Fahrt bzw. einen Site Visit
	an und bucht es. Es erscheint danach im Zeitimport der Ausgangsrechnung
	des Kunden (siehe sales_invoice.get_billable_time_logs).

	Ohne Rollenpruefung: die Rolle "Employee" darf Zeitblaetter in ERPNext
	anlegen, aber nicht buchen - massgeblich ist die Berechtigung auf den
	Quellbeleg."""
	from erpnext.projects.doctype.timesheet.timesheet import OverlapError

	company = company or frappe.db.get_value("Employee", source.employee, "company")
	ts = frappe.get_doc(
		{
			"doctype": "Timesheet",
			"employee": source.employee,
			"company": company,
			"customer": customer,
			"parent_project": project or None,
			"note": _("Automatisch erzeugt aus {0} {1}").format(_(source.doctype), source.name),
			"time_logs": [
				{
					"activity_type": activity_type,
					"from_time": from_time,
					"to_time": to_time,
					"project": project or None,
					"description": description or source.name,
					"is_billable": 1,
					"billing_hours": billing_hours or 0,
				}
			],
		}
	)
	ts.flags.ignore_permissions = True
	try:
		# Die Ueberschneidungspruefung laeuft schon in validate (also beim insert)
		ts.insert()
		ts.submit()
	except OverlapError:
		frappe.throw(
			_("Dieser Zeitraum überschneidet sich mit einer bereits erfassten Zeitbuchung für {0}.").format(
				source.employee
			),
			title=_("Zeitüberschneidung"),
		)
	return ts.name


def ensure_timesheet_not_invoiced(timesheet):
	"""Ein bereits fakturiertes Zeitblatt darf nicht mehr mitstorniert werden."""
	if not timesheet:
		return
	invoice = frappe.db.get_value(
		"Timesheet Detail", {"parent": timesheet, "sales_invoice": ["is", "set"]}, "sales_invoice"
	)
	if invoice:
		frappe.throw(
			_("Zeitblatt {0} wurde bereits in {1} abgerechnet und kann nicht mehr storniert werden.").format(
				timesheet, invoice
			)
		)


def cancel_timesheet(timesheet):
	if not timesheet:
		return
	ensure_timesheet_not_invoiced(timesheet)
	ts = frappe.get_doc("Timesheet", timesheet)
	if ts.docstatus != 1:
		return
	ts.flags.ignore_permissions = True
	ts.cancel()


def check_sales_order(sales_order, customer):
	"""Auftrag muss offen sein und zum Kunden des Belegs gehoeren - sonst
	koennte ein Techniker Positionen in beliebige fremde Auftraege schreiben."""
	so = frappe.db.get_value("Sales Order", sales_order, ["customer", "docstatus", "status"], as_dict=True)
	if not so:
		frappe.throw(_("Auftrag {0} existiert nicht.").format(sales_order))
	if so.docstatus == 2 or so.status in GESCHLOSSENE_STATUS:
		frappe.throw(_("Auftrag {0} ist storniert oder abgeschlossen.").format(frappe.bold(sales_order)))
	if customer and so.customer != customer:
		frappe.throw(
			_("Auftrag {0} gehört zum Kunden {1}, nicht zu {2}.").format(
				frappe.bold(sales_order), frappe.bold(so.customer), frappe.bold(customer)
			)
		)
	return so


def price_rows(header_doc, rows, throw=True):
	"""Ermittelt Preis, Lager, Einheit und Liefertermin fuer neue Positionen
	ueber ERPNexts eigene Logik (Preisliste, Preisregeln, Waehrung) auf einem
	nie gespeicherten Auftrag mit den Kopfdaten von header_doc.

	update_child_qty_rate uebernimmt fuer neue Zeilen genau den uebergebenen
	Preis - ohne diesen Schritt landen sie mit 0 im Auftrag.

	rows: dicts mit item_code, qty, description, optional uom.
	Muss als Administrator laufen (get_item_details prueft Artikel-Leserechte)."""
	tmp = frappe.new_doc("Sales Order")
	tmp.update(
		{f: header_doc.get(f) for f in header_doc.meta.get_valid_columns() if f not in NICHT_KOPIEREN}
	)
	for row in rows:
		tmp.append("items", {"item_code": row["item_code"], "qty": row["qty"], "uom": row.get("uom") or None})
	tmp.set_missing_values()
	tmp.calculate_taxes_and_totals()

	priced = []
	for row, item in zip(rows, tmp.items, strict=True):
		if throw and not flt(item.rate):
			frappe.throw(
				_(
					"Für Artikel {0} wurde kein Verkaufspreis gefunden (Preisliste {1}). "
					"Bitte einen Artikelpreis hinterlegen."
				).format(frappe.bold(row["item_code"]), frappe.bold(tmp.selling_price_list))
			)
		priced.append(
			{
				"item_code": row["item_code"],
				"qty": flt(row["qty"]),
				"rate": flt(item.rate),
				"uom": item.uom,
				"conversion_factor": item.conversion_factor,
				"warehouse": item.warehouse,
				"description": row["description"],
				"delivery_date": item.delivery_date or tmp.delivery_date,
			}
		)
	return priced


def zero_price_allowed():
	return cint(frappe.db.get_single_value("Zeit Projekt Einstellungen", "allow_zero_price"))


def add_rows_to_sales_order(sales_order, customer, rows, source):
	"""Haengt Positionen an einen (auch bereits gebuchten) Auftrag an und gibt
	die Namen der neu entstandenen Auftragspositionen zurueck (fuer das
	Zurueckbuchen beim Stornieren).

	Nutzt erpnext.controllers.accounts_controller.update_child_qty_rate - wie
	der "Update Items"-Dialog im Auftrag: Steuern, Summen, Kreditlimit usw.
	werden korrekt neu berechnet. Weil das als Administrator laeuft, markiert
	jede neue Position ihren Ursprungsbeleg (custom_site_visit) und ein
	Kommentar im Auftrag nennt den Nutzer, der gebucht hat."""
	from erpnext.controllers.accounts_controller import update_child_qty_rate

	check_sales_order(sales_order, customer)
	nutzer = frappe.utils.get_fullname(frappe.session.user)
	ohne_preis_erlaubt = zero_price_allowed()
	with as_administrator():
		so = frappe.get_doc("Sales Order", sales_order)
		priced = price_rows(so, rows, throw=not ohne_preis_erlaubt)
		vorher = {row.name for row in so.items}
		trans_items = [dict(row.as_dict(), docname=row.name) for row in so.items] + priced
		update_child_qty_rate("Sales Order", frappe.as_json(trans_items), so.name)
		# Neue Zeilen werden in der Reihenfolge von rows angehaengt -
		# nach idx sortiert passt die Rueckgabe zeilenweise zu rows.
		nachher = frappe.get_all(
			"Sales Order Item",
			filters={"parenttype": "Sales Order", "parent": so.name},
			order_by="idx asc",
			pluck="name",
		)
		neu = [name for name in nachher if name not in vorher]
		for name in neu:
			frappe.db.set_value("Sales Order Item", name, "custom_site_visit", source.name, update_modified=False)

		ohne_preis = [p["item_code"] for p in priced if not flt(p["rate"])]
		text = _("{0} Position(en) aus {1} {2} übernommen, gebucht von {3}.").format(
			len(neu), _(source.doctype), frappe.utils.get_link_to_form(source.doctype, source.name), nutzer
		)
		if ohne_preis:
			text += " " + _("Ohne Verkaufspreis (bitte prüfen): {0}").format(", ".join(ohne_preis))
		so.add_comment("Comment", text)

	if ohne_preis:
		frappe.msgprint(
			_("Für {0} wurde kein Verkaufspreis gefunden - die Position steht mit 0 im Auftrag {1}.").format(
				", ".join(ohne_preis), sales_order
			),
			indicator="orange",
			alert=True,
		)
	return neu


def remove_rows_from_sales_order(sales_order, item_names):
	"""Entfernt beim Stornieren genau die Positionen wieder, die der Beleg beim
	Buchen angelegt hat. Bereits gelieferte/fakturierte Positionen lehnt
	ERPNext selbst ab - dann bleibt auch das Stornieren blockiert."""
	from erpnext.controllers.accounts_controller import update_child_qty_rate

	item_names = set(item_names or [])
	if not sales_order or not item_names:
		return

	with as_administrator():
		so = frappe.get_doc("Sales Order", sales_order)
		if so.docstatus == 2:
			return
		rest = [row for row in so.items if row.name not in item_names]
		if len(rest) == len(so.items):
			return
		if not rest:
			frappe.throw(
				_(
					"Auftrag {0} hätte nach dem Entfernen keine Positionen mehr. "
					"Bitte den Auftrag selbst anpassen oder stornieren."
				).format(frappe.bold(sales_order))
			)
		trans_items = [dict(row.as_dict(), docname=row.name) for row in rest]
		update_child_qty_rate("Sales Order", frappe.as_json(trans_items), so.name)
