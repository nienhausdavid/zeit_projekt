"""Fahrtenbuch Einstellungen -> Zeit Projekt Einstellungen.

Alle Einstellungen liegen jetzt an einem Ort. Die gespeicherten Werte des
alten Single-Doctypes "Fahrtenbuch Einstellungen" werden uebernommen (auch der
API-Schluessel, der verschluesselt in __Auth liegt), danach wird der alte
Doctype entfernt. Laeuft nach der Modell-Synchronisation, damit die neuen
Felder in "Zeit Projekt Einstellungen" schon existieren."""

import frappe
from frappe.utils import cint
from frappe.utils.password import get_decrypted_password

ALT = "Fahrtenbuch Einstellungen"
NEU = "Zeit Projekt Einstellungen"
FELDER = (
	"api_type", "api_url", "model", "image_original", "max_image_px", "context_length", "keep_alive",
	"activity_type", "km_item", "rounding_minutes", "auto_start_timer", "auto_open_camera", "capture_location",
)  # fmt: skip


def execute():
	if not frappe.db.exists("DocType", ALT):
		return

	# Direkt aus tabSingles (kein get_values: Singles hat keine Spalte "creation")
	werte = dict(frappe.db.sql("select field, value from `tabSingles` where doctype=%s", (ALT,)))
	felder = {df.fieldname: df for df in frappe.get_meta(NEU).fields}
	standard = {name: df.default for name, df in felder.items() if df.default}

	def typisiert(feld, wert):
		# tabSingles speichert alles als Text; die Pruefungen vergleichen Zahlen
		return cint(wert) if felder[feld].fieldtype in ("Int", "Check") else wert

	doc = frappe.get_doc(NEU)
	for feld in FELDER:
		if werte.get(feld) not in (None, ""):
			doc.set(feld, typisiert(feld, werte[feld]))
		elif feld in standard:
			# Neue Felder einer schon gespeicherten Single bekommen ihren Standardwert nicht
			# von selbst (er gilt nur fuer neue Dokumente) - sonst stuenden z. B. "Timer
			# automatisch starten" und "Kamera automatisch oeffnen" (Standard an) auf 0.
			doc.set(feld, typisiert(feld, standard[feld]))

	schluessel = get_decrypted_password(ALT, ALT, "api_key", raise_exception=False)
	if schluessel:
		doc.api_key = schluessel
	doc.flags.ignore_permissions = True
	doc.save()

	frappe.delete_doc("DocType", ALT, force=True, ignore_missing=True)
	frappe.db.delete("Singles", {"doctype": ALT})
	frappe.db.delete("__Auth", {"doctype": ALT})
	frappe.clear_cache(doctype=NEU)
