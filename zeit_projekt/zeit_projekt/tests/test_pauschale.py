import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from zeit_projekt.site_visit.site_visit import create_sales_order
from zeit_projekt.zeit_projekt.report.abrechnungsansicht.abrechnungsansicht import execute as abrechnung
from zeit_projekt.zeit_projekt.sales_invoice import get_billable_time_logs
from zeit_projekt.zeit_projekt.tests.utils import (
	FAHRZEIT,
	KUNDE_A,
	MONTAGE,
	ensure_fixtures,
	ensure_vehicle,
	expect_error,
)


class TestPauschale(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = ensure_fixtures()
		cls.vehicle = ensure_vehicle()

	def tearDown(self):
		frappe.set_user("Administrator")

	def auftrag(self, **kwargs):
		return create_sales_order(KUNDE_A, MONTAGE, **kwargs)

	def einsatz(self, so, tag, von="10:00:00", bis="12:00:00"):
		sv = frappe.get_doc(
			{
				"doctype": "Site Visit",
				"customer": KUNDE_A,
				"employee": self.ctx.employee,
				"activity_type": MONTAGE,
				"date": f"2031-06-{tag:02d}",
				"from_time": f"2031-06-{tag:02d} {von}",
				"to_time": f"2031-06-{tag:02d} {bis}",
				"sales_order": so,
				"description": "Montage",
			}
		).insert()
		sv.submit()
		return sv

	def fahrt(self, so, tag, km=(1000, 1042)):
		f = frappe.get_doc(
			{
				"doctype": "Fahrt",
				"employee": self.ctx.employee,
				"date": f"2031-06-{tag:02d}",
				"vehicle": self.vehicle,
				"sales_order": so,
				"start_time": f"2031-06-{tag:02d} 14:00:00",
				"end_time": f"2031-06-{tag:02d} 15:00:00",
				"start_odometer": km[0],
				"end_odometer": km[1],
				"activity_type": FAHRZEIT,
				"bill_km": 1,
				"km_item": "ZP-KM",
			}
		).insert()
		f.submit()
		return f

	def test_neuer_auftrag_mit_abrechnungsart_und_planung(self):
		so = frappe.get_doc("Sales Order", self.auftrag(abrechnungsart="Pauschale", geplante_stunden=12.5))
		self.assertEqual((so.custom_abrechnungsart, flt(so.custom_geplante_stunden)), ("Pauschale", 12.5))
		standard = frappe.get_doc("Sales Order", self.auftrag())
		self.assertNotEqual(so.items[0].description, standard.items[0].description)  # eigener Hinweistext
		self.assertEqual(standard.custom_abrechnungsart, "Nach Aufwand")
		self.assertFalse(standard.custom_geplante_stunden)

	def test_ungueltige_angaben_abgelehnt(self):
		with expect_error(self):
			self.auftrag(abrechnungsart="Irgendwas")
		with expect_error(self):
			self.auftrag(geplante_stunden=-1)

	def test_pauschale_zeit_wird_erfasst_aber_nicht_abgerechnet(self):
		pauschal = self.auftrag(abrechnungsart="Pauschale")
		aufwand = self.auftrag()
		sv_p = self.einsatz(pauschal, 1)
		sv_a = self.einsatz(aufwand, 2)

		zeile_p = frappe.get_doc("Timesheet", sv_p.timesheet).time_logs[0]
		zeile_a = frappe.get_doc("Timesheet", sv_a.timesheet).time_logs[0]
		self.assertEqual((zeile_p.is_billable, flt(zeile_p.hours)), (0, 2.0))  # Zeit ist trotzdem erfasst
		self.assertEqual(zeile_a.is_billable, 1)

		importiert = [z.sales_order or z.custom_sales_order for z in get_billable_time_logs(KUNDE_A)["rows"]]
		self.assertNotIn(pauschal, importiert)
		self.assertIn(aufwand, importiert)
		offen = {z.sales_order for z in abrechnung({"customer": KUNDE_A})[1]}
		self.assertNotIn(pauschal, offen)
		self.assertIn(aufwand, offen)

	def test_pauschale_kilometer_werden_nicht_abgerechnet(self):
		pauschal = self.auftrag(abrechnungsart="Pauschale")
		aufwand = self.auftrag()
		fp = self.fahrt(pauschal, 3, (1000, 1042))
		fa = self.fahrt(aufwand, 4, (1042, 1100))

		km = {f.name for f in get_billable_time_logs(KUNDE_A)["kilometers"]}
		self.assertNotIn(fp.name, km)
		self.assertIn(fa.name, km)
		self.assertEqual(abrechnung({"customer": KUNDE_A, "sales_order": pauschal})[1], [])  # auch keine Fahrzeit
