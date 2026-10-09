import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from zeit_projekt.zeit_projekt.sales_invoice import get_billable_time_logs
from zeit_projekt.zeit_projekt.tests.utils import (
	FAHRZEIT,
	KUNDE_A,
	TECH,
	ensure_fixtures,
	expect_error,
	make_sales_order,
	sales_order_rows,
)


class TestFahrt(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = ensure_fixtures()
		cls.so = make_sales_order(cls.ctx.company)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Fahrtenbuch Einstellungen", "rounding_minutes", 0)

	def fahrt(self, start="2031-03-10 08:00:00", end="2031-03-10 09:30:00", km=(1000, 1042), bill_km=1, so=True):
		return frappe.get_doc(
			{
				"doctype": "Fahrt",
				"employee": self.ctx.employee,
				"date": start[:10],
				"sales_order": self.so.name if so else None,
				"start_time": start,
				"end_time": end,
				"start_odometer": km[0],
				"end_odometer": km[1],
				"start_location": "Werkstatt",
				"end_location": "Kunde",
				"activity_type": FAHRZEIT,
				"bill_km": bill_km,
				"km_item": "ZP-KM" if bill_km else None,
			}
		).insert()

	def test_buchen_legt_zeitblatt_an_und_laesst_auftrag_unveraendert(self):
		vorher = len(sales_order_rows(self.so.name))
		frappe.set_user(TECH)
		f = self.fahrt()
		f.submit()

		self.assertEqual(f.customer, KUNDE_A)
		self.assertEqual(len(sales_order_rows(self.so.name)), vorher)
		ts = frappe.get_doc("Timesheet", f.timesheet)
		self.assertEqual(ts.docstatus, 1)
		self.assertEqual(ts.customer, KUNDE_A)
		self.assertEqual(ts.time_logs[0].activity_type, FAHRZEIT)
		self.assertEqual(flt(ts.time_logs[0].hours), 1.5)
		self.assertIn(f.name, ts.time_logs[0].description)

	def test_taktung(self):
		frappe.db.set_single_value("Fahrtenbuch Einstellungen", "rounding_minutes", 15)
		f = self.fahrt("2031-03-11 08:00:00", "2031-03-11 08:50:00")
		f.submit()
		log = frappe.get_doc("Timesheet", f.timesheet).time_logs[0]
		self.assertAlmostEqual(flt(log.hours), 50 / 60, places=3)
		self.assertEqual(flt(log.billing_hours), 1.0)

	def test_pflichtfelder_vor_dem_buchen(self):
		ohne_km = self.fahrt("2031-03-12 08:00:00", "2031-03-12 09:00:00", km=(0, 0), bill_km=0)
		ohne_km.reload()
		self.assertEqual(ohne_km.start_odometer, 0)  # leer wird als 0 gespeichert
		with expect_error(self):
			ohne_km.submit()

		ohne_kunde = self.fahrt("2031-03-13 08:00:00", "2031-03-13 09:00:00", so=False)
		with expect_error(self):
			ohne_kunde.submit()

	def test_kilometer_ueber_rechnung_genau_einmal(self):
		f = self.fahrt("2031-03-14 08:00:00", "2031-03-14 09:00:00")
		f.submit()

		r = get_billable_time_logs(KUNDE_A, from_time="2031-03-14 00:00:00", to_time="2031-03-14 23:59:59")
		km = {k.name: k for k in r["kilometers"]}
		self.assertIn(f.name, km)
		self.assertEqual(km[f.name].distance_km, 42)
		self.assertEqual(km[f.name].km_item, "ZP-KM")
		self.assertIn(f.name, km[f.name].description)
		self.assertTrue(any(z.time_sheet == f.timesheet for z in r["rows"]))

		def rechnung():
			return frappe.get_doc(
				{
					"doctype": "Sales Invoice",
					"customer": KUNDE_A,
					"company": self.ctx.company,
					"items": [{"item_code": "ZP-KM", "qty": 42, "custom_fahrt": f.name}],
				}
			).insert()

		si = rechnung()
		self.assertEqual(flt(si.items[0].rate), 0.5)
		si.submit()
		self.assertEqual(frappe.db.get_value("Fahrt", f.name, "km_sales_invoice"), si.name)

		r = get_billable_time_logs(KUNDE_A, from_time="2031-03-14 00:00:00", to_time="2031-03-14 23:59:59")
		self.assertNotIn(f.name, {k.name for k in r["kilometers"]})
		with expect_error(self):
			rechnung()
		f.reload()
		with expect_error(self):
			f.cancel()

		si.cancel()
		self.assertFalse(frappe.db.get_value("Fahrt", f.name, "km_sales_invoice"))
		f.reload()
		f.cancel()
		self.assertEqual(frappe.db.get_value("Timesheet", f.timesheet, "docstatus"), 2)

	def test_kilometer_eines_anderen_kunden_abgelehnt(self):
		f = self.fahrt("2031-03-15 08:00:00", "2031-03-15 09:00:00")
		f.submit()
		with expect_error(self):
			frappe.get_doc(
				{
					"doctype": "Sales Invoice",
					"customer": "ZP Kunde B",
					"company": self.ctx.company,
					"items": [{"item_code": "ZP-KM", "qty": 42, "custom_fahrt": f.name}],
				}
			).insert()

	def test_zeitueberschneidung_klare_meldung(self):
		self.fahrt("2031-03-16 08:00:00", "2031-03-16 09:00:00").submit()
		zweite = self.fahrt("2031-03-16 08:30:00", "2031-03-16 09:30:00")
		with expect_error(self) as ctx:
			zweite.submit()
		# eigene Meldung (frappe.throw) statt ERPNexts roher OverlapError
		self.assertIs(type(ctx.exception), frappe.ValidationError)
