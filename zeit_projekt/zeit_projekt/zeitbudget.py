"""Zeitbudget eines Auftrags: auf den Auftrag gebuchte Zeit gegen die geplanten Stunden.

Gezaehlt wird die tatsaechliche Dauer (hours) aller gebuchten Zeitblatt-Zeilen mit diesem Auftrag
(Feld custom_sales_order) - abrechenbar oder nicht, auch bei Pauschale: es geht darum, wie viel der
eingeplanten Zeit schon gebraucht wurde. Ohne geplante Stunden gibt es kein Budget."""

import frappe
from frappe.utils import flt

# Ab diesem Verbrauch (in Prozent der geplanten Zeit) wechselt die Farbe
WARNUNG_AB = 80
UEBERSCHRITTEN_AB = 100


def farbe(prozent):
	"""green: im Rahmen, orange: fast aufgebraucht (ab 80 %, 100 % eingeschlossen), red: ueberschritten."""
	if prozent > UEBERSCHRITTEN_AB:
		return "red"
	if prozent >= WARNUNG_AB:
		return "orange"
	return "green"


def verbrauchte_stunden(auftraege):
	"""Auftrag -> auf ihn gebuchte Stunden (gebuchte Zeitblaetter)."""
	auftraege = [a for a in set(auftraege) if a]
	if not auftraege:
		return {}
	summen = {}
	for zeile in frappe.get_all(
		"Timesheet Detail",
		filters=[["docstatus", "=", 1], ["parenttype", "=", "Timesheet"], ["custom_sales_order", "in", auftraege]],
		fields=["custom_sales_order", "hours"],
		limit=0,
	):
		summen[zeile.custom_sales_order] = summen.get(zeile.custom_sales_order, 0) + flt(zeile.hours)
	return summen


def budget(geplant, verbraucht):
	"""Kennzahlen zu geplanten und verbrauchten Stunden; None ohne Planung."""
	geplant = flt(geplant)
	if geplant <= 0:
		return None
	verbraucht = flt(verbraucht)
	prozent = round(verbraucht / geplant * 100, 1)
	return {
		"geplant": geplant,
		"verbraucht": round(verbraucht, 2),
		"rest": round(geplant - verbraucht, 2),
		"prozent": prozent,
		"farbe": farbe(prozent),
	}


def zeitbudget(sales_order):
	geplant = frappe.db.get_value("Sales Order", sales_order, "custom_geplante_stunden")
	return budget(geplant, verbrauchte_stunden([sales_order]).get(sales_order))


def _darf_sehen(sales_order):
	"""Wer den Auftrag lesen darf - oder Fahrten/Kundeneinsaetze erfasst (Techniker duerfen den
	Auftrag selbst nicht lesen, sollen aber sehen, wie viel Zeit noch da ist)."""
	if frappe.has_permission("Sales Order", "read", sales_order):
		return True
	return any(
		frappe.has_permission(doctype, ptype) for doctype in ("Fahrt", "Site Visit") for ptype in ("create", "write")
	)


@frappe.whitelist()
def get_zeitbudget(sales_order):
	"""Fuer die Anzeige im Auftrag, Kundeneinsatz und in der Fahrt. None: kein Auftrag oder keine Planung."""
	if not sales_order or not _darf_sehen(sales_order):
		return None
	return zeitbudget(sales_order)
