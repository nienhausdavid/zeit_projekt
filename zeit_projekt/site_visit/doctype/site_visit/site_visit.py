import erpnext
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_datetime, nowdate


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
		self.validate_breaks()
		self.working_hours = (
			sum((bis - ab).total_seconds() for ab, bis in self.get_work_segments()) / 3600
			if self.to_time
			else 0
		)

	def validate_breaks(self):
		"""Pausen muessen im Einsatzzeitraum liegen und duerfen sich nicht
		ueberschneiden. Hoechstens eine darf noch laufen; endet der Einsatz
		waehrend einer Pause ("Timer stoppen" in der Pause), endet sie mit ihm."""
		if not self.from_time:
			return
		if self.to_time:
			for row in self.breaks:
				if not row.to_time:
					row.to_time = self.to_time

		beginn = get_datetime(self.from_time)
		ende = get_datetime(self.to_time) if self.to_time else None
		vorher_bis = None
		for row in sorted(self.breaks, key=lambda r: get_datetime(r.from_time)):
			ab = get_datetime(row.from_time)
			bis = get_datetime(row.to_time) if row.to_time else None
			if ab < beginn or (ende and (bis or ab) > ende):
				frappe.throw(_("Zeile {0}: Die Pause muss innerhalb des Einsatzzeitraums liegen.").format(row.idx))
			if bis and bis < ab:
				frappe.throw(_("Zeile {0}: Das Ende der Pause muss nach ihrem Beginn liegen.").format(row.idx))
			if vorher_bis and ab < vorher_bis:
				frappe.throw(_("Zeile {0}: Die Pause überschneidet sich mit einer anderen.").format(row.idx))
			# Eine laufende Pause blockiert alles danach - so kann nur die
			# letzte Pause offen sein.
			vorher_bis = bis or get_datetime("9999-12-31")

	def get_work_segments(self):
		"""Einsatzzeitraum ohne Pausen als Liste von (ab, bis) - je Abschnitt
		eine Zeitblatt-Zeile, damit Pausen weder abgerechnet werden noch mit
		einer Zeitbuchung kollidieren, die der Techniker waehrend der Pause
		(z. B. Notfall bei einem anderen Kunden) erfasst."""
		if not (self.from_time and self.to_time):
			return []
		zeiger = get_datetime(self.from_time)
		ende = get_datetime(self.to_time)
		abschnitte = []
		for row in sorted(self.breaks, key=lambda r: get_datetime(r.from_time)):
			ab, bis = get_datetime(row.from_time), get_datetime(row.to_time)
			if ab > zeiger:
				abschnitte.append((zeiger, ab))
			zeiger = max(zeiger, bis)
		if zeiger < ende:
			abschnitte.append((zeiger, ende))
		return abschnitte

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
