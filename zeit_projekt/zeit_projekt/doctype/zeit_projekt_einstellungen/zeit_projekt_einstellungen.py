import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt
from frappe.utils.nestedset import get_descendants_of


# Tabellenspalte -> Feld der Aktivitaetsart
AKTIVITAET_FELDER = {
	"dienstleistungsartikel": "custom_dienstleistungsartikel",
	"rechnungstext": "custom_rechnungstext",
	"billing_rate": "billing_rate",
}


class ZeitProjektEinstellungen(Document):
	def onload(self):
		"""Die Tabelle "Aktivitätsarten" ist nur eine Ansicht: maßgeblich sind
		die Felder an der Aktivitätsart selbst (dort lesen Zeitimport und
		"Neuer Auftrag"). Deshalb bei jedem Öffnen frisch aus den aktiven
		Aktivitätsarten füllen - auch Änderungen direkt an einer
		Aktivitätsart sind so sofort zu sehen."""
		self.set("aktivitaetsarten", [])
		for at in frappe.get_all(
			"Activity Type",
			filters={"disabled": 0},
			fields=["name", *AKTIVITAET_FELDER.values()],
			order_by="name asc",
		):
			self.append(
				"aktivitaetsarten",
				{"activity_type": at.name, **{spalte: at.get(feld) for spalte, feld in AKTIVITAET_FELDER.items()}},
			)
		self.set_artikelpreise()

	def set_artikelpreise(self):
		preisliste = frappe.db.get_single_value("Selling Settings", "selling_price_list")
		for row in self.aktivitaetsarten:
			row.artikelpreis = (
				frappe.db.get_value(
					"Item Price",
					{"item_code": row.dienstleistungsartikel, "price_list": preisliste, "selling": 1},
					"price_list_rate",
				)
				if row.dienstleistungsartikel and preisliste
				else None
			)

	def validate(self):
		self.validate_aktivitaetsarten()
		for row in self.excluded_item_groups:
			if not frappe.db.get_value("Item Group", row.item_group, "parent_item_group"):
				frappe.throw(
					_("Die oberste Artikelgruppe {0} würde alle Artikel ausschließen.").format(
						frappe.bold(row.item_group)
					)
				)
		self.aktivitaetsarten_zurueckschreiben()

	def validate_aktivitaetsarten(self):
		gesehen = set()
		for row in self.aktivitaetsarten:
			if row.activity_type in gesehen:
				frappe.throw(
					_("Zeile {0}: Aktivitätsart {1} steht doppelt in der Tabelle.").format(
						row.idx, frappe.bold(row.activity_type)
					)
				)
			gesehen.add(row.activity_type)
			if row.dienstleistungsartikel:
				artikel = frappe.db.get_value(
					"Item", row.dienstleistungsartikel, ["disabled", "is_sales_item"], as_dict=True
				)
				if not artikel or artikel.disabled or not artikel.is_sales_item:
					frappe.throw(
						_("Zeile {0}: Artikel {1} ist gesperrt oder kein Verkaufsartikel.").format(
							row.idx, frappe.bold(row.dienstleistungsartikel)
						)
					)

	def aktivitaetsarten_zurueckschreiben(self):
		"""Werte der Tabelle in die Aktivitätsarten schreiben (über deren
		eigenes Speichern, also mit Validierung und Änderungsverlauf). Die
		Tabelle selbst wird nicht gespeichert - sonst überschriebe ein späteres
		Speichern der Einstellungen ohne geöffnetes Formular (z. B. per Code)
		neuere Änderungen an den Aktivitätsarten mit alten Werten."""
		for row in self.aktivitaetsarten:
			at = frappe.get_doc("Activity Type", row.activity_type)
			geaendert = False
			for spalte, feld in AKTIVITAET_FELDER.items():
				neu = row.get(spalte)
				alt = at.get(feld)
				gleich = flt(neu) == flt(alt) if feld == "billing_rate" else (neu or None) == (alt or None)
				if not gleich:
					at.set(feld, neu or (0 if feld == "billing_rate" else None))
					geaendert = True
			if geaendert:
				at.save()
		# Das Formular fuellt sie nach dem Speichern ueber onload() neu
		# (frappe.desk.form.save.savedocs -> run_onload).
		self.set("aktivitaetsarten", [])


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
