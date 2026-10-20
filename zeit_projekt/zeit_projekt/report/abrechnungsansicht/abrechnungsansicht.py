"""Abrechnungsansicht: was ist abzurechnen?

Offene (gebuchte, abrechenbare, noch in keiner gebuchten Rechnung stehende)
Zeitbuchungen und Fahrt-Kilometer, zusammengefasst je Kunde, Auftrag und
Projekt - dieselben Zeiten und Fahrten, die der Zeitimport der Ausgangsrechnung
holt (sales_invoice.get_billable_time_logs). Der Kunde ist dabei wie dort der
des Projekts der Zeitbuchung, sonst der des Zeitblatts.

Gelesen wird mit den Rechten des Benutzers (get_list)."""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from zeit_projekt.zeit_projekt.billing import pauschale_auftraege
from zeit_projekt.zeit_projekt.sales_invoice import _row_customers


def execute(filters=None):
	filters = frappe._dict(filters or {})
	gruppen = {}
	_zeiten_sammeln(gruppen, filters)
	_kilometer_sammeln(gruppen, filters)
	_namen_ergaenzen(gruppen)
	daten = sorted(
		gruppen.values(),
		key=lambda g: (g.kunde is None, g.kunde_name or "", g.sales_order or "", g.project or ""),
	)
	return _spalten(), daten


def _gruppe(gruppen, kunde, sales_order, project):
	schluessel = (kunde, sales_order, project)
	if schluessel not in gruppen:
		gruppen[schluessel] = frappe._dict(
			kunde=kunde,
			sales_order=sales_order,
			project=project,
			anzahl=0,
			stunden=0.0,
			entwurf_stunden=0.0,
			betrag=0.0,
			km=0.0,
			aeltester=None,
		)
	return gruppen[schluessel]


def _aeltester(gruppe, datum):
	datum = getdate(datum)
	if not gruppe.aeltester or datum < gruppe.aeltester:
		gruppe.aeltester = datum


def _zeiten_sammeln(gruppen, filters):
	bedingungen = [["docstatus", "=", 1], ["is_billable", "=", 1], ["sales_invoice", "is", "not set"]]
	if filters.get("project"):
		bedingungen.append(["project", "=", filters.project])
	if filters.get("sales_order"):
		bedingungen.append(["custom_sales_order", "=", filters.sales_order])
	if filters.get("from_date"):
		bedingungen.append(["from_time", ">=", f"{getdate(filters.from_date)} 00:00:00"])
	if filters.get("to_date"):
		bedingungen.append(["from_time", "<=", f"{getdate(filters.to_date)} 23:59:59"])

	zeilen = frappe.get_list(
		"Timesheet Detail",
		parent_doctype="Timesheet",
		filters=bedingungen,
		fields=["name", "parent", "project", "custom_sales_order", "hours", "billing_hours", "billing_amount", "from_time"],
		limit=0,
	)
	if not zeilen:
		return
	for zeile in zeilen:
		zeile.time_sheet = zeile.parent
	kunde_von = _row_customers(zeilen)
	if filters.get("customer"):
		zeilen = [z for z in zeilen if kunde_von.get(z.name) == filters.customer]

	# Zeiten, die schon in einer Rechnung im Entwurf stehen (noch nicht gebucht, deshalb
	# gilt die Zeit in ERPNext noch als offen) - sonst wird sie ein zweites Mal abgerechnet
	im_entwurf = set(
		frappe.get_all(
			"Sales Invoice Timesheet",
			filters={"timesheet_detail": ["in", [z.name for z in zeilen]], "docstatus": 0},
			pluck="timesheet_detail",
		)
		if zeilen
		else []
	)

	for zeile in zeilen:
		gruppe = _gruppe(gruppen, kunde_von.get(zeile.name), zeile.custom_sales_order, zeile.project)
		stunden = flt(zeile.billing_hours) or flt(zeile.hours)
		gruppe.anzahl += 1
		gruppe.stunden += stunden
		if zeile.name in im_entwurf:
			gruppe.entwurf_stunden += stunden
		gruppe.betrag += flt(zeile.billing_amount)
		_aeltester(gruppe, zeile.from_time)


def _kilometer_sammeln(gruppen, filters):
	bedingungen = {
		"docstatus": 1,
		"bill_km": 1,
		"distance_km": [">", 0],
		"km_sales_invoice": ["is", "not set"],
	}
	for feld in ("customer", "project", "sales_order"):
		if filters.get(feld):
			bedingungen[feld] = filters[feld]
	if filters.get("from_date") and filters.get("to_date"):
		bedingungen["date"] = ["between", [getdate(filters.from_date), getdate(filters.to_date)]]
	elif filters.get("from_date"):
		bedingungen["date"] = [">=", getdate(filters.from_date)]
	elif filters.get("to_date"):
		bedingungen["date"] = ["<=", getdate(filters.to_date)]

	fahrten = frappe.get_list(
		"Fahrt", filters=bedingungen, fields=["customer", "project", "sales_order", "distance_km", "date"], limit=0
	)
	# Pauschal abgerechnete Auftraege: die Kilometer stecken im Pauschalpreis
	pauschal = pauschale_auftraege(f.sales_order for f in fahrten)
	for fahrt in fahrten:
		if fahrt.sales_order in pauschal:
			continue
		gruppe = _gruppe(gruppen, fahrt.customer, fahrt.sales_order, fahrt.project)
		gruppe.km += flt(fahrt.distance_km)
		_aeltester(gruppe, fahrt.date)


def _namen_ergaenzen(gruppen):
	kunden = {g.kunde for g in gruppen.values() if g.kunde}
	kundennamen = (
		dict(
			frappe.get_all(
				"Customer", filters={"name": ["in", list(kunden)]}, fields=["name", "customer_name"], as_list=True
			)
		)
		if kunden
		else {}
	)
	auftraege = {g.sales_order for g in gruppen.values() if g.sales_order}
	kommissionen = (
		dict(
			frappe.get_all(
				"Sales Order", filters={"name": ["in", list(auftraege)]}, fields=["name", "po_no"], as_list=True
			)
		)
		if auftraege
		else {}
	)
	for gruppe in gruppen.values():
		gruppe.kunde_name = kundennamen.get(gruppe.kunde) if gruppe.kunde else _("Kunde fehlt")
		gruppe.po_no = kommissionen.get(gruppe.sales_order)


def _spalten():
	return [
		{"fieldname": "kunde", "label": _("Kunde"), "fieldtype": "Link", "options": "Customer", "width": 130},
		{"fieldname": "kunde_name", "label": _("Kundenname"), "fieldtype": "Data", "width": 220},
		{"fieldname": "sales_order", "label": _("Auftrag"), "fieldtype": "Link", "options": "Sales Order", "width": 140},
		{"fieldname": "po_no", "label": _("Kommission"), "fieldtype": "Data", "width": 130},
		{"fieldname": "project", "label": _("Projekt"), "fieldtype": "Link", "options": "Project", "width": 130},
		{"fieldname": "anzahl", "label": _("Zeitbuchungen"), "fieldtype": "Int", "width": 110},
		{"fieldname": "stunden", "label": _("Stunden offen"), "fieldtype": "Float", "precision": 2, "width": 110},
		{
			"fieldname": "entwurf_stunden",
			"label": _("davon im Rechnungsentwurf"),
			"fieldtype": "Float",
			"precision": 2,
			"width": 130,
		},
		{"fieldname": "betrag", "label": _("Offener Betrag"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "km", "label": _("Kilometer offen"), "fieldtype": "Float", "precision": 1, "width": 110},
		{"fieldname": "aeltester", "label": _("Ältester Eintrag"), "fieldtype": "Date", "width": 110},
	]
