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
		self.assertEqual(d["capture_location"], 0)  # Standort ist standardmaessig aus
		for knopf in ("knopf_timer", "knopf_foto", "knopf_timer_foto", "knopf_ende_foto"):
			self.assertEqual(d[knopf], 1)  # Knoepfe sind standardmaessig an
		self.assertIn("activity_type", d)
		self.assertNotIn("api_key", d)

	def test_ocr_einstellungen_nur_fuer_system_manager(self):
		"""Der Abschnitt "Kilometerstand-Erkennung" (mit dem API-Schluessel) liegt auf
		permlevel 1; die uebrigen Rollen sehen nur Stufe 0."""
		from unittest.mock import patch

		meta = frappe.get_meta("Zeit Projekt Einstellungen")
		stufe = {f.fieldname: f.permlevel for f in meta.fields}
		for feld in ("api_type", "api_url", "model", "api_key", "max_image_px", "image_original", "context_length"):
			self.assertEqual(stufe[feld], 1, feld)
		for feld in ("activity_type", "km_item", "auto_start_timer", "capture_location", "positionsbezeichnung"):
			self.assertEqual(stufe[feld], 0, feld)

		for rolle in ("Accounts User", "Accounts Manager", "Projects User"):
			with patch("frappe.get_roles", return_value=[rolle]):
				self.assertEqual(meta.get_permlevel_access("read"), [0], rolle)
		with patch("frappe.get_roles", return_value=["System Manager"]):
			self.assertEqual(sorted(meta.get_permlevel_access("read")), [0, 1])
			self.assertEqual(sorted(meta.get_permlevel_access("write")), [0, 1])

	def _neuer_benutzer(self, mail="zp-selbst@example.com", desk=True):
		"""Desk-Benutzer ohne Mitarbeiter. Er braucht eine Rolle mit Desk-Zugriff (hier "Projects
		User", nur lesen bei Fahrt): "Employee" haelt ERPNext ohne Mitarbeiter nicht, ein Benutzer
		nur damit waere kein Desk-Benutzer. Ohne desk (Website User) gibt es keine Rolle."""
		if not frappe.db.exists("User", mail):
			user = frappe.get_doc({"doctype": "User", "email": mail, "first_name": "Selbst", "send_welcome_email": 0})
			user.insert()
			if desk:
				user.add_roles("Projects User")
		return mail

	def _selbstanlage(self, an):
		frappe.db.set_single_value("Zeit Projekt Einstellungen", "employee_self_service", 1 if an else 0)
		frappe.clear_document_cache("Zeit Projekt Einstellungen", "Zeit Projekt Einstellungen")

	def _selbstanpassung(self, an):
		frappe.db.set_single_value("Zeit Projekt Einstellungen", "employee_self_edit", 1 if an else 0)
		frappe.clear_document_cache("Zeit Projekt Einstellungen", "Zeit Projekt Einstellungen")

	def tearDown(self):
		frappe.set_user("Administrator")
		self._selbstanlage(False)
		self._selbstanpassung(False)

	def test_eigenen_mitarbeiter_anlegen_nur_employee_rolle_dazu(self):
		mail = self._neuer_benutzer()
		geschlecht = frappe.db.get_value("Gender", {}) or "Male"
		frappe.clear_cache(user=mail)
		rollen_vorher = set(frappe.get_roles(mail))
		self._selbstanlage(True)

		frappe.set_user(mail)
		self.assertEqual(technician.get_employee_status(), {"employee": None, "self_service": True, "self_edit": False})
		name = technician.create_own_employee("Selbst", geschlecht, "1991-05-17", "Techniker")

		emp = frappe.get_doc("Employee", name)
		self.assertEqual((emp.user_id, emp.status, emp.first_name), (mail, "Active", "Selbst"))
		self.assertEqual(technician.get_employee_status(), {"employee": name, "self_service": False, "self_edit": False})
		frappe.set_user("Administrator")
		frappe.clear_cache(user=mail)
		# ERPNext vergibt mit dem Mitarbeiter die Rolle Employee - sonst kommt nichts dazu
		self.assertEqual(set(frappe.get_roles(mail)) - rollen_vorher, {"Employee"})

		# nur einmal, und es gibt keinen Weg, einen anderen Benutzer anzugeben
		frappe.set_user(mail)
		with self.assertRaises(frappe.ValidationError):
			technician.create_own_employee("Nochmal", geschlecht, "1991-05-17")
		with self.assertRaises(TypeError):
			technician.create_own_employee("X", geschlecht, "1991-05-17", user_id="Administrator")

	def test_benutzerberechtigung_nur_fuer_techniker_nicht_fuer_system_manager(self):
		geschlecht = frappe.db.get_value("Gender", {}) or "Male"
		self._selbstanlage(True)
		tech = self._neuer_benutzer("zp-selbst-ber@example.com")
		admin = self._neuer_benutzer("zp-selbst-sm@example.com")
		frappe.get_doc("User", admin).add_roles("System Manager")
		frappe.clear_cache(user=admin)

		ergebnis = {}
		for mail in (tech, admin):
			frappe.set_user(mail)
			name = technician.create_own_employee("Selbst", geschlecht, "1991-05-17")
			frappe.set_user("Administrator")
			ergebnis[mail] = bool(
				frappe.db.exists("User Permission", {"user": mail, "allow": "Employee", "for_value": name})
			)
		self.assertTrue(ergebnis[tech])  # Techniker: auf den eigenen Mitarbeiter beschraenkt
		self.assertFalse(ergebnis[admin])  # System Manager: keine Beschraenkung

	def test_eigene_mitarbeiterdaten_anpassen(self):
		mail = self._neuer_benutzer("zp-selbst-edit@example.com")
		genders = frappe.get_all("Gender", pluck="name", order_by="name asc")
		self._selbstanlage(True)
		frappe.set_user(mail)
		name = technician.create_own_employee("Alt", genders[0], "1991-05-17", "Name", "2020-01-01")
		self.assertFalse(technician.get_employee_status()["self_edit"])  # Standard: aus

		with self.assertRaises(frappe.PermissionError):
			technician.update_own_employee("Neu", genders[0], "1992-06-18")
		with self.assertRaises(frappe.PermissionError):
			technician.get_employee_form_data(1)

		frappe.set_user("Administrator")
		self._selbstanpassung(True)
		frappe.clear_cache(user=mail)
		rollen_vorher = set(frappe.get_roles(mail))
		vorher = frappe.db.get_value("Employee", name, ["company", "status", "user_id", "department"], as_dict=True)

		frappe.set_user(mail)
		self.assertTrue(technician.get_employee_status()["self_edit"])
		daten = technician.get_employee_form_data(1)
		self.assertEqual((daten["first_name"], daten["last_name"], daten["date_of_birth"]), ("Alt", "Name", "1991-05-17"))

		self.assertEqual(technician.update_own_employee("Neu", genders[1], "1992-06-18", "Nachname", "2021-02-03"), name)
		frappe.set_user("Administrator")
		emp = frappe.get_doc("Employee", name)
		self.assertEqual((emp.first_name, emp.last_name, emp.gender), ("Neu", "Nachname", genders[1]))
		self.assertEqual((str(emp.date_of_birth), str(emp.date_of_joining)), ("1992-06-18", "2021-02-03"))
		# alles andere bleibt unberuehrt
		nachher = frappe.db.get_value("Employee", name, ["company", "status", "user_id", "department"], as_dict=True)
		self.assertEqual(nachher, vorher)
		frappe.clear_cache(user=mail)
		self.assertEqual(set(frappe.get_roles(mail)), rollen_vorher)

		# ungueltige Angaben werden abgelehnt, nichts wird geaendert
		frappe.set_user(mail)
		for args in (("", genders[0], "1992-06-18"), ("X", "Gibtsnicht", "1992-06-18"), ("X", genders[0], "2999-01-01")):
			with self.assertRaises(frappe.ValidationError, msg=str(args)):
				technician.update_own_employee(*args)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Employee", name, "first_name"), "Neu")

	def test_anpassen_ohne_eigenen_mitarbeiter(self):
		mail = self._neuer_benutzer("zp-selbst-leer@example.com")
		genders = frappe.get_all("Gender", pluck="name", order_by="name asc")
		self._selbstanpassung(True)
		frappe.set_user(mail)
		self.assertFalse(technician.get_employee_status()["self_edit"])
		with self.assertRaises(frappe.ValidationError):
			technician.update_own_employee("X", genders[0], "1992-06-18")

	def test_selbstanlage_nur_wenn_freigeschaltet(self):
		mail = self._neuer_benutzer("zp-selbst-aus@example.com")
		geschlecht = frappe.db.get_value("Gender", {}) or "Male"
		frappe.set_user(mail)
		self.assertEqual(technician.get_employee_status(), {"employee": None, "self_service": False, "self_edit": False})
		with self.assertRaises(frappe.PermissionError):
			technician.create_own_employee("X", geschlecht, "1991-05-17")
		with self.assertRaises(frappe.PermissionError):
			technician.get_employee_form_data()
		frappe.set_user("Administrator")
		self.assertIsNone(frappe.db.get_value("Employee", {"user_id": mail}))

	def test_selbstanlage_nicht_fuer_website_benutzer_und_gast(self):
		geschlecht = frappe.db.get_value("Gender", {}) or "Male"
		self._selbstanlage(True)
		web = self._neuer_benutzer("zp-web@example.com", desk=False)
		for user in (web, "Guest"):
			frappe.set_user(user)
			with self.assertRaises(frappe.PermissionError, msg=user):
				technician.create_own_employee("X", geschlecht, "1991-05-17")
			with self.assertRaises(frappe.PermissionError, msg=user):
				technician.get_employee_status()
			frappe.set_user("Administrator")

	def test_selbstanlage_prueft_angaben(self):
		mail = self._neuer_benutzer("zp-selbst-pruefen@example.com")
		self._selbstanlage(True)
		frappe.set_user(mail)
		geschlecht = frappe.db.get_value("Gender", {}) or "Male"
		for args in (
			("", geschlecht, "1991-05-17"),  # Vorname fehlt
			("X", "Gibtsnicht", "1991-05-17"),  # Geschlecht unbekannt
			("X", geschlecht, "2999-01-01"),  # Geburtsdatum in der Zukunft
			("X", geschlecht, frappe.utils.add_years(frappe.utils.nowdate(), -10)),  # zu jung
		):
			with self.assertRaises(frappe.ValidationError, msg=str(args)):
				technician.create_own_employee(*args)
		with self.assertRaises(frappe.ValidationError):
			technician.create_own_employee("X", geschlecht, "1991-05-17", None, "2999-01-01")  # Eintritt in der Zukunft
		self.assertIsNone(technician.get_employee_status()["employee"])  # nichts angelegt

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

	def test_ausgeschlossene_artikelgruppen(self):
		wurzel = frappe.db.get_value("Item Group", {"parent_item_group": ["in", ["", None]]}, "name")
		oben = frappe.get_doc(
			{"doctype": "Item Group", "item_group_name": "ZP Leistungen", "parent_item_group": wurzel, "is_group": 1}
		).insert()
		unten = frappe.get_doc(
			{"doctype": "Item Group", "item_group_name": "ZP Leistungen Vor Ort", "parent_item_group": oben.name}
		).insert()
		frappe.get_doc(
			{"doctype": "Item", "item_code": "ZP-GESPERRT", "item_name": "ZP-GESPERRT", "item_group": unten.name,
			 "stock_uom": "Nos", "is_stock_item": 0, "is_sales_item": 1}
		).insert()

		einstellungen = frappe.get_single("Zeit Projekt Einstellungen")
		einstellungen.append("excluded_item_groups", {"item_group": wurzel})
		with self.assertRaises(frappe.ValidationError):
			einstellungen.save()
		einstellungen = frappe.get_single("Zeit Projekt Einstellungen")
		einstellungen.set("excluded_item_groups", [{"item_group": oben.name}])
		einstellungen.save()

		frappe.set_user(TECH)
		gefunden = [a[0] for a in self.search(technician.item_query, "Item", "ZP-")]
		self.assertIn("ZP-ADAPTER", gefunden)
		self.assertNotIn("ZP-GESPERRT", gefunden)

		frappe.set_user("Administrator")
		so = make_sales_order(self.ctx.company)
		sv = frappe.get_doc(
			{
				"doctype": "Site Visit",
				"sales_order": so.name,
				"employee": self.ctx.employee,
				"activity_type": "ZP Montage",
				"date": "2031-07-01",
				"from_time": "2031-07-01 10:00:00",
				"extra_items": [{"item_code": "ZP-GESPERRT", "qty": 1}],
			}
		)
		with self.assertRaises(frappe.ValidationError):
			sv.insert()
