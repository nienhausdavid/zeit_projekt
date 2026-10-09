import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from zeit_projekt.site_visit.site_visit import create_sales_order
from zeit_projekt.zeit_projekt.tests.utils import (
	BUCHHALTUNG,
	KUNDE_A,
	KUNDE_B,
	MONTAGE,
	TECH,
	ensure_fixtures,
	expect_error,
	make_sales_order,
	sales_order_rows,
)


class TestSiteVisit(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = ensure_fixtures()

	def tearDown(self):
		frappe.set_user("Administrator")

	def site_visit(self, tag, sales_order=None, items=None, customer=KUNDE_A):
		return frappe.get_doc(
			{
				"doctype": "Site Visit",
				"customer": customer,
				"employee": self.ctx.employee,
				"activity_type": MONTAGE,
				"date": f"2031-04-{tag:02d}",
				"from_time": f"2031-04-{tag:02d} 10:00:00",
				"to_time": f"2031-04-{tag:02d} 12:00:00",
				"sales_order": sales_order,
				"description": "Montage",
				"extra_items": items or [],
			}
		).insert()

	def test_techniker_bucht_mit_zusatzartikel(self):
		so = make_sales_order(self.ctx.company)
		frappe.set_user(TECH)
		sv = self.site_visit(1, so.name, [{"item_code": "ZP-ADAPTER", "qty": 2, "rate": 999}])

		self.assertEqual(sv.customer_name, KUNDE_A)
		row = sv.extra_items[0]
		self.assertEqual(flt(row.rate), 15)  # aus der Preisliste, nicht die Eingabe
		self.assertEqual(flt(row.amount), 30)
		self.assertEqual((row.item_name, row.uom), ("ZP-ADAPTER", "Nos"))

		sv.submit()
		ts = frappe.get_doc("Timesheet", sv.timesheet)
		self.assertEqual((ts.docstatus, ts.customer), (1, KUNDE_A))
		self.assertEqual(flt(ts.time_logs[0].billing_rate), 90)

		zeile = next(z for z in sales_order_rows(so.name) if z.name == sv.extra_items[0].sales_order_item)
		self.assertEqual((flt(zeile.rate), flt(zeile.qty)), (15, 2))
		self.assertIn(sv.name, zeile.description)
		# Rueckverfolgbarkeit: Herkunft an der Position, Techniker im Verlauf
		self.assertEqual(frappe.db.get_value("Sales Order Item", zeile.name, "custom_site_visit"), sv.name)
		kommentar = frappe.get_all(
			"Comment",
			filters={"reference_doctype": "Sales Order", "reference_name": so.name, "comment_type": "Comment"},
			pluck="content",
		)
		self.assertTrue(any(sv.name in k and "zp-tech" in k for k in kommentar), kommentar)

	def test_auftrag_eines_anderen_kunden_abgelehnt(self):
		fremd = make_sales_order(self.ctx.company, KUNDE_B)
		with expect_error(self):
			self.site_visit(2, fremd.name)

	def test_auftrag_ist_pflicht_und_bestimmt_den_kunden(self):
		with expect_error(self, frappe.MandatoryError):
			self.site_visit(7)
		so = make_sales_order(self.ctx.company)
		sv = self.site_visit(8, so.name, customer=None)
		self.assertEqual((sv.customer, sv.customer_name), (KUNDE_A, KUNDE_A))

	def test_zusatzartikel_ohne_preis_blockiert_buchen(self):
		so = make_sales_order(self.ctx.company)
		sv = self.site_visit(3, so.name, [{"item_code": "ZP-OHNEPREIS", "qty": 1}])
		with expect_error(self):
			sv.submit()

	def test_zusatzartikel_ohne_preis_erlaubt_per_einstellung(self):
		frappe.db.set_single_value("Zeit Projekt Einstellungen", "allow_zero_price", 1)
		try:
			so = make_sales_order(self.ctx.company)
			sv = self.site_visit(6, so.name, [{"item_code": "ZP-OHNEPREIS", "qty": 1}])
			sv.submit()
			zeile = frappe.db.get_value(
				"Sales Order Item", sv.extra_items[0].sales_order_item, ["item_code", "rate"], as_dict=True
			)
			self.assertEqual((zeile.item_code, flt(zeile.rate)), ("ZP-OHNEPREIS", 0))
		finally:
			frappe.db.set_single_value("Zeit Projekt Einstellungen", "allow_zero_price", 0)

	def test_neuer_auftrag_direkt_mit_kommissionsnummer(self):
		frappe.set_user(TECH)
		kommission = frappe.generate_hash(length=10)
		name = create_sales_order(KUNDE_A, MONTAGE, po_no=kommission, date="2031-04-04")

		so = frappe.get_doc("Sales Order", name)
		self.assertEqual((so.docstatus, so.customer, so.po_no), (0, KUNDE_A, kommission))
		self.assertTrue(so.delivery_date)
		# Platzhalter: Dienstleistungsartikel der Aktivitaetsart mit Preis 0 -
		# die Zeit selbst wird ueber das Zeitblatt abgerechnet
		self.assertEqual([(i.item_code, flt(i.rate)) for i in so.items], [("ZP-MONTAGE", 0)])

		sv = self.site_visit(4, name, [{"item_code": "ZP-ADAPTER", "qty": 3}])
		sv.submit()
		zeilen = sales_order_rows(name)
		self.assertEqual([(z.item_code, flt(z.rate), flt(z.qty)) for z in zeilen][-1], ("ZP-ADAPTER", 15, 3))
		self.assertEqual(frappe.db.get_value("Sales Order", name, "docstatus"), 0)

		frappe.set_user("Administrator")
		sv.cancel()
		self.assertEqual([z.item_code for z in sales_order_rows(name)], ["ZP-MONTAGE"])

	def test_neuer_auftrag_braucht_dienstleistungsartikel(self):
		frappe.set_user(TECH)
		frappe.db.set_value("Activity Type", MONTAGE, "custom_dienstleistungsartikel", None)
		try:
			with expect_error(self):
				create_sales_order(KUNDE_A, MONTAGE)
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_value("Activity Type", MONTAGE, "custom_dienstleistungsartikel", "ZP-MONTAGE")

	def test_neuer_auftrag_nur_mit_einsatzrechten(self):
		frappe.set_user(BUCHHALTUNG)
		with expect_error(self, frappe.PermissionError):
			create_sales_order(KUNDE_A, MONTAGE)

	def test_stornieren_und_berichtigen(self):
		so = make_sales_order(self.ctx.company)
		sv = self.site_visit(5, so.name, [{"item_code": "ZP-ADAPTER", "qty": 2}])
		sv.submit()
		so_item = sv.extra_items[0].sales_order_item

		sv.cancel()
		self.assertNotIn(so_item, {z.name for z in sales_order_rows(so.name)})
		self.assertEqual(frappe.db.get_value("Timesheet", sv.timesheet, "docstatus"), 2)
		self.assertEqual(frappe.db.get_value("Site Visit Item", sv.extra_items[0].name, "added_to_order"), 0)

		# Berichtigen wie im Browser: no_copy-Felder werden nicht kopiert
		neu = frappe.copy_doc(frappe.get_doc("Site Visit", sv.name), ignore_no_copy=False)
		neu.amended_from = sv.name
		neu.docstatus = 0
		neu.insert()
		neu.submit()
		self.assertEqual(len([z for z in sales_order_rows(so.name) if neu.name in (z.description or "")]), 1)

	def test_pausen_werden_herausgerechnet(self):
		so = make_sales_order(self.ctx.company)
		so_b = make_sales_order(self.ctx.company, KUNDE_B)
		sv = frappe.get_doc(
			{
				"doctype": "Site Visit",
				"sales_order": so.name,
				"employee": self.ctx.employee,
				"activity_type": MONTAGE,
				"date": "2031-05-02",
				"from_time": "2031-05-02 10:00:00",
				"to_time": "2031-05-02 14:00:00",
				"breaks": [
					{"from_time": "2031-05-02 11:00:00", "to_time": "2031-05-02 11:30:00", "reason": "Pause"},
					{"from_time": "2031-05-02 12:00:00", "to_time": "2031-05-02 12:45:00", "reason": "Notfall bei anderem Kunden"},
				],
			}
		).insert()
		self.assertEqual(flt(sv.working_hours, 2), 2.75)

		# Notfall beim anderen Kunden waehrend der Pause - darf nicht kollidieren
		notfall = self.site_visit(2, so_b.name, customer=KUNDE_B)
		notfall.update({"date": "2031-05-02", "from_time": "2031-05-02 12:05:00", "to_time": "2031-05-02 12:40:00"})
		notfall.save()
		notfall.submit()

		sv.submit()
		ts = frappe.get_doc("Timesheet", sv.timesheet)
		self.assertEqual(
			[(str(log.from_time), str(log.to_time)) for log in ts.time_logs],
			[
				("2031-05-02 10:00:00", "2031-05-02 11:00:00"),
				("2031-05-02 11:30:00", "2031-05-02 12:00:00"),
				("2031-05-02 12:45:00", "2031-05-02 14:00:00"),
			],
		)
		self.assertEqual(flt(ts.total_billable_hours, 2), 2.75)

	def test_laufende_pause_endet_mit_dem_einsatz(self):
		so = make_sales_order(self.ctx.company)
		sv = self.site_visit(9, so.name)
		sv.to_time = None
		sv.append("breaks", {"from_time": "2031-04-09 11:00:00", "reason": "Pause"})
		sv.save()
		self.assertFalse(sv.breaks[0].to_time)
		self.assertEqual(flt(sv.working_hours), 0)

		# zweite Pause, solange die erste noch laeuft
		sv.append("breaks", {"from_time": "2031-04-09 11:10:00", "reason": "Pause"})
		with expect_error(self):
			sv.save()
		sv.reload()

		sv.to_time = "2031-04-09 11:40:00"
		sv.save()
		self.assertEqual(str(sv.breaks[0].to_time), "2031-04-09 11:40:00")
		self.assertEqual(flt(sv.working_hours, 2), 1.0)

	def test_pause_ausserhalb_des_einsatzes_abgelehnt(self):
		so = make_sales_order(self.ctx.company)
		sv = self.site_visit(10, so.name)
		sv.append("breaks", {"from_time": "2031-04-10 09:00:00", "to_time": "2031-04-10 10:30:00"})
		with expect_error(self):
			sv.save()
