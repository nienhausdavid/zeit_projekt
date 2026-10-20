import erpnext
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from zeit_projekt.zeit_projekt.billing import check_employee_required
from zeit_projekt.zeit_projekt.pausen import arbeitsabschnitte, pausen_pruefen


class SiteVisit(Document):
	def validate(self):
		check_employee_required(self)
		if not self.company:
			self.company = erpnext.get_default_company()
		if self.is_new() and not self.amended_from:
			# added_to_order wird mitkopiert, damit eine Berichtigung bereits im
			# Auftrag stehende Zeilen nicht doppelt uebernimmt - bei einem
			# duplizierten (neuen) Einsatz muessen sie dagegen neu hinein.
			for row in self.extra_items:
				row.added_to_order = 0
		self.set_from_links()
		self.set_link_names()
		self.validate_extra_item_groups()
		self.set_extra_item_rates()
		self.validate_breaks()
		self.working_hours = (
			sum((bis - ab).total_seconds() for ab, bis in self.get_work_segments()) / 3600
			if self.to_time
			else 0
		)

	def validate_breaks(self):
		"""Pausen muessen im Einsatzzeitraum liegen und duerfen sich nicht
		ueberschneiden - gemeinsame Logik mit der Fahrt (zeit_projekt/pausen.py)."""
		pausen_pruefen(self, "from_time", "to_time")

	def get_work_segments(self):
		"""Einsatzzeitraum ohne Pausen als Liste von (ab, bis) - je Abschnitt
		eine Zeitblatt-Zeile (siehe zeit_projekt/pausen.py)."""
		return arbeitsabschnitte(self, "from_time", "to_time")

	def set_from_links(self):
		"""Jeder Einsatz gehoert zu einem Auftrag ODER einem Projekt (oder
		beidem). Der Auftrag bestimmt Kunde und - falls leer - Projekt, sonst
		das Projekt den Kunden. Auftrag/Projekt eines anderen Kunden werden
		schon beim Speichern abgelehnt (nicht erst beim Buchen).

		Ohne Auftrag laeuft die Abrechnung ueber das Projekt: die Zeit steht im
		Zeitblatt und kommt mit dem Zeitimport in die Rechnung. Zusatzartikel
		gibt es nur mit Auftrag - sie werden dort eingetragen."""
		from zeit_projekt.zeit_projekt.billing import check_project, check_sales_order

		if not self.sales_order and not self.project:
			frappe.throw(
				_("Bitte einen Auftrag oder ein Projekt wählen – darüber wird der Einsatz abgerechnet."),
				frappe.MandatoryError,
			)

		if self.sales_order:
			so = frappe.db.get_value("Sales Order", self.sales_order, ["customer", "project"], as_dict=True)
			if not so:
				frappe.throw(_("Auftrag {0} existiert nicht.").format(self.sales_order))
			self.customer = self.customer or so.customer
			self.project = self.project or so.project
			if self.is_new() or self.has_value_changed("sales_order") or self.has_value_changed("customer"):
				check_sales_order(self.sales_order, self.customer)

		if self.project:
			# Geprueft wird nur bei neuem Einsatz oder geaenderter Zuordnung: ein
			# alter Einsatz auf einem inzwischen stornierten Projekt bleibt
			# bearbeitbar (vor dem Buchen prueft before_submit noch einmal).
			if self.is_new() or self.has_value_changed("project") or self.has_value_changed("customer"):
				projekt_kunde = check_project(self.project, self.customer)
			else:
				projekt_kunde = frappe.db.get_value("Project", self.project, "customer")
			self.customer = self.customer or projekt_kunde

		if not self.sales_order and any(row.item_code and not row.added_to_order for row in self.extra_items):
			frappe.throw(
				_(
					"Zusatzartikel werden über den Auftrag abgerechnet. Bitte einen Auftrag wählen "
					"oder über „Neuer Auftrag“ anlegen."
				)
			)

	def set_link_names(self):
		"""Ersatz fuer fetch_from: das holt im Browser mit den Rechten des
		Nutzers, und Techniker duerfen Kunde/Artikel nicht lesen."""
		self.customer_name = (
			frappe.db.get_value("Customer", self.customer, "customer_name") if self.customer else None
		)
		for row in self.extra_items:
			if row.item_code:
				item_name, stock_uom = frappe.db.get_value(
					"Item", row.item_code, ["item_name", "stock_uom"]
				) or (None, None)
				row.item_name = item_name
				row.uom = row.uom or stock_uom

	def validate_extra_item_groups(self):
		"""Die Artikelsuche blendet ausgeschlossene Gruppen und Dienstleistungsartikel aus - hier
		dasselbe fuer Eingaben ueber API/Import. Bereits uebernommene Zeilen bleiben."""
		from zeit_projekt.zeit_projekt.doctype.zeit_projekt_einstellungen.zeit_projekt_einstellungen import (
			excluded_item_groups,
			gesperrte_artikel,
		)

		ausgeschlossen = excluded_item_groups()
		gesperrt = gesperrte_artikel()
		for row in self.extra_items:
			if not row.item_code or row.added_to_order:
				continue
			if row.item_code in gesperrt:
				frappe.throw(
					_("Zeile {0}: Artikel {1} ist ein Dienstleistungsartikel und kann nicht als Zusatzartikel gebucht werden.").format(
						row.idx, frappe.bold(row.item_code)
					)
				)
			if not ausgeschlossen:
				continue
			gruppe = frappe.db.get_value("Item", row.item_code, "item_group")
			if gruppe in ausgeschlossen:
				frappe.throw(
					_("Zeile {0}: Artikel {1} gehört zur Artikelgruppe {2}, die als Zusatzartikel ausgeschlossen ist.").format(
						row.idx, frappe.bold(row.item_code), frappe.bold(gruppe)
					)
				)

	def set_extra_item_rates(self):
		"""Preis der Zusatzartikel kommt aus ERPNext (Preisliste/Preisregeln
		des Kunden bzw. des verknuepften Auftrags), nicht vom Techniker - rate
		ist im Formular schreibgeschuetzt. Nur zur Anzeige; beim Uebernehmen in
		den Auftrag wird erneut gerechnet. Fehlender Preis blockiert hier noch
		nicht, erst beim Buchen."""
		from zeit_projekt.zeit_projekt.billing import as_administrator, price_rows

		rows = [row for row in self.extra_items if row.item_code and not row.added_to_order]
		if not rows or not self.customer:
			return

		with as_administrator():
			if self.sales_order:
				header = frappe.get_doc("Sales Order", self.sales_order)
			else:
				header = frappe.new_doc("Sales Order")
				header.update(
					{
						"customer": self.customer,
						"company": self.company,
						"project": self.project,
						"transaction_date": self.date or nowdate(),
					}
				)
			priced = price_rows(
				header,
				[{"item_code": r.item_code, "qty": r.qty or 1, "uom": r.uom, "description": ""} for r in rows],
				throw=False,
			)

		for row, price in zip(rows, priced, strict=True):
			row.rate = price["rate"]
			row.amount = flt(price["rate"]) * flt(row.qty)
