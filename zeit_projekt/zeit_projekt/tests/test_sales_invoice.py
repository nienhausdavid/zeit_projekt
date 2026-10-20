import frappe
from frappe.tests import IntegrationTestCase

from zeit_projekt.zeit_projekt.sales_invoice import get_billable_time_logs
from zeit_projekt.zeit_projekt.tests.utils import (
	KUNDE_A,
	KUNDE_B,
	MONTAGE,
	ensure_fixtures,
	make_project,
	make_sales_order,
)


class TestZeitimport(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = ensure_fixtures()
		cls.ts = {kunde: cls.timesheet(kunde, tag) for tag, kunde in enumerate((KUNDE_A, KUNDE_B), start=1)}

	@classmethod
	def timesheet(cls, customer, tag):
		ts = frappe.get_doc(
			{
				"doctype": "Timesheet",
				"employee": cls.ctx.employee,
				"company": cls.ctx.company,
				"customer": customer,
				"time_logs": [
					{
						"activity_type": MONTAGE,
						"from_time": f"2031-05-0{tag} 08:00:00",
						"to_time": f"2031-05-0{tag} 09:00:00",
						"is_billable": 1,
					}
				],
			}
		).insert()
		ts.submit()
		return ts.name

	def zeiten(self, customer):
		return get_billable_time_logs(customer, from_time="2031-05-01 00:00:00", to_time="2031-05-31 23:59:59")

	def test_nur_zeiten_des_rechnungskunden(self):
		r = self.zeiten(KUNDE_A)
		self.assertEqual({z.time_sheet for z in r["rows"]}, {self.ts[KUNDE_A]})
		self.assertGreaterEqual(r["skipped"], 1)

		r = self.zeiten(KUNDE_B)
		self.assertEqual({z.time_sheet for z in r["rows"]}, {self.ts[KUNDE_B]})

	def test_kunde_pflicht(self):
		with self.assertRaises(frappe.ValidationError):
			get_billable_time_logs(None)

	def einsatz(self, sales_order, tag):
		sv = frappe.get_doc(
			{
				"doctype": "Site Visit",
				"sales_order": sales_order,
				"employee": self.ctx.employee,
				"activity_type": MONTAGE,
				"date": f"2031-06-{tag:02d}",
				"from_time": f"2031-06-{tag:02d} 10:00:00",
				"to_time": f"2031-06-{tag:02d} 11:30:00",
			}
		).insert()
		sv.submit()
		return sv

	def test_auftragsfilter_und_auftrag_in_der_rechnung(self):
		from frappe.utils import flt

		so_1, so_2 = make_sales_order(self.ctx.company), make_sales_order(self.ctx.company)
		sv_1, sv_2 = self.einsatz(so_1.name, 1), self.einsatz(so_2.name, 2)

		r = get_billable_time_logs(
			KUNDE_A, from_time="2031-06-01 00:00:00", to_time="2031-06-30 23:59:59", sales_order=so_1.name
		)
		self.assertEqual([(z.time_sheet, z.sales_order) for z in r["rows"]], [(sv_1.timesheet, so_1.name)])

		# Rechnung wie aus dem Import: Position mit Auftragsbezug laesst sich buchen
		zeile = r["rows"][0]
		si = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"customer": KUNDE_A,
				"company": self.ctx.company,
				"items": [{"item_code": "ZP-MONTAGE", "qty": flt(zeile.billing_hours), "sales_order": zeile.sales_order}],
				"timesheets": [{"time_sheet": zeile.time_sheet, "timesheet_detail": zeile.name, "billing_hours": zeile.billing_hours}],
			}
		)
		si.set_missing_values()
		si.insert()
		si.submit()
		self.assertEqual(si.items[0].sales_order, so_1.name)
		self.assertEqual(frappe.db.get_value("Timesheet Detail", zeile.name, "sales_invoice"), si.name)
		self.assertIn(sv_2.timesheet, {z.time_sheet for z in self.zeiten_juni()})

	def zeiten_juni(self):
		return get_billable_time_logs(KUNDE_A, from_time="2031-06-01 00:00:00", to_time="2031-06-30 23:59:59")["rows"]

	def test_auftrag_wird_an_alten_zeitbuchungen_nachgetragen(self):
		from zeit_projekt.install import _auftrag_an_zeitbuchungen_nachtragen

		so = make_sales_order(self.ctx.company)
		sv = self.einsatz(so.name, 3)
		zeilen = frappe.get_all("Timesheet Detail", filters={"parent": sv.timesheet}, pluck="name")
		for z in zeilen:
			frappe.db.set_value("Timesheet Detail", z, "custom_sales_order", None)

		_auftrag_an_zeitbuchungen_nachtragen()
		self.assertEqual(
			{frappe.db.get_value("Timesheet Detail", z, "custom_sales_order") for z in zeilen}, {so.name}
		)

	def test_projekt_abrechnen(self):
		"""Zeiten ohne Auftrag nur auf ein Projekt gebucht: der Zeitimport holt
		alle offenen des Projekts, die Rechnung traegt das Projekt - und der
		Projektstand (abrechenbar/abgerechnet) stimmt danach."""
		from frappe.utils import flt

		projekt = make_project()
		for tag in (6, 7):
			sv = frappe.get_doc(
				{
					"doctype": "Site Visit",
					"project": projekt.name,
					"employee": self.ctx.employee,
					"activity_type": MONTAGE,
					"date": f"2032-03-{tag:02d}",
					"from_time": f"2032-03-{tag:02d} 10:00:00",
					"to_time": f"2032-03-{tag:02d} 11:30:00",
				}
			).insert()
			sv.submit()

		# ohne Datumsgrenzen, wie der Knopf "Projekt abrechnen"
		r = get_billable_time_logs(KUNDE_A, project=projekt.name)
		self.assertEqual(len(r["rows"]), 2)
		self.assertEqual({z.project for z in r["rows"]}, {projekt.name})
		self.assertEqual(flt(frappe.db.get_value("Project", projekt.name, "total_billable_amount")), 270)

		si = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"customer": KUNDE_A,
				"company": self.ctx.company,
				"project": projekt.name,
				"items": [
					{
						"item_code": "ZP-MONTAGE",
						"qty": flt(z.billing_hours),
						"project": z.project,
						# der Import schreibt Datum/Uhrzeit hinein - so sind gleiche Artikel unterscheidbar
						"description": f"{z.from_time}-{z.to_time}",
					}
					for z in r["rows"]
				],
				"timesheets": [
					{"time_sheet": z.time_sheet, "timesheet_detail": z.name, "billing_hours": z.billing_hours}
					for z in r["rows"]
				],
			}
		)
		si.set_missing_values()
		si.insert()
		si.submit()

		self.assertEqual(flt(frappe.db.get_value("Project", projekt.name, "total_billed_amount")), flt(si.net_total))
		self.assertEqual(get_billable_time_logs(KUNDE_A, project=projekt.name)["rows"], [])
