import frappe
from frappe.tests import IntegrationTestCase

from zeit_projekt.fahrtenbuch.fahrtenbuch import get_available_models, get_fahrt_defaults
from zeit_projekt.zeit_projekt import technician
from zeit_projekt.zeit_projekt.tests.utils import (
	BUCHHALTUNG,
	KUNDE_A,
	KUNDE_B,
	TECH,
	ensure_fixtures,
	make_sales_order,
)


class TestTechnikerRechte(IntegrationTestCase):
	"""Techniker mit nur der Rolle "Employee" duerfen Kunde/Auftrag/Artikel
	nicht lesen - die eingeschraenkten Suchen muessen trotzdem funktionieren,
	aber nur fuer sie."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = ensure_fixtures()
		cls.so_b = make_sales_order(cls.ctx.company, KUNDE_B)

	def tearDown(self):
		frappe.set_user("Administrator")

	def search(self, fn, doctype, txt="", filters=None):
		return frappe.call(fn, doctype, txt, "name", 0, 50, filters or {})

	def test_suchen_fuer_techniker(self):
		frappe.set_user(TECH)
		self.assertIn(KUNDE_A, [k[0] for k in self.search(technician.customer_query, "Customer", "ZP Kunde")])
		auftraege = self.search(technician.sales_order_query, "Sales Order", filters={"customer": KUNDE_B})
		self.assertIn(self.so_b.name, [a[0] for a in auftraege])
		self.assertTrue(all(frappe.db.get_value("Sales Order", a[0], "customer") == KUNDE_B for a in auftraege))
		self.assertIn("ZP-KM", [a[0] for a in self.search(technician.item_query, "Item", "ZP-")])
		self.assertEqual(technician.get_link_details("Sales Order", self.so_b.name).get("customer"), KUNDE_B)

	def test_link_validierung_wie_im_browser(self):
		from frappe.client import validate_link_and_fetch

		frappe.set_user(TECH)
		frappe.local.request = frappe._dict(method="POST")
		r = validate_link_and_fetch("Customer", KUNDE_A, query="zeit_projekt.zeit_projekt.technician.customer_query")
		self.assertEqual(r.get("name"), KUNDE_A)

	def test_gesperrt_fuer_andere(self):
		frappe.set_user(TECH)
		with self.assertRaises(frappe.PermissionError):
			technician.get_link_details("User", "Administrator")
		with self.assertRaises(frappe.PermissionError):
			get_available_models("http://127.0.0.1:1")

		frappe.set_user(BUCHHALTUNG)
		with self.assertRaises(frappe.PermissionError):
			self.search(technician.customer_query, "Customer")

	def test_fahrt_vorbelegung(self):
		frappe.set_user(TECH)
		d = get_fahrt_defaults()
		self.assertEqual((d["auto_start_timer"], d["auto_open_camera"]), (1, 1))
		self.assertIn("activity_type", d)
		self.assertNotIn("api_key", d)

	def test_offene_auftraege_zum_projekt(self):
		projekt = frappe.get_doc(
			{"doctype": "Project", "project_name": f"ZP Projekt {frappe.generate_hash(length=6)}", "customer": KUNDE_A}
		).insert()
		namen = []
		for kommission in ("K-1", "K-2"):
			so = make_sales_order(self.ctx.company, submit=False)
			so.update({"project": projekt.name, "po_no": f"{kommission}-{frappe.generate_hash(length=6)}"})
			so.submit()
			namen.append(so.name)

		frappe.set_user(TECH)
		auftraege = technician.get_open_sales_orders(projekt.name, KUNDE_A)
		self.assertEqual(sorted(a.name for a in auftraege), sorted(namen))
		self.assertTrue(all(a.po_no and a.transaction_date for a in auftraege))
