"""Die neuen Schalter "Knöpfe im Fahrt-Formular" sind standardmäßig an.

Bei einem schon gespeicherten Single-Doctype bekommen neue Felder ihren
Standardwert nicht, sondern wären 0 (= alle Knöpfe weg). Deshalb hier einmalig
auf 1 setzen."""

import frappe


def execute():
	for feld in ("knopf_timer", "knopf_foto", "knopf_timer_foto"):
		frappe.db.set_single_value("Zeit Projekt Einstellungen", feld, 1)
