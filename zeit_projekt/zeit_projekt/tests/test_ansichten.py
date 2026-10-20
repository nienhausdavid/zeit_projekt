import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from zeit_projekt.zeit_projekt.report.abrechnungsansicht.abrechnungsansicht import execute as abrechnung
from zeit_projekt.zeit_projekt.report.auftrags__und_projektansicht.auftrags__und_projektansicht import (
	execute as auftraege_und_projekte,
)
from zeit_projekt.zeit_projekt.sales_invoice import get_billable_time_logs
from zeit_projekt.zeit_projekt.tests.utils import (
	BUCHHALTUNG,
	FAHRZEIT,
	KUNDE_A,
	MONTAGE,
	TECH,
	ensure_fixtures,
	ensure_vehicle,
	make_project,
	make_sales_order,
)


class TestAnsichten(IntegrationTestCase):
	"""Abrechnungsansicht und Auftrags- und Projektansicht."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = ensure_fixtures()
		cls.vehicle = ensure_vehicle()

	def einsatz(self, tag, sales_order=None, project=None):
		sv = frappe.get_doc(
			{
				"doctype": "Site Visit",
				"sales_order": sales_order,
				"project": project,
				"employee": self.ctx.employee,
				"activity_type": MONTAGE,
				"date": f"2033-01-{tag:02d}",
				"from_time": f"2033-01-{tag:02d} 10:00:00",
				"to_time": f"2033-01-{tag:02d} 12:00:00",
			}
		).insert()
		sv.submit()
		return sv

	def auftrag_mit_projekt(self, projekt):
		so = make_sales_order(self.ctx.company, submit=False)
		so.project = projekt.name
		so.submit()
		return so

	def rechnung(self, tag):
		"""Rechnung wie aus dem Zeitimport fuer die Zeiten eines Tages (Entwurf)."""
		zeilen = get_billable_time_logs(
			KUNDE_A, from_time=f"2033-01-{tag:02d} 00:00:00", to_time=f"2033-01-{tag:02d} 23:59:59"
		)["rows"]
		si = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"customer": KUNDE_A,
				"company": self.ctx.company,
				"items": [
					{
						"item_code": "ZP-MONTAGE",
						"qty": flt(z.billing_hours),
						"description": f"{z.from_time}-{z.to_time}",
					}
					for z in zeilen
				],
				"timesheets": [
					{"time_sheet": z.time_sheet, "timesheet_detail": z.name, "billing_hours": z.billing_hours}
					for z in zeilen
				],
			}
		)
		si.set_missing_values()
		si.insert()
		return si

	def test_abrechnungsansicht(self):
		projekt = make_project()
		so = self.auftrag_mit_projekt(projekt)
		self.einsatz(1, sales_order=so.name)  # Auftrag + Projekt (aus dem Auftrag)
		self.einsatz(2, project=projekt.name)  # nur Projekt
		fahrt = frappe.get_doc(
			{
				"doctype": "Fahrt",
				"employee": self.ctx.employee,
				"date": "2033-01-03",
				"vehicle": self.vehicle,
				"project": projekt.name,
				"start_time": "2033-01-03 08:00:00",
				"end_time": "2033-01-03 09:00:00",
				"start_odometer": 2000,
				"end_odometer": 2030,
				"activity_type": FAHRZEIT,
				"bill_km": 1,
				"km_item": "ZP-KM",
			}
		).insert()
		fahrt.submit()

		spalten, daten = abrechnung({"project": projekt.name})
		self.assertIn("stunden", [s["fieldname"] for s in spalten])
		zeilen = {(z.sales_order, z.project): z for z in daten}
		self.assertEqual(set(zeilen), {(so.name, projekt.name), (None, projekt.name)})
		mit_auftrag, nur_projekt = zeilen[(so.name, projekt.name)], zeilen[(None, projekt.name)]
		for z in (mit_auftrag, nur_projekt):
			self.assertEqual((z.kunde, z.kunde_name), (KUNDE_A, KUNDE_A))
		self.assertEqual((mit_auftrag.anzahl, flt(mit_auftrag.stunden), flt(mit_auftrag.betrag)), (1, 2, 180))
		self.assertEqual(mit_auftrag.po_no, so.po_no)
		# Fahrzeit (1 Std.) und 30 km stehen bei der Gruppe ohne Auftrag
		self.assertEqual((nur_projekt.anzahl, flt(nur_projekt.stunden), flt(nur_projekt.km)), (2, 3, 30))

		# Filter nach Auftrag, Kunde und Datum
		self.assertEqual([z.sales_order for z in abrechnung({"sales_order": so.name})[1]], [so.name])
		self.assertEqual(abrechnung({"project": projekt.name, "from_date": "2033-02-01"})[1], [])

		# In einem Rechnungsentwurf: weiter offen, aber gekennzeichnet
		self.rechnung(2)
		nur_projekt = {(z.sales_order, z.project): z for z in abrechnung({"project": projekt.name})[1]}[(None, projekt.name)]
		self.assertEqual(flt(nur_projekt.entwurf_stunden), 2)
		self.assertEqual(flt(nur_projekt.stunden), 3)

	def test_auftrags_und_projektansicht_als_baum(self):
		projekt = make_project()
		so_projekt = self.auftrag_mit_projekt(projekt)
		so_frei = make_sales_order(self.ctx.company)
		self.einsatz(4, sales_order=so_projekt.name)
		self.einsatz(5, project=projekt.name)
		self.einsatz(6, sales_order=so_frei.name)

		spalten, daten = auftraege_und_projekte({"customer": KUNDE_A})
		self.assertEqual(spalten[0]["fieldtype"], "Dynamic Link")
		namen = [z.beleg for z in daten]
		zeile = {z.beleg: z for z in daten}

		# Projekt mit seinem Auftrag darunter (eingerueckt); der Auftrag ohne Projekt steht oben daneben
		i = namen.index(projekt.name)
		self.assertEqual(namen[i + 1], so_projekt.name)
		self.assertEqual((zeile[projekt.name].indent, zeile[so_projekt.name].indent), (0, 1))
		self.assertEqual((zeile[so_frei.name].indent, zeile[so_frei.name].doctype), (0, "Sales Order"))
		self.assertEqual(zeile[projekt.name].doctype, "Project")

		# Projekt: alles, was auf ihm gebucht ist (4 Std.); Auftrag darunter nur seine 2 Std.
		self.assertEqual((flt(zeile[projekt.name].stunden), flt(zeile[projekt.name].stunden_offen)), (4, 4))
		self.assertEqual((flt(zeile[so_projekt.name].stunden), flt(zeile[so_projekt.name].auftragswert)), (2, 15))
		self.assertEqual(zeile[so_projekt.name].bezeichnung, so_projekt.po_no)
		self.assertEqual(flt(zeile[projekt.name].betrag_offen), 360)

		# Nach der Rechnung fuer den Auftrags-Einsatz: Auftrag ganz, Projekt zur Haelfte berechnet
		si = self.rechnung(4)
		for z in si.items:
			z.sales_order = so_projekt.name
		si.project = projekt.name
		si.insert() if si.is_new() else si.save()
		si.submit()
		zeile = {z.beleg: z for z in auftraege_und_projekte({"customer": KUNDE_A})[1]}
		self.assertEqual(flt(zeile[so_projekt.name].zeit_prozent), 100)
		self.assertEqual(flt(zeile[projekt.name].zeit_prozent), 50)
		self.assertEqual(flt(zeile[so_projekt.name].abgerechnet), flt(si.net_total))

		# Filter: nur ein Projekt - samt Auftraegen, ohne freie Auftraege
		nur_projekt = [z.beleg for z in auftraege_und_projekte({"project": projekt.name})[1]]
		self.assertEqual(nur_projekt, [projekt.name, so_projekt.name])

	def test_abgeschlossene_ausblenden(self):
		projekt = make_project(status="Completed")
		namen = lambda f: [z.beleg for z in auftraege_und_projekte({"customer": KUNDE_A, **f})[1]]  # noqa: E731
		self.assertNotIn(projekt.name, namen({}))
		self.assertIn(projekt.name, namen({"abgeschlossene_ausblenden": 0}))

	def test_abgeschlossenes_projekt_mit_offenem_auftrag_bleibt_kopfzeile(self):
		projekt = make_project(status="Completed")
		so = make_sales_order(self.ctx.company, submit=False)
		so.db_set("project", projekt.name)
		zeilen = auftraege_und_projekte({"customer": KUNDE_A})[1]
		namen = [z.beleg for z in zeilen]
		self.assertIn(projekt.name, namen)
		self.assertEqual(namen[namen.index(projekt.name) + 1], so.name)
		self.assertEqual(zeilen[namen.index(so.name)].indent, 1)

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_rechte(self):
		"""Ueber den Desk-Weg (frappe.desk.query_report.run): die Abrechnungsansicht fuer
		Buchhaltung, Techniker sehen keine der beiden Ansichten."""
		from frappe.desk.query_report import run

		frappe.set_user(BUCHHALTUNG)
		self.assertIn("result", run("Abrechnungsansicht", filters={}))
		with self.assertRaises(frappe.PermissionError):
			run("Auftrags- und Projektansicht", filters={})

		frappe.set_user(TECH)
		for bericht in ("Abrechnungsansicht", "Auftrags- und Projektansicht"):
			with self.assertRaises(frappe.PermissionError):
				run(bericht, filters={})
