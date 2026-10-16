"""Neuer Schalter "Endstand fotografieren und Fahrt beenden": standardmäßig an.

Wie bei knoepfe_standard_an: ein schon gespeichertes Single-Doc bekommt den Standardwert
eines neuen Feldes nicht, der Knopf wäre sonst bei bestehenden Installationen aus."""

import frappe


def execute():
	frappe.db.set_single_value("Zeit Projekt Einstellungen", "knopf_ende_foto", 1)
