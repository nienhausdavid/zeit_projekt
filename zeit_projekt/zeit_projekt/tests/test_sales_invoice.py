import frappe
from frappe.tests import IntegrationTestCase

from zeit_projekt.zeit_projekt.sales_invoice import get_billable_time_logs
from zeit_projekt.zeit_projekt.tests.utils import KUNDE_A, KUNDE_B, MONTAGE, ensure_fixtures


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
