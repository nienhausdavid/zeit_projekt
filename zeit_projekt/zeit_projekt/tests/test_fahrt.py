import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from zeit_projekt.zeit_projekt.sales_invoice import get_billable_time_logs
from zeit_projekt.zeit_projekt.tests.utils import (
	FAHRZEIT,
	KUNDE_A,
	TECH,
	ensure_fixtures,
	ensure_vehicle,
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
		cls.vehicle = ensure_vehicle()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Zeit Projekt Einstellungen", "rounding_minutes", 0)

	def fahrt(self, start="2031-03-10 08:00:00", end="2031-03-10 09:30:00", km=(1000, 1042), bill_km=1, so=True, employee=True, vehicle=True):
		return frappe.get_doc(
			{
				"doctype": "Fahrt",
				"employee": self.ctx.employee if employee else None,
				"date": start[:10],
				"vehicle": self.vehicle if vehicle else None,
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

	def test_standorte_werden_gespeichert(self):
		import json

		karte = {
			"type": "FeatureCollection",
			"features": [
				{
					"type": "Feature",
					"properties": {"art": art, "zeit": "2031-03-10 08:00:00", "genauigkeit_m": 12},
					"geometry": {"type": "Point", "coordinates": [lng, lat]},
				}
				for art, lng, lat in (("start", 9.99, 53.55), ("ende", 10.01, 53.56))
			],
		}
		f = self.fahrt()
		f.route_map = json.dumps(karte)
		f.save()
		f.reload()
		punkte = json.loads(f.route_map)["features"]
		self.assertEqual([p["properties"]["art"] for p in punkte], ["start", "ende"])
		self.assertEqual(punkte[0]["geometry"]["coordinates"], [9.99, 53.55])

	def test_pause_ergibt_zwei_zeilen_und_netto_fahrzeit(self):
		f = self.fahrt(start="2031-03-20 08:00:00", end="2031-03-20 09:30:00", bill_km=0)
		f.append("breaks", {"from_time": "2031-03-20 08:30:00", "to_time": "2031-03-20 08:45:00", "reason": "Pause"})
		f.save()
		self.assertEqual(flt(f.duration_hours), 1.25)  # ohne die 15 Minuten Pause
		f.submit()
		zeilen = frappe.get_doc("Timesheet", f.timesheet).time_logs
		self.assertEqual(len(zeilen), 2)
		self.assertEqual([flt(z.hours) for z in zeilen], [0.5, 0.75])
		self.assertEqual(str(zeilen[0].to_time), "2031-03-20 08:30:00")
		self.assertEqual(str(zeilen[1].from_time), "2031-03-20 08:45:00")

	def test_taktung_gilt_auch_mit_pausen(self):
		frappe.db.set_single_value("Zeit Projekt Einstellungen", "rounding_minutes", 15)
		f = self.fahrt(start="2031-03-21 08:00:00", end="2031-03-21 08:50:00", bill_km=0)
		f.append("breaks", {"from_time": "2031-03-21 08:20:00", "to_time": "2031-03-21 08:30:00", "reason": "Pause"})
		f.save()  # netto 40 Minuten, 2 x 20
		f.submit()
		zeilen = frappe.get_doc("Timesheet", f.timesheet).time_logs
		self.assertEqual(len(zeilen), 2)
		self.assertAlmostEqual(flt(zeilen[0].billing_hours), 0.3333, places=3)  # tatsaechlich 20 min
		# 40 Minuten netto -> auf 45 aufgerundet; der Aufschlag haengt an der letzten Zeile
		self.assertAlmostEqual(sum(flt(z.billing_hours) for z in zeilen), 0.75, places=3)

	def test_laufende_pause_endet_mit_der_fahrt(self):
		f = self.fahrt(bill_km=0)
		f.append("breaks", {"from_time": "2031-03-10 09:00:00", "reason": "Pause"})  # noch offen
		f.save()
		self.assertEqual(str(f.breaks[0].to_time), "2031-03-10 09:30:00")
		self.assertEqual(flt(f.duration_hours), 1.0)

	def test_pause_ausserhalb_oder_ueberlappend_abgelehnt(self):
		f = self.fahrt(bill_km=0)
		f.append("breaks", {"from_time": "2031-03-10 07:00:00", "to_time": "2031-03-10 07:30:00", "reason": "Pause"})
		with self.assertRaises(frappe.ValidationError):
			f.save()
		f = self.fahrt(bill_km=0)
		f.append("breaks", {"from_time": "2031-03-10 08:10:00", "to_time": "2031-03-10 08:40:00", "reason": "Pause"})
		f.append("breaks", {"from_time": "2031-03-10 08:30:00", "to_time": "2031-03-10 08:50:00", "reason": "Pause"})
		with self.assertRaises(frappe.ValidationError):
			f.save()

	def test_ohne_mitarbeiter_speichern_und_buchen(self):
		"""Der Mitarbeiter ist freiwillig: Fahrt speichern und buchen geht ohne, das
		Zeitblatt entsteht ohne Mitarbeiter mit der Standardfirma."""
		import erpnext

		f = self.fahrt(employee=False)
		self.assertFalse(f.employee)
		f.submit()
		ts = frappe.get_doc("Timesheet", f.timesheet)
		self.assertEqual(ts.docstatus, 1)
		self.assertFalse(ts.employee)
		self.assertEqual(ts.company, erpnext.get_default_company())
		self.assertEqual(flt(ts.time_logs[0].hours), 1.5)

	def test_mitarbeiter_pflicht_per_einstellung(self):
		frappe.db.set_single_value("Zeit Projekt Einstellungen", "employee_required", 1)
		frappe.clear_document_cache("Zeit Projekt Einstellungen", "Zeit Projekt Einstellungen")
		try:
			with self.assertRaises(frappe.MandatoryError):
				self.fahrt(employee=False)
			self.assertTrue(self.fahrt(employee=True).name)  # mit Mitarbeiter geht es
		finally:
			frappe.db.set_single_value("Zeit Projekt Einstellungen", "employee_required", 0)
			frappe.clear_document_cache("Zeit Projekt Einstellungen", "Zeit Projekt Einstellungen")

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
		frappe.db.set_single_value("Zeit Projekt Einstellungen", "rounding_minutes", 15)
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

	def test_auftrag_und_projekt_werden_serverseitig_geprueft(self):
		from zeit_projekt.zeit_projekt.tests.utils import make_project

		fremd = make_sales_order(self.ctx.company, customer="ZP Kunde B")
		for feld, wert in (("sales_order", fremd.name), ("project", make_project("ZP Kunde B").name)):
			f = frappe.get_doc(
				{
					"doctype": "Fahrt",
					"customer": KUNDE_A,
					"date": "2031-03-12",
					"vehicle": self.vehicle,
					"start_time": "2031-03-12 08:00:00",
					feld: wert,
				}
			)
			with expect_error(self):
				f.insert()
		with expect_error(self):
			frappe.get_doc(
				{
					"doctype": "Fahrt",
					"customer": KUNDE_A,
					"date": "2031-03-12",
					"vehicle": self.vehicle,
					"start_time": "2031-03-12 08:00:00",
					"project": make_project(KUNDE_A, status="Cancelled").name,
				}
			).insert()

	def test_abgeschlossener_auftrag_blockiert_das_buchen(self):
		so = make_sales_order(self.ctx.company)
		f = self.fahrt("2031-03-13 08:00:00", "2031-03-13 09:00:00", bill_km=0)
		f.db_set("sales_order", so.name)
		f.reload()
		frappe.db.set_value("Sales Order", so.name, "status", "Closed")
		with expect_error(self):
			f.submit()

	def test_zeitueberschneidung_klare_meldung(self):
		self.fahrt("2031-03-16 08:00:00", "2031-03-16 09:00:00").submit()
		zweite = self.fahrt("2031-03-16 08:30:00", "2031-03-16 09:30:00")
		with expect_error(self) as ctx:
			zweite.submit()
		# eigene Meldung (frappe.throw) statt ERPNexts roher OverlapError
		self.assertIs(type(ctx.exception), frappe.ValidationError)

	# --- Fahrzeug, Plausibilitaet, Erinnerungen -----------------------------------------------

	def _einstellung(self, name, wert):
		frappe.db.set_single_value("Zeit Projekt Einstellungen", name, wert)
		frappe.clear_document_cache("Zeit Projekt Einstellungen", "Zeit Projekt Einstellungen")

	def test_standardfahrzeug_aus_letzter_fahrt(self):
		self.fahrt("2031-04-01 08:00:00", "2031-04-01 09:00:00")  # Fahrzeug gesetzt
		neu = self.fahrt("2031-04-02 08:00:00", "2031-04-02 09:00:00", vehicle=False)
		self.assertEqual(neu.vehicle, self.vehicle)

	def test_fahrzeug_pflicht_beim_buchen(self):
		self.fahrt("2031-04-03 08:00:00", "2031-04-03 09:00:00")
		f = self.fahrt("2031-04-04 08:00:00", "2031-04-04 09:00:00", vehicle=False)
		frappe.db.set_value("Fahrt", f.name, "vehicle", None)
		f.reload()
		self._einstellung("vehicle_required", 1)
		try:
			with expect_error(self):
				f.submit()
			f.reload()
			self._einstellung("vehicle_required", 0)
			f.submit()  # ohne die Einstellung ist das Fahrzeug freiwillig
		finally:
			self._einstellung("vehicle_required", 1)

	def test_letzter_stand_des_fahrzeugs(self):
		from zeit_projekt.fahrtenbuch.fahrtenbuch import letzter_stand

		kennzeichen = ensure_vehicle("ZP-TEST-2", 7000)
		self.assertEqual(letzter_stand(kennzeichen), {"stand": 7000, "fahrt": None})  # aus den Fahrzeugdaten
		self.assertIsNone(letzter_stand(None))
		alt = frappe.get_doc(
			{"doctype": "Fahrt", "date": "2031-05-01", "vehicle": kennzeichen, "start_time": "2031-05-01 08:00:00",
			 "end_time": "2031-05-01 09:00:00", "start_odometer": 7000, "end_odometer": 7050}
		).insert()
		neu = frappe.get_doc(
			{"doctype": "Fahrt", "date": "2031-05-02", "vehicle": kennzeichen, "start_time": "2031-05-02 08:00:00",
			 "end_time": "2031-05-02 09:00:00", "start_odometer": 7050, "end_odometer": 7120}
		).insert()
		self.assertEqual(letzter_stand(kennzeichen), {"stand": 7120, "fahrt": neu.name})
		self.assertEqual(letzter_stand(kennzeichen, ausser=neu.name), {"stand": 7050, "fahrt": alt.name})

	def setUp(self):
		from frappe.utils import add_to_date, now_datetime

		self._start = add_to_date(now_datetime(), seconds=-1)

	def _entwurf(self, start, end=None, end_km=0):
		return frappe.get_doc(
			{"doctype": "Fahrt", "date": start[:10], "start_time": start, "end_time": end, "start_odometer": 1000,
			 "end_odometer": end_km}
		).insert()

	def _meldungen(self, fahrt):
		# Namen werden nach einem Rollback wiederverwendet, Meldungen frueherer Laeufe koennen
		# uebrig sein: nur die seit Testbeginn zaehlen
		return frappe.get_all("Notification Log", filters={"document_type": "Fahrt", "document_name": fahrt.name, "creation": [">=", self._start]}, pluck="subject")

	def test_erinnerung_laufender_timer(self):
		from frappe.utils import add_to_date, now_datetime

		from zeit_projekt.fahrtenbuch.erinnerungen import pruefe_fahrten

		lang = self._entwurf(str(add_to_date(now_datetime(), hours=-12)))
		kurz = self._entwurf(str(add_to_date(now_datetime(), hours=-1)))
		pruefe_fahrten(nur=[lang.name, kurz.name])
		self.assertEqual(len(self._meldungen(lang)), 1)
		self.assertEqual(self._meldungen(kurz), [])
		pruefe_fahrten(nur=[lang.name, kurz.name])  # kein zweites Mal
		self.assertEqual(len(self._meldungen(lang)), 1)

	def test_erinnerung_endstand_fehlt(self):
		from frappe.utils import add_to_date, now_datetime

		from zeit_projekt.fahrtenbuch.erinnerungen import pruefe_fahrten

		start = add_to_date(now_datetime(), hours=-6)
		offen = self._entwurf(str(start), str(add_to_date(now_datetime(), hours=-3)))
		fertig = self._entwurf(str(start), str(add_to_date(now_datetime(), hours=-3)), end_km=1050)
		pruefe_fahrten(nur=[offen.name, fertig.name])
		self.assertEqual(len(self._meldungen(offen)), 1)
		self.assertEqual(self._meldungen(fertig), [])

	def test_erinnerungen_abschaltbar(self):
		from frappe.utils import add_to_date, now_datetime

		from zeit_projekt.fahrtenbuch.erinnerungen import pruefe_fahrten

		lang = self._entwurf(str(add_to_date(now_datetime(), hours=-12)))
		self._einstellung("reminders_enabled", 0)
		try:
			pruefe_fahrten(nur=[lang.name])
			self.assertEqual(self._meldungen(lang), [])
		finally:
			self._einstellung("reminders_enabled", 1)
