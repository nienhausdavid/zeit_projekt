"""Erinnerungen fuer vergessene Fahrten (stuendlicher Scheduler-Job).

Zwei Faelle, je Fahrt und Art nur einmal (Merker-Haken an der Fahrt):
- Der Timer laeuft laenger als "Timer laeuft laenger als (Stunden)".
- Die Fahrt wurde beendet, der Endstand fehlt aber noch nach "Endstand fehlt nach (Stunden)".
Benachrichtigt wird der Benutzer des Mitarbeiters, sonst der Ersteller der Fahrt - als
Eintrag in der Glocke des Desks (Notification Log)."""

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, now_datetime


def pruefe_fahrten(nur=None):
	"""nur: Liste von Fahrt-Namen, auf die die Pruefung beschraenkt wird (fuer Tests)."""
	einstellungen = frappe.get_cached_doc("Zeit Projekt Einstellungen")
	if not cint(einstellungen.reminders_enabled):
		return
	jetzt = now_datetime()

	stunden = cint(einstellungen.reminder_running_hours)
	if stunden > 0:
		for fahrt in frappe.get_all(
			"Fahrt",
			filters={
				"docstatus": 0,
				"start_time": ["<", add_to_date(jetzt, hours=-stunden)],
				"end_time": ["is", "not set"],
				"reminder_running_sent": 0,
				**({"name": ["in", nur]} if nur is not None else {}),
			},
			fields=["name", "employee", "owner"],
		):
			_erinnere(
				fahrt,
				"reminder_running_sent",
				_("Fahrt {0}: Der Timer läuft seit mehr als {1} Stunden").format(fahrt.name, stunden),
				_("Bitte die Fahrt beenden und den Endstand eintragen, falls sie schon zu Ende ist."),
			)

	stunden = cint(einstellungen.reminder_end_hours)
	if stunden > 0:
		for fahrt in frappe.get_all(
			"Fahrt",
			# Frappe vergleicht "<" mit IFNULL(feld, 0001-01-01): ohne "ist gesetzt" kaemen auch
			# laufende Fahrten ohne Ende in die Liste
			filters=[
				["Fahrt", "docstatus", "=", 0],
				["Fahrt", "end_time", "is", "set"],
				["Fahrt", "end_time", "<", add_to_date(jetzt, hours=-stunden)],
				["Fahrt", "end_odometer", "=", 0],
				["Fahrt", "reminder_end_sent", "=", 0],
				*([["Fahrt", "name", "in", nur]] if nur is not None else []),
			],
			fields=["name", "employee", "owner"],
		):
			_erinnere(
				fahrt,
				"reminder_end_sent",
				_("Fahrt {0}: Der Endstand fehlt").format(fahrt.name),
				_("Die Fahrt ist beendet, aber der Kilometerstand am Ende ist noch nicht eingetragen."),
			)


def _empfaenger(fahrt):
	user = frappe.db.get_value("Employee", fahrt.employee, "user_id") if fahrt.employee else None
	return user or fahrt.owner


def _erinnere(fahrt, merker, betreff, text):
	user = _empfaenger(fahrt)
	if user and frappe.db.get_value("User", user, "enabled"):
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"type": "Alert",
				"subject": betreff,
				"email_content": text,
				"for_user": user,
				"document_type": "Fahrt",
				"document_name": fahrt.name,
			}
		).insert(ignore_permissions=True)
	# Auch ohne Empfaenger als erledigt markieren, sonst wird jede Stunde neu gesucht
	frappe.db.set_value("Fahrt", fahrt.name, merker, 1, update_modified=False)
