import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.nestedset import get_descendants_of


class ZeitProjektEinstellungen(Document):
	def validate(self):
		for row in self.excluded_item_groups:
			if not frappe.db.get_value("Item Group", row.item_group, "parent_item_group"):
				frappe.throw(
					_("Die oberste Artikelgruppe {0} würde alle Artikel ausschließen.").format(
						frappe.bold(row.item_group)
					)
				)


def excluded_item_groups():
	"""Artikelgruppen (inkl. Untergruppen), die als Zusatzartikel im
	Kundeneinsatz nicht waehlbar sind. Ohne Rechtepruefung gelesen - auch
	Techniker brauchen die Liste, duerfen die Einstellungen aber nicht lesen."""
	gruppen = set()
	for gruppe in frappe.get_all(
		"Zeit Projekt Artikelgruppe",
		filters={"parenttype": "Zeit Projekt Einstellungen", "parentfield": "excluded_item_groups"},
		pluck="item_group",
	):
		gruppen.add(gruppe)
		gruppen.update(get_descendants_of("Item Group", gruppe))
	return gruppen


@frappe.whitelist()
def get_einstellungen():
	"""Einstellungen fuer das Formular-Skript. Faellt auf die Standardwerte
	zurueck, solange die Einstellungen noch nie gespeichert wurden."""
	doc = frappe.get_cached_doc("Zeit Projekt Einstellungen")
	return {
		"positionsbezeichnung": doc.positionsbezeichnung or "Nur Datum und Uhrzeit",
		"lieferdatum_quelle": doc.lieferdatum_quelle or "Beginn der Zeitbuchung",
	}
