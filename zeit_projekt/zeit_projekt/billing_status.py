"""Abrechnungsstand ("% berechnet") von Auftraegen, deren Zeit ueber das
Zeitblatt abgerechnet wird.

ERPNext rechnet per_billed nach Betrag der Auftragspositionen (status_updater,
_calculate_target_parent_percentage). Die Zeit eines Kundeneinsatzes steht aber
nicht als Betrag im Auftrag - der ueber "Neuer Auftrag" angelegte hat nur eine
Position zu Preis 0 -, sondern in Zeitbuchungen mit dem Feld Auftrag
(custom_sales_order), die der Zeitimport in die Rechnung holt. Folgen ohne
diese Korrektur:

- Auftrag mit Summe 0: ERPNext vergleicht dann die berechnete Menge mit der
  Auftragsmenge (update_billing_status_for_zero_amount_refdoc) - 1,5 Std. aus
  dem ersten von zwei Einsaetzen gegen Menge 1 ergibt "Vollständig berechnet".
- Steht der Auftrag nicht in der Rechnungsposition (Entwurf beim Abrechnen,
  anderes Projekt), bleibt er fuer immer "Nicht berechnet".
- Auftrag mit Zusatzartikeln: sind die berechnet, gilt er als vollstaendig
  berechnet, auch wenn die Zeit noch offen ist.

Hier zaehlen deshalb Positionen und Zeitbuchungen gemeinsam, gewichtet nach
Betrag: berechneter Betrag der Positionen (billed_amt, von ERPNext gepflegt)
plus Abrechnungsbetrag der bereits abgerechneten Zeitbuchungen, geteilt durch
die Summe aus beidem. Auftraege ohne Zeitbuchungen bleiben unberuehrt.

Laeuft nach ERPNexts eigener Berechnung (doc_events kommen nach der
Controller-Methode) - beim Buchen/Stornieren von Rechnung, Zeitblatt und
Auftrag."""

import frappe
from frappe.utils import flt


def update_sales_orders(sales_orders):
	for name in sorted({so for so in sales_orders if so}):
		_update(name)


def _update(sales_order):
	so = frappe.db.get_value("Sales Order", sales_order, ["docstatus"], as_dict=True)
	if not so or so.docstatus != 1:
		return

	zeiten = frappe.get_all(
		"Timesheet Detail",
		filters={
			"custom_sales_order": sales_order,
			"parenttype": "Timesheet",
			"docstatus": 1,
			"is_billable": 1,
		},
		fields=["billing_amount", "billing_hours", "hours", "sales_invoice"],
	)
	if not zeiten:
		return

	positionen = frappe.get_all(
		"Sales Order Item",
		filters={"parent": sales_order, "parenttype": "Sales Order"},
		fields=["amount", "billed_amt"],
	)
	gesamt = sum(abs(flt(p.amount)) for p in positionen) + sum(flt(z.billing_amount) for z in zeiten)
	berechnet = sum(min(abs(flt(p.billed_amt)), abs(flt(p.amount))) for p in positionen) + sum(
		flt(z.billing_amount) for z in zeiten if z.sales_invoice
	)
	if not gesamt:
		# Zeiten ohne Stundensatz und keine Positionen mit Betrag: nach Stunden
		stunden = [flt(z.billing_hours) or flt(z.hours) for z in zeiten]
		gesamt = sum(stunden)
		berechnet = sum(h for h, z in zip(stunden, zeiten, strict=True) if z.sales_invoice)

	prozent = round(berechnet / gesamt * 100, 6) if gesamt else 0
	if prozent < 0.001:
		status = "Not Billed"
	elif prozent > 99.999999:
		status = "Fully Billed"
	else:
		status = "Partly Billed"

	doc = frappe.get_doc("Sales Order", sales_order)
	if flt(doc.per_billed, 6) == prozent and doc.billing_status == status:
		return
	doc.db_set({"per_billed": prozent, "billing_status": status}, notify=True)
	doc.set_status(update=True)


def on_timesheet_change(doc, method=None):
	"""Zeitblatt gebucht/storniert - auch die aus Kundeneinsatz und Fahrt."""
	update_sales_orders(row.get("custom_sales_order") for row in doc.time_logs)


def on_sales_order_submit(doc, method=None):
	"""Ein Auftrag kann erst nach den Einsaetzen gebucht werden (Entwurf aus
	"Neuer Auftrag") - deren Zeiten sind dann vielleicht schon abgerechnet."""
	update_sales_orders([doc.name])


def sales_orders_of_invoice(doc):
	auftraege = {item.sales_order for item in doc.items if item.get("sales_order")}
	details = [row.timesheet_detail for row in doc.get("timesheets") or [] if row.timesheet_detail]
	if details:
		auftraege.update(
			frappe.get_all(
				"Timesheet Detail",
				filters={"name": ["in", details], "custom_sales_order": ["is", "set"]},
				pluck="custom_sales_order",
			)
		)
	return auftraege
