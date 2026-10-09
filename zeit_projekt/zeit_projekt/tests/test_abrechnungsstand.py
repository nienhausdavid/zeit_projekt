import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from zeit_projekt.site_visit.site_visit import create_sales_order
from zeit_projekt.zeit_projekt.sales_invoice import get_billable_time_logs
from zeit_projekt.zeit_projekt.tests.utils import KUNDE_A, MONTAGE, ensure_fixtures, make_sales_order


class TestAbrechnungsstand(IntegrationTestCase):
	"""Auftraege, deren Zeit ueber das Zeitblatt abgerechnet wird: "% berechnet"
	muss Zeitbuchungen mitzaehlen (billing_status.py)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = ensure_fixtures()

	def einsatz(self, sales_order, tag):
		sv = frappe.get_doc(
			{
				"doctype": "Site Visit",
				"sales_order": sales_order,
				"employee": self.ctx.employee,
				"activity_type": MONTAGE,
				"date": f"2032-02-{tag:02d}",
				"from_time": f"2032-02-{tag:02d} 10:00:00",
				"to_time": f"2032-02-{tag:02d} 11:30:00",
			}
		).insert()
		sv.submit()
		return sv

	def rechnung(self, tag):
		"""Rechnung wie aus dem Zeitimport fuer die Zeiten eines Tages."""
		tag = f"2032-02-{tag:02d}"
		zeilen = get_billable_time_logs(KUNDE_A, from_time=f"{tag} 00:00:00", to_time=f"{tag} 23:59:59")["rows"]
		si = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"customer": KUNDE_A,
				"company": self.ctx.company,
				"items": [
					{"item_code": "ZP-MONTAGE", "qty": flt(z.billing_hours), "sales_order": z.sales_order}
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
		si.submit()
		return si

	def stand(self, sales_order):
		d = frappe.db.get_value("Sales Order", sales_order, ["per_billed", "billing_status"], as_dict=True)
		return round(flt(d.per_billed), 2), d.billing_status

	def test_nur_zeit_schrittweise_abgerechnet(self):
		so = frappe.get_doc("Sales Order", create_sales_order(KUNDE_A, MONTAGE))
		so.submit()
		self.einsatz(so.name, 1)
		self.einsatz(so.name, 2)
		self.assertEqual(self.stand(so.name), (0, "Not Billed"))

		# ERPNext allein haette hier "Fully Billed" gesetzt (1,5 Std. >= Menge 1)
		self.rechnung(1)
		self.assertEqual(self.stand(so.name), (50, "Partly Billed"))

		zweite = self.rechnung(2)
		self.assertEqual(self.stand(so.name), (100, "Fully Billed"))

		zweite.cancel()
		self.assertEqual(self.stand(so.name), (50, "Partly Billed"))

	def test_auftrag_erst_nach_der_rechnung_gebucht(self):
		so = frappe.get_doc("Sales Order", create_sales_order(KUNDE_A, MONTAGE))
		self.einsatz(so.name, 3)
		si = self.rechnung(3)
		self.assertFalse(si.items[0].sales_order)  # Entwurf: kein Auftragsbezug in der Position

		so.reload()
		so.submit()
		self.assertEqual(self.stand(so.name), (100, "Fully Billed"))

	def test_zusatzartikel_und_zeit_zusammen(self):
		from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

		so = make_sales_order(self.ctx.company)  # ZP-ADAPTER 1 x 15
		self.einsatz(so.name, 4)  # 1,5 Std. x 90 = 135

		aus_auftrag = make_sales_invoice(so.name)
		aus_auftrag.insert()
		aus_auftrag.submit()
		# ERPNext allein: 100 % - die Zeit ist aber noch offen
		self.assertEqual(self.stand(so.name), (10, "Partly Billed"))

		self.rechnung(4)
		self.assertEqual(self.stand(so.name), (100, "Fully Billed"))
