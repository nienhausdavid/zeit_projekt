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

	def test_symbole_in_gespeichertes_desktop_layout(self):
		import json

		from zeit_projekt.install import _in_desktop_layouts_eintragen
		from zeit_projekt.zeit_projekt.tests.utils import TECH, ensure_fixtures

		ensure_fixtures()
		fremd = {"name": "Fremd", "label": "Fremd", "icon_type": "Link", "parent_icon": None}
		# Layout eines Benutzers wie vom Desk gespeichert (flache Liste von Objekten) - plus
		# ein Textwert, wie ihn eine fruehere Fassung der Funktion faelschlich schrieb.
		frappe.get_doc(
			{"doctype": "Desktop Layout", "user": TECH, "layout": json.dumps([fremd, "Zeit & Projekt"])}
		).insert(ignore_permissions=True)

		self.assertTrue(_in_desktop_layouts_eintragen())
		layout = json.loads(frappe.db.get_value("Desktop Layout", TECH, "layout"))
		self.assertTrue(all(isinstance(x, dict) for x in layout))
		self.assertEqual(
			[x["name"] for x in layout], ["Fremd", "Zeit & Projekt", "Fahrtenbuch", "Site Visits"]
		)
		# Der Rest des Layouts bleibt unveraendert, Wiederholung aendert nichts
		self.assertEqual(layout[0], fremd)
		self.assertFalse(_in_desktop_layouts_eintragen())

	def test_desk_symbole_haben_bilder(self):
		"""Untergeordnete Desk-Symbole brauchen je Variante ein SVG unter
		public/icons/desktop_icons/<variante>/<label>.svg, sonst zeigt der Desk nur
		den Anfangsbuchstaben. Das App-Symbol selbst nutzt logo_url."""
		import glob
		import json
		import os

		app = frappe.get_app_path("zeit_projekt")
		unterpunkte = 0
		for datei in glob.glob(os.path.join(app, "desktop_icon", "*.json")):
			with open(datei) as f:
				icon = json.load(f)
			if icon.get("icon_type") != "Link":
				self.assertTrue(icon.get("logo_url"), icon["label"])
				continue
			unterpunkte += 1
			for variante in ("solid", "subtle"):
				svg = os.path.join(app, "public", "icons", "desktop_icons", variante, f"{frappe.scrub(icon['label'])}.svg")
				self.assertTrue(os.path.isfile(svg), svg)
		self.assertGreaterEqual(unterpunkte, 2)

	def test_pause_wird_nicht_zu_anhalten(self):
		# ERPNext uebersetzt "Pause" im Deutschen mit "Anhalten" (Arbeitsplatz); als Grund
		# einer Pause im Fahrtenbuch soll es "Pause" bleiben.
		self.assertEqual(frappe._("Pause", lang="de"), "Pause")

	def test_fahrzeuge_in_der_seitenleiste(self):
		self.assertTrue(frappe.db.exists("Sidebar Item", {"parent": "Fahrtenbuch", "link_to": "Vehicle"}))

	def test_desk(self):
		from frappe.apps import get_apps

		self.assertEqual(frappe.db.get_value("Desktop Icon", "Zeit & Projekt", "icon_type"), "App")
		kinder = frappe.get_all("Desktop Icon", filters={"parent_icon": "Zeit & Projekt"}, pluck="link_to")
		self.assertEqual(sorted(kinder), ["Fahrtenbuch", "Site Visits"])
		# Frappe >= 16.51 liest "Sidebar"; "Workspace Sidebar" ist dort wirkungslos.
		doctype = "Sidebar" if frappe.db.table_exists("Sidebar") else "Workspace Sidebar"
		for sidebar in kinder:
			self.assertTrue(frappe.db.exists(doctype, sidebar))
		if doctype == "Sidebar":
			self.assertEqual(frappe.db.get_value("Sidebar", "Fahrtenbuch", "module"), "Fahrtenbuch")
			self.assertEqual(frappe.db.get_value("Sidebar", "Site Visits", "module"), "Site Visit")
		kacheln = [a for a in get_apps() if a["name"] == "zeit_projekt"]
		self.assertEqual(len(kacheln), 1)
		self.assertTrue(kacheln[0]["route"].startswith("/desk/"))

	def test_desk_nach_update_von_alter_version(self):
		"""Eine fruehere Version liess Frappe "Zeit & Projekt" und "Site Visits"
		selbst erzeugen - juenger als die Dateien, daher vom migrate uebergangen.
		after_migrate muss sie trotzdem auf den Stand der App bringen."""
		from zeit_projekt.install import _desk_abgleichen

		frappe.db.set_value(
			"Desktop Icon", "Zeit & Projekt", {"link": "/app/fahrt", "standard": 0}, update_modified=True
		)
		frappe.db.set_value("Desktop Icon", "Site Visits", {"app": None, "standard": 0}, update_modified=True)
		frappe.delete_doc("Desktop Icon", "Fahrtenbuch", force=True, for_reload=True)

		_desk_abgleichen()

		symbole = {
			d.name: d
			for d in frappe.get_all(
				"Desktop Icon",
				filters={"name": ["in", ["Zeit & Projekt", "Fahrtenbuch", "Site Visits"]]},
				fields=["name", "app", "standard", "link", "parent_icon"],
			)
		}
		self.assertEqual(sorted(symbole), ["Fahrtenbuch", "Site Visits", "Zeit & Projekt"])
		self.assertEqual(symbole["Zeit & Projekt"].link, "/desk/fahrt?sidebar=Fahrtenbuch")
		for name in ("Fahrtenbuch", "Site Visits"):
			self.assertEqual(symbole[name].parent_icon, "Zeit & Projekt")
		for d in symbole.values():
			self.assertEqual((d.app, d.standard), ("zeit_projekt", 1))

	def test_projekt_aus_auftrag_ohne_eu_einvoice(self):
		"""buyer_reference gibt es nur mit eu_einvoice - ohne das Feld darf die
		Projektanlage nicht scheitern."""
		from zeit_projekt.zeit_projekt.tests.utils import KUNDE_A, ensure_fixtures, make_sales_order

		ctx = ensure_fixtures()
		so = make_sales_order(ctx.company, submit=False)
		so.custom_projekt_erstellen = 1
		so.submit()
		self.assertTrue(so.project)
		self.assertEqual(frappe.db.get_value("Project", so.project, "customer"), KUNDE_A)

	def test_aktivitaetsarten_in_den_einstellungen(self):
		"""Die Tabelle zeigt die Aktivitaetsarten und schreibt beim Speichern
		in sie zurueck - gespeichert wird sie selbst nicht."""
		from zeit_projekt.zeit_projekt.tests.utils import MONTAGE, ensure_fixtures

		ensure_fixtures()
		neu = frappe.get_doc({"doctype": "Activity Type", "activity_type": "ZP Wartung"}).insert()

		einstellungen = frappe.get_single("Zeit Projekt Einstellungen")
		einstellungen.run_method("onload")
		zeilen = {z.activity_type: z for z in einstellungen.aktivitaetsarten}
		self.assertEqual(zeilen[MONTAGE].dienstleistungsartikel, "ZP-MONTAGE")
		self.assertEqual(frappe.utils.flt(zeilen[MONTAGE].artikelpreis), 95)
		self.assertFalse(zeilen[neu.name].dienstleistungsartikel)

		zeilen[neu.name].update({"dienstleistungsartikel": "ZP-MONTAGE", "rechnungstext": "Wartung", "billing_rate": 70})
		einstellungen.save()
		self.assertEqual(
			frappe.db.get_value(
				"Activity Type", neu.name, ["custom_dienstleistungsartikel", "custom_rechnungstext", "billing_rate"]
			),
			("ZP-MONTAGE", "Wartung", 70),
		)
		self.assertFalse(frappe.get_all("Zeit Projekt Aktivitaetsart", limit=1))

		# Speichern ohne geoeffnetes Formular aendert keine Aktivitaetsart
		frappe.db.set_value("Activity Type", neu.name, "billing_rate", 75)
		frappe.get_single("Zeit Projekt Einstellungen").save()
		self.assertEqual(frappe.db.get_value("Activity Type", neu.name, "billing_rate"), 75)

		einstellungen = frappe.get_single("Zeit Projekt Einstellungen")
		einstellungen.run_method("onload")
		einstellungen.aktivitaetsarten[0].dienstleistungsartikel = "ZP-GIBTSNICHT"
		with self.assertRaises(frappe.ValidationError):
			einstellungen.save()
