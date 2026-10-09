import erpnext
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate


class SiteVisit(Document):
	def validate(self):
		if not self.company:
			self.company = erpnext.get_default_company()
		if self.is_new() and not self.amended_from:
			# added_to_order wird mitkopiert, damit eine Berichtigung bereits im
			# Auftrag stehende Zeilen nicht doppelt uebernimmt - bei einem
			# duplizierten (neuen) Einsatz muessen sie dagegen neu hinein.
			for row in self.extra_items:
				row.added_to_order = 0
		self.set_from_sales_order()
		self.set_link_names()
		self.set_extra_item_rates()

	def set_from_sales_order(self):
		"""Der Auftrag ist Pflicht und bestimmt den Kunden: fehlt der Kunde,
		kommt er aus dem Auftrag; ein Auftrag eines anderen Kunden wird schon
		beim Speichern abgelehnt (nicht erst beim Buchen)."""
		from zeit_projekt.zeit_projekt.billing import check_sales_order

		if not self.sales_order:
			return
		so = frappe.db.get_value("Sales Order", self.sales_order, ["customer", "project"], as_dict=True)
		if not so:
			frappe.throw(_("Auftrag {0} existiert nicht.").format(self.sales_order))
		self.customer = self.customer or so.customer
		self.project = self.project or so.project
		if self.is_new() or self.has_value_changed("sales_order") or self.has_value_changed("customer"):
			check_sales_order(self.sales_order, self.customer)

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
