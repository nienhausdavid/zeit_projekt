import frappe
from frappe.tests import IntegrationTestCase


class TestApp(IntegrationTestCase):
	"""Installation, Desk-Einbindung, Uebersetzungen, PDF-Einstellung."""

	def test_module_gehoeren_zur_app(self):
		for module in ("Zeit Projekt", "Fahrtenbuch", "Site Visit"):
			self.assertEqual(frappe.db.get_value("Module Def", module, "app_name"), "zeit_projekt")

	def test_parallele_einzel_apps_blockiert(self):
		from zeit_projekt.install import before_app_install

		for app in ("fahrtenbuch", "site_visit"):
			with self.assertRaises(frappe.ValidationError):
				before_app_install(app)
		before_app_install("hrms")  # andere Apps bleiben erlaubt

	def test_projekt_verknuepfungen(self):
		items = [
			item
			for group in frappe.get_meta("Project").get_dashboard_data().get("transactions", [])
			for item in group.get("items", [])
		]
		self.assertIn("Fahrt", items)
		self.assertIn("Site Visit", items)

	def test_custom_fields(self):
		for name in (
			"Activity Type-custom_dienstleistungsartikel",
			"Sales Order-custom_projekt_erstellen",
			"Sales Invoice Item-custom_fahrt",
		):
			self.assertTrue(frappe.db.exists("Custom Field", name), name)

	def test_uebersetzung_nur_im_kontext(self):
		self.assertNotEqual(frappe._("Duration", lang="de"), "Zeitraum")
		self.assertEqual(frappe._("Duration", lang="de", context="Site Visit"), "Zeitraum")

	def test_chrome_pdf_standardmaessig_aus(self):
		from zeit_projekt.zeit_projekt.pdf import chrome_enabled, force_chrome_pdf

		self.assertFalse(chrome_enabled())
		frappe.local.request = frappe._dict(path="/api/method/frappe.utils.print_format.download_pdf")
		frappe.local.form_dict = frappe._dict()
		force_chrome_pdf()
		self.assertIsNone(frappe.local.form_dict.get("pdf_generator"))

		frappe.db.set_single_value("Zeit Projekt Einstellungen", "force_chrome_pdf", 1)
		frappe.db.value_cache.clear()
		force_chrome_pdf()
		self.assertEqual(frappe.local.form_dict.get("pdf_generator"), "chrome")
