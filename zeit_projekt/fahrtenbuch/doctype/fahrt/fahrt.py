import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_datetime, time_diff_in_hours


class Fahrt(Document):
	def validate(self):
		"""End/Kilometerstand sind erst beim Buchen Pflicht (siehe
		before_submit) - beim blossen Speichern als Entwurf, z. B. durch den
		Timer ("Timer starten" speichert sofort, damit die Startzeit einen
		Reload uebersteht), sind sie oft noch leer. Deshalb hier nur rechnen/
		pruefen, wenn beide Werte eines Paars tatsaechlich vorliegen."""
		if self.start_time and self.end_time:
			if get_datetime(self.end_time) <= get_datetime(self.start_time):
				frappe.throw(_("Das Ende muss nach dem Beginn liegen."))
			self.duration_hours = flt(time_diff_in_hours(self.end_time, self.start_time), 2)

		if self.start_odometer is not None and self.end_odometer is not None:
			# Kein frappe.throw hier, wenn end < start: waehrend eines Entwurfs
			# (z. B. nach einem falschen OCR-Treffer, den man noch korrigieren
			# will) darf das Speichern nicht blockiert sein - nur das Buchen
			# selbst (siehe before_submit unten). Trotzdem darf hier keine
			# negative Zahl im Feld stehen bleiben - bis der Endstand korrigiert
			# ist, bleibt distance_km einfach leer statt falsch/negativ.
			if self.end_odometer >= self.start_odometer:
				self.distance_km = self.end_odometer - self.start_odometer
			else:
				self.distance_km = None

	def before_submit(self):
		"""Was zum Buchen fehlen darf, aber nicht zum Buchen selbst: hier statt
		als reqd im Feld, damit ein Entwurf (z. B. per Timer gestartet, noch
		mitten in der Fahrt) jederzeit speicherbar bleibt."""
		if not self.end_time:
			frappe.throw(_("Bitte vor dem Buchen eine Endzeit eintragen."))
		if self.start_odometer is None or self.end_odometer is None:
			frappe.throw(_("Bitte vor dem Buchen beide Kilometerstände eintragen."))
		if self.end_odometer < self.start_odometer:
			frappe.throw(_("Der Kilometerstand am Ende darf nicht kleiner als am Anfang sein."))
		if not self.sales_order:
			frappe.throw(_("Bitte vor dem Buchen einen Auftrag wählen."))
		if not self.time_item:
			frappe.throw(_("Bitte vor dem Buchen einen Artikel für die Fahrzeit wählen."))
