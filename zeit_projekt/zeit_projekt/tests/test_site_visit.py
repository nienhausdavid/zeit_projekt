import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from zeit_projekt.site_visit.site_visit import create_sales_order
from zeit_projekt.zeit_projekt.tests.utils import (
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
		sv = self.site_visit(2, fremd.name)
		with expect_error(self):
			sv.submit()

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

	def test_neuer_auftrag_aus_site_visit(self):
		frappe.set_user(TECH)
		sv = self.site_visit(4, items=[{"item_code": "ZP-ADAPTER", "qty": 1}, {"item_code": "ZP-ADAPTER", "qty": 3}])
		name = create_sales_order(sv.name, po_no=frappe.generate_hash(length=10))

		so = frappe.get_doc("Sales Order", name)
		self.assertEqual(so.docstatus, 0)
		self.assertTrue(so.delivery_date)
		self.assertEqual([flt(i.rate) for i in so.items], [15, 15])
		self.assertEqual({i.custom_site_visit for i in so.items}, {sv.name})
		sv.reload()
		self.assertEqual(sv.sales_order, name)
		self.assertTrue(all(r.added_to_order for r in sv.extra_items))

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
