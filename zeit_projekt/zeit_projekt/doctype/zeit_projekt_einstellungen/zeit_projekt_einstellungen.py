import frappe
from frappe.model.document import Document


class ZeitProjektEinstellungen(Document):
	pass


@frappe.whitelist()
def get_einstellungen():
	"""Einstellungen fuer das Formular-Skript. Faellt auf die Standardwerte
	zurueck, solange die Einstellungen noch nie gespeichert wurden."""
	doc = frappe.get_cached_doc("Zeit Projekt Einstellungen")
	return {
		"positionsbezeichnung": doc.positionsbezeichnung or "Nur Datum und Uhrzeit",
		"lieferdatum_quelle": doc.lieferdatum_quelle or "Beginn der Zeitbuchung",
	}
