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

	def test_uebersetzungen(self):
		# Quelle ist Deutsch, en.csv uebersetzt - ERPNext-Begriffe bleiben unberuehrt
		self.assertEqual(frappe._("Tätigkeit", lang="en"), "Work Performed")
		self.assertNotEqual(frappe._("Duration", lang="de"), "Zeitraum")
		self.assertEqual(frappe._("Site Visit", lang="de"), "Kundeneinsatz")

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

	def test_desk(self):
		from frappe.apps import get_apps

		self.assertEqual(frappe.db.get_value("Desktop Icon", "Zeit & Projekt", "icon_type"), "App")
		kinder = frappe.get_all("Desktop Icon", filters={"parent_icon": "Zeit & Projekt"}, pluck="link_to")
		self.assertEqual(sorted(kinder), ["Fahrtenbuch", "Site Visits"])
		for sidebar in kinder:
			self.assertTrue(frappe.db.exists("Workspace Sidebar", sidebar))
		kacheln = [a for a in get_apps() if a["name"] == "zeit_projekt"]
		self.assertEqual(len(kacheln), 1)
		self.assertTrue(kacheln[0]["route"].startswith("/desk/"))
