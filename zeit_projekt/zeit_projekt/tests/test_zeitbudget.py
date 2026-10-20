import frappe
from frappe.tests import IntegrationTestCase

from zeit_projekt.site_visit.site_visit import create_sales_order
from zeit_projekt.zeit_projekt.report.auftrags__und_projektansicht.auftrags__und_projektansicht import (
	execute as auftraege_und_projekte,
)
from zeit_projekt.zeit_projekt.tests.utils import KUNDE_A, MONTAGE, TECH, ensure_fixtures
from zeit_projekt.zeit_projekt.zeitbudget import budget, farbe, get_zeitbudget, verbrauchte_stunden


class TestZeitbudget(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = ensure_fixtures()

	def tearDown(self):
		frappe.set_user("Administrator")

	def einsatz(self, so, tag, stunden):
		bis = f"{10 + int(stunden):02d}:{int(stunden % 1 * 60):02d}:00"
		sv = frappe.get_doc(
			{
				"doctype": "Site Visit",
				"customer": KUNDE_A,
				"employee": self.ctx.employee,
				"activity_type": MONTAGE,
				"date": f"2031-07-{tag:02d}",
				"from_time": f"2031-07-{tag:02d} 10:00:00",
				"to_time": f"2031-07-{tag:02d} {bis}",
				"sales_order": so,
			}
		).insert()
		sv.submit()

	def test_farbgrenzen(self):
		self.assertEqual([farbe(p) for p in (0, 79.9, 80, 100, 100.1, 250)], ["green", "green", "orange", "orange", "red", "red"])

	def test_ohne_planung_kein_budget(self):
		self.assertIsNone(budget(0, 5))
		self.assertIsNone(budget(None, 5))
		so = create_sales_order(KUNDE_A, MONTAGE)
		self.assertIsNone(get_zeitbudget(so))

	def test_verbrauch_gegen_plan_mit_farbe(self):
		so = create_sales_order(KUNDE_A, MONTAGE, geplante_stunden=4)
		self.assertEqual(get_zeitbudget(so)["verbraucht"], 0)

		self.einsatz(so, 1, 2)
		b = get_zeitbudget(so)
		self.assertEqual((b["verbraucht"], b["prozent"], b["farbe"], b["rest"]), (2.0, 50.0, "green", 2.0))

		self.einsatz(so, 2, 1.5)
		b = get_zeitbudget(so)
		self.assertEqual((b["verbraucht"], b["prozent"], b["farbe"]), (3.5, 87.5, "orange"))

		self.einsatz(so, 3, 1)
		b = get_zeitbudget(so)
		self.assertEqual((b["prozent"], b["farbe"], b["rest"]), (112.5, "red", -0.5))

	def test_pauschale_zeit_zaehlt_gegen_den_plan(self):
		so = create_sales_order(KUNDE_A, MONTAGE, abrechnungsart="Pauschale", geplante_stunden=10)
		self.einsatz(so, 4, 2)
		self.assertEqual(verbrauchte_stunden([so]), {so: 2.0})
		self.assertEqual(get_zeitbudget(so)["prozent"], 20.0)

	def test_techniker_sieht_das_budget(self):
		so = create_sales_order(KUNDE_A, MONTAGE, geplante_stunden=8)
		frappe.set_user(TECH)
		self.assertEqual(get_zeitbudget(so)["geplant"], 8.0)

	def test_auftragsansicht_zeigt_budget(self):
		so = create_sales_order(KUNDE_A, MONTAGE, geplante_stunden=2)
		ohne = create_sales_order(KUNDE_A, MONTAGE)
		self.einsatz(so, 5, 3)
		zeilen = {z.beleg: z for z in auftraege_und_projekte({"customer": KUNDE_A})[1]}
		self.assertEqual(
			(zeilen[so].geplant, zeilen[so].verbraucht, zeilen[so].budget_prozent, zeilen[so].budget_farbe),
			(2.0, 3.0, 150.0, "red"),
		)
		self.assertIsNone(zeilen[ohne].budget_prozent)
