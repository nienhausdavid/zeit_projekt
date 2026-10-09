import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, get_datetime, time_diff_in_hours


class Fahrt(Document):
	def validate(self):
		"""Ende/Kilometerstand sind erst beim Buchen Pflicht (siehe
		before_submit) - beim Speichern als Entwurf, z. B. durch den Timer,
		sind sie oft noch leer. Hier nur rechnen, wenn die Werte vorliegen.

		Leere Int-Felder speichert Frappe als 0 (Spalte NOT NULL DEFAULT 0),
		"leer" ist hier also immer 0, nie None."""
		if self.start_time and self.end_time:
			if get_datetime(self.end_time) <= get_datetime(self.start_time):
				frappe.throw(_("Das Ende muss nach dem Beginn liegen."))
			self.duration_hours = flt(time_diff_in_hours(self.end_time, self.start_time), 2)

		# Kein throw bei end < start: ein falscher OCR-Treffer soll speicherbar
		# bleiben, bis er korrigiert ist - nur das Buchen blockiert (unten).
		start, end = cint(self.start_odometer), cint(self.end_odometer)
		self.distance_km = end - start if start and end and end >= start else 0

	def before_submit(self):
		"""Was zum Speichern fehlen darf, aber nicht zum Buchen."""
		if not self.customer:
			self.customer = self._customer_from_links()
		if not self.end_time:
			frappe.throw(_("Bitte vor dem Buchen eine Endzeit eintragen."))
		if not cint(self.start_odometer) or not cint(self.end_odometer):
			frappe.throw(_("Bitte vor dem Buchen beide Kilometerstände eintragen."))
		if cint(self.end_odometer) < cint(self.start_odometer):
			frappe.throw(_("Der Kilometerstand am Ende darf nicht kleiner als am Anfang sein."))
		if not self.customer:
			frappe.throw(_("Bitte vor dem Buchen einen Kunden wählen."))
		if not self.activity_type:
			frappe.throw(_("Bitte vor dem Buchen eine Aktivitätsart für die Fahrzeit wählen."))
		if not flt(self.duration_hours):
			frappe.throw(_("Die Fahrzeit ist 0 Stunden."))
		if self.bill_km:
			if not self.km_item:
				frappe.throw(_("Bitte einen Artikel für die Kilometer wählen."))
			if not self.distance_km:
				frappe.throw(_("Die Strecke ist 0 km - Kilometer können nicht abgerechnet werden."))

	def _customer_from_links(self):
		for doctype, name in (("Project", self.project), ("Sales Order", self.sales_order), ("Site Visit", self.site_visit)):
			if name:
				customer = frappe.db.get_value(doctype, name, "customer")
				if customer:
					return customer
