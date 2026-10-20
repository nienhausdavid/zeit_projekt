"""Auftrags- und Projektansicht: Aufträge und Projekte in einer Liste.

Ein Projekt steht mit seinen Aufträgen darunter (eingerückt, auf- und
zuklappbar); Aufträge ohne Projekt stehen auf der obersten Ebene daneben.
Zu jeder Zeile: gebuchte und noch offene Stunden, offener Betrag, was schon
abgerechnet ist.

Die Zahlen einer Projektzeile umfassen alles, was auf das Projekt gebucht ist -
auch die Zeiten, die zugleich auf einen der Aufträge darunter laufen. Eine
Summenzeile gibt es deshalb nicht (sie zählte doppelt).

Projekte und Aufträge liest der Bericht mit den Rechten des Benutzers (get_list)."""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	ausblenden = cint(filters.get("abgeschlossene_ausblenden", 1))

	projekt_bedingungen = {}
	auftrag_bedingungen = {"docstatus": ["<", 2]}
	if filters.get("customer"):
		projekt_bedingungen["customer"] = auftrag_bedingungen["customer"] = filters.customer
	if filters.get("project"):
		projekt_bedingungen["name"] = auftrag_bedingungen["project"] = filters.project
	if ausblenden:
		projekt_bedingungen["status"] = ["not in", ["Completed", "Cancelled"]]
		auftrag_bedingungen["status"] = ["not in", ["Closed", "Completed", "Cancelled"]]

	projekte = frappe.get_list(
		"Project",
		filters=projekt_bedingungen,
		fields=["name", "project_name", "customer", "status", "expected_start_date", "total_billed_amount"],
		limit=0,
	)
	auftraege = frappe.get_list(
		"Sales Order",
		filters=auftrag_bedingungen,
		fields=["name", "customer", "po_no", "transaction_date", "status", "project", "net_total", "per_billed"],
		limit=0,
	)

	# Ist ein Projekt abgeschlossen (ausgeblendet), seine Auftraege aber noch offen, bleibt es als
	# Kopfzeile stehen - sonst loest sich der Bezug zum Projekt auf.
	fehlend = {a.project for a in auftraege if a.project} - {p.name for p in projekte}
	if fehlend:
		projekte += frappe.get_list(
			"Project",
			filters={"name": ["in", list(fehlend)]},
			fields=["name", "project_name", "customer", "status", "expected_start_date", "total_billed_amount"],
			limit=0,
		)

	projektnamen = {p.name for p in projekte}
	kinder = defaultdict(list)
	ohne_projekt = []
	for auftrag in auftraege:
		if auftrag.project in projektnamen:
			kinder[auftrag.project].append(auftrag)
		else:
			ohne_projekt.append(auftrag)

	zeit_projekt = _zeit_summen("project", projektnamen)
	zeit_auftrag = _zeit_summen("custom_sales_order", {a.name for a in auftraege})
	rechnungen = _rechnungsbetraege({a.name for a in auftraege})
	kundennamen = _kundennamen({x.customer for x in (*projekte, *auftraege) if x.customer})

	oberste = [("Project", p) for p in projekte] + [("Sales Order", a) for a in ohne_projekt]
	oberste.sort(key=lambda e: (kundennamen.get(e[1].customer, ""), e[0] != "Project", e[1].name))

	daten = []
	for typ, beleg in oberste:
		if typ == "Project":
			daten.append(_projekt_zeile(beleg, kundennamen, zeit_projekt.get(beleg.name)))
			for auftrag in sorted(kinder[beleg.name], key=lambda a: (a.transaction_date, a.name)):
				daten.append(_auftrag_zeile(auftrag, kundennamen, zeit_auftrag, rechnungen, indent=1))
		else:
			daten.append(_auftrag_zeile(beleg, kundennamen, zeit_auftrag, rechnungen, indent=0))
	return _spalten(), daten


def _zeit_summen(feld, namen):
	"""feld ("project" bzw. "custom_sales_order") -> gebuchte/offene Zeit der abrechenbaren Zeitbuchungen."""
	if not namen:
		return {}
	# get_all: die Summen je Projekt/Auftrag stehen auch im Projekt selbst (Stunden, abrechenbarer
	# Betrag) - ein Projects Manager ohne Zeitblatt-Recht soll sie hier ebenfalls sehen. Gefragt wird
	# nur nach Projekten und Auftraegen, die er lesen darf (siehe execute).
	zeilen = frappe.get_all(
		"Timesheet Detail",
		filters=[["docstatus", "=", 1], ["is_billable", "=", 1], [feld, "in", list(namen)]],
		fields=[feld, "hours", "billing_hours", "billing_amount", "sales_invoice"],
		limit=0,
	)
	summen = defaultdict(lambda: frappe._dict(stunden=0.0, offen=0.0, betrag_offen=0.0))
	for zeile in zeilen:
		summe = summen[zeile.get(feld)]
		stunden = flt(zeile.billing_hours) or flt(zeile.hours)
		summe.stunden += stunden
		if not zeile.sales_invoice:
			summe.offen += stunden
			summe.betrag_offen += flt(zeile.billing_amount)
	return summen


def _rechnungsbetraege(auftraege):
	"""Auftrag -> Summe der Rechnungspositionen (gebuchte Rechnungen) mit diesem Auftrag - auch die
	aus dem Zeitimport, die ERPNext beim Auftrag nicht als berechnet zählt."""
	if not auftraege:
		return {}
	summen = defaultdict(float)
	for position in frappe.get_all(
		"Sales Invoice Item",
		filters={"sales_order": ["in", list(auftraege)], "docstatus": 1},
		fields=["sales_order", "net_amount"],
	):
		summen[position.sales_order] += flt(position.net_amount)
	return summen


def _kundennamen(kunden):
	if not kunden:
		return {}
	return dict(
		frappe.get_all(
			"Customer", filters={"name": ["in", list(kunden)]}, fields=["name", "customer_name"], as_list=True
		)
	)


def _zeit_felder(zeile, summe):
	summe = summe or frappe._dict(stunden=0.0, offen=0.0, betrag_offen=0.0)
	zeile.update(
		stunden=summe.stunden,
		stunden_offen=summe.offen,
		betrag_offen=summe.betrag_offen,
		# Anteil der gebuchten Stunden, die schon in einer gebuchten Rechnung stehen
		zeit_prozent=(summe.stunden - summe.offen) / summe.stunden * 100 if summe.stunden else None,
	)
	return zeile


def _projekt_zeile(projekt, kundennamen, summe):
	return _zeit_felder(
		frappe._dict(
			beleg=projekt.name,
			doctype="Project",
			typ=_("Projekt"),
			kunde=projekt.customer,
			kunde_name=kundennamen.get(projekt.customer),
			bezeichnung=projekt.project_name,
			status=_(projekt.status) if projekt.status else None,
			datum=projekt.expected_start_date,
			auftragswert=None,
			abgerechnet=flt(projekt.total_billed_amount),
			auftrag_prozent=None,
			indent=0,
		),
		summe,
	)


def _auftrag_zeile(auftrag, kundennamen, zeit, rechnungen, indent):
	return _zeit_felder(
		frappe._dict(
			beleg=auftrag.name,
			doctype="Sales Order",
			typ=_("Auftrag"),
			kunde=auftrag.customer,
			kunde_name=kundennamen.get(auftrag.customer),
			bezeichnung=auftrag.po_no,
			status=_(auftrag.status) if auftrag.status else None,
			datum=auftrag.transaction_date,
			auftragswert=flt(auftrag.net_total),
			abgerechnet=flt(rechnungen.get(auftrag.name)),
			auftrag_prozent=flt(auftrag.per_billed),
			indent=indent,
		),
		zeit.get(auftrag.name),
	)


def _spalten():
	return [
		{
			"fieldname": "beleg",
			"label": _("Projekt / Auftrag"),
			"fieldtype": "Dynamic Link",
			"options": "doctype",
			"width": 170,
		},
		{"fieldname": "doctype", "label": _("DocType"), "fieldtype": "Data", "hidden": 1},
		{"fieldname": "typ", "label": _("Typ"), "fieldtype": "Data", "width": 80},
		{"fieldname": "kunde", "label": _("Kunde"), "fieldtype": "Link", "options": "Customer", "width": 130},
		{"fieldname": "kunde_name", "label": _("Kundenname"), "fieldtype": "Data", "width": 200},
		{"fieldname": "bezeichnung", "label": _("Projektname / Kommission"), "fieldtype": "Data", "width": 200},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "datum", "label": _("Datum"), "fieldtype": "Date", "width": 100},
		{"fieldname": "auftragswert", "label": _("Auftragswert"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "stunden", "label": _("Stunden gebucht"), "fieldtype": "Float", "precision": 2, "width": 110},
		{"fieldname": "stunden_offen", "label": _("Stunden offen"), "fieldtype": "Float", "precision": 2, "width": 100},
		{"fieldname": "betrag_offen", "label": _("Zeit offen (Betrag)"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "abgerechnet", "label": _("Abgerechnet"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "zeit_prozent", "label": _("Zeit berechnet %"), "fieldtype": "Percent", "width": 110},
		{"fieldname": "auftrag_prozent", "label": _("Auftrag % berechnet"), "fieldtype": "Percent", "width": 120},
	]
