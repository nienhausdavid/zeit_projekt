"""Rentabilitaet von Pauschalauftraegen: Pauschalpreis je Stunde gegen den Sollsatz.

Bei Pauschale wird die Zeit nicht abgerechnet, sondern gegen die geplanten Stunden gerechnet
(zeitbudget.py). Hier kommt das Geld dazu:

- geplanter Satz: Pauschalbetrag / geplante Stunden (schon beim Anlegen sichtbar)
- effektiver Satz: Pauschalbetrag / auf den Auftrag gebuchte Stunden
- Sollsatz: Preislistenpreis des Dienstleistungsartikels der gebuchten Aktivitaetsarten, nach Stunden
  gewichtet (ohne Buchungen: der der Standard-Aktivitaetsart aus den Einstellungen)
- Abweichung in Prozent vom Sollsatz - mit dem effektiven Satz, solange Zeit gebucht ist, sonst mit
  dem geplanten.

Der Pauschalbetrag sind die Positionen mit dem Pauschalartikel oder einem Dienstleistungsartikel einer
Aktivitaetsart; Material und weitere Positionen zaehlen nicht mit. Fahrtkosten und Lohnkosten sind nicht
eingerechnet (Verkaufssatz als Massstab, keine Kostenrechnung)."""

from collections import defaultdict

import frappe
from frappe.utils import flt

from zeit_projekt.zeit_projekt.zeitbudget import verbrauchte_stunden

# Ab dieser Abweichung nach unten (in Prozent des Sollsatzes) wechselt orange auf rot
ROT_AB = -20


def farbe(abweichung):
	"""green: mindestens Sollsatz, orange: bis 20 % darunter, red: mehr als 20 % darunter."""
	if abweichung >= 0:
		return "green"
	if abweichung >= ROT_AB:
		return "orange"
	return "red"


def pauschalbetrag(sales_order):
	"""Summe der Pauschalpositionen des Auftrags (netto)."""
	artikel = set(
		frappe.get_all(
			"Activity Type", filters={"custom_dienstleistungsartikel": ["is", "set"]}, pluck="custom_dienstleistungsartikel"
		)
	)
	pauschal = frappe.db.get_single_value("Zeit Projekt Einstellungen", "pauschalartikel")
	if pauschal:
		artikel.add(pauschal)
	if not artikel:
		return 0.0
	return sum(
		flt(z.amount)
		for z in frappe.get_all(
			"Sales Order Item",
			filters={"parent": sales_order, "parenttype": "Sales Order", "item_code": ["in", list(artikel)]},
			fields=["amount"],
		)
	)


def _listenpreis(item_code, price_list):
	preis = frappe.db.get_value(
		"Item Price", {"item_code": item_code, "price_list": price_list, "selling": 1}, "price_list_rate"
	)
	return flt(preis) or flt(frappe.db.get_value("Item", item_code, "standard_rate"))


def sollsatz(sales_order, price_list):
	"""Stundensatz, an dem die Pauschale gemessen wird; 0, wenn sich keiner ermitteln laesst."""
	stunden = defaultdict(float)
	for zeile in frappe.get_all(
		"Timesheet Detail",
		filters=[["docstatus", "=", 1], ["parenttype", "=", "Timesheet"], ["custom_sales_order", "=", sales_order]],
		fields=["activity_type", "hours"],
		limit=0,
	):
		if zeile.activity_type:
			stunden[zeile.activity_type] += flt(zeile.hours)
	if not stunden:
		standard = frappe.db.get_single_value("Zeit Projekt Einstellungen", "activity_type")
		if standard:
			stunden[standard] = 1.0
	summe = gewicht = 0.0
	for aktivitaet, h in stunden.items():
		artikel = frappe.db.get_value("Activity Type", aktivitaet, "custom_dienstleistungsartikel")
		preis = _listenpreis(artikel, price_list) if artikel else 0
		if preis > 0 and h > 0:
			summe += preis * h
			gewicht += h
	return summe / gewicht if gewicht else 0.0


def rentabilitaet(sales_order, verbraucht=None):
	"""Kennzahlen zur Pauschale; None, wenn der Auftrag keine Pauschale mit Betrag ist."""
	so = frappe.db.get_value(
		"Sales Order",
		sales_order,
		["custom_abrechnungsart", "custom_geplante_stunden", "selling_price_list"],
		as_dict=True,
	)
	if not so or so.custom_abrechnungsart != "Pauschale":
		return None
	betrag = pauschalbetrag(sales_order)
	if betrag <= 0:
		return None
	if verbraucht is None:
		verbraucht = verbrauchte_stunden([sales_order]).get(sales_order)
	geplant, verbraucht = flt(so.custom_geplante_stunden), flt(verbraucht)
	geplanter_satz = betrag / geplant if geplant > 0 else None
	effektiver_satz = betrag / verbraucht if verbraucht > 0 else None
	soll = sollsatz(sales_order, so.selling_price_list)
	massstab = effektiver_satz if effektiver_satz is not None else geplanter_satz
	abweichung = round((massstab - soll) / soll * 100, 1) if soll and massstab is not None else None
	return {
		"betrag": betrag,
		"geplanter_satz": round(geplanter_satz, 2) if geplanter_satz is not None else None,
		"effektiver_satz": round(effektiver_satz, 2) if effektiver_satz is not None else None,
		"sollsatz": round(soll, 2) or None,
		"abweichung": abweichung,
		"farbe": farbe(abweichung) if abweichung is not None else None,
	}


@frappe.whitelist()
def get_rentabilitaet(sales_order):
	"""Fuer die Anzeige im Auftrag. Nur mit Leserecht am Auftrag: Preise sind nichts fuer Techniker."""
	if not sales_order or not frappe.has_permission("Sales Order", "read", sales_order):
		return None
	return rentabilitaet(sales_order)
