"""Neue Einstellungen "Prüfungen und Erinnerungen" mit ihren Standardwerten füllen.

Ein schon gespeichertes Single-Doc bekommt die Standardwerte neuer Felder nicht (Häkchen wären
aus, Zahlen 0) - hier einmalig setzen."""

import frappe


def execute():
	frappe.db.set_single_value(
		"Zeit Projekt Einstellungen",
		{
			"vehicle_required": 1,
			"max_km_luecke": 500,
			"reminders_enabled": 1,
			"reminder_running_hours": 10,
			"reminder_end_hours": 2,
		},
	)
