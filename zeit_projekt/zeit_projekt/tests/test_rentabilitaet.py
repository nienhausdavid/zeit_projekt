import frappe
from frappe.tests import IntegrationTestCase

from zeit_projekt.site_visit.site_visit import create_sales_order
from zeit_projekt.zeit_projekt.rentabilitaet import farbe, get_rentabilitaet, rentabilitaet
from zeit_projekt.zeit_projekt.report.auftrags__und_projektansicht.auftrags__und_projektansicht import (
	execute as auftraege_und_projekte,
)
from zeit_projekt.zeit_projekt.tests.utils import KUNDE_A, MONTAGE, TECH, ensure_fixtures


class TestRentabilitaet(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = ensure_fixtures()

	def tearDown(self):
		frappe.set_user("Administrator")

	def einsatz(self, so, tag, stunden):
		sv = frappe.get_doc(
			{
				"doctype": "Site Visit",
				"customer": KUNDE_A,
				"employee": self.ctx.employee,
				"activity_type": MONTAGE,
				"date": f"2031-08-{tag:02d}",
				"from_time": f"2031-08-{tag:02d} 08:00:00",
				"to_time": f"2031-08-{tag:02d} {8 + int(stunden):02d}:00:00",
				"sales_order": so,
			}
		).insert()
		sv.submit()

	def test_farbgrenzen(self):
		self.assertEqual([farbe(x) for x in (10, 0, -0.1, -20, -20.1, -50)], ["green", "green", "orange", "orange", "red", "red"])

	def test_nur_pauschale_mit_betrag(self):
		self.assertIsNone(rentabilitaet(create_sales_order(KUNDE_A, MONTAGE, geplante_stunden=8)))
		# Pauschale ohne Preis: nichts zu messen
		self.assertIsNone(rentabilitaet(create_sales_order(KUNDE_A, abrechnungsart="Pauschale", pauschalbezeichnung="Test")))

	def test_satz_geplant_und_effektiv_gegen_sollsatz(self):
		so = create_sales_order(
			KUNDE_A, abrechnungsart="Pauschale", geplante_stunden=10, pauschalpreis=760, pauschalbezeichnung="Test",
			positionen=[{"item_code": "ZP-ADAPTER", "qty": 3}],  # Material zaehlt nicht zum Pauschalbetrag
		)
		self.einsatz(so, 10, 8)  # 760 / 8 = 95 = Sollsatz
		r = rentabilitaet(so)
		self.assertEqual((r["betrag"], r["geplanter_satz"], r["effektiver_satz"], r["sollsatz"]), (760, 76.0, 95.0, 95.0))
		self.assertEqual((r["abweichung"], r["farbe"]), (0.0, "green"))

		self.einsatz(so, 11, 2)  # 10 Std. -> 76 = 20 % darunter
		r = rentabilitaet(so)
		self.assertEqual((r["effektiver_satz"], r["abweichung"], r["farbe"]), (76.0, -20.0, "orange"))

		self.einsatz(so, 12, 1)  # 11 Std. -> 69,09
		r = rentabilitaet(so)
		self.assertEqual((r["effektiver_satz"], r["abweichung"], r["farbe"]), (69.09, -27.3, "red"))

	def test_vor_der_ersten_buchung_zaehlt_der_geplante_satz(self):
		frappe.db.set_single_value("Zeit Projekt Einstellungen", "activity_type", MONTAGE)
		frappe.clear_document_cache("Zeit Projekt Einstellungen", "Zeit Projekt Einstellungen")
		so = create_sales_order(
			KUNDE_A, abrechnungsart="Pauschale", geplante_stunden=16, pauschalpreis=1200, pauschalbezeichnung="Test"
		)
		r = rentabilitaet(so)
		self.assertIsNone(r["effektiver_satz"])
		self.assertEqual((r["geplanter_satz"], r["sollsatz"], r["abweichung"], r["farbe"]), (75.0, 95.0, -21.1, "red"))

	def test_ansicht_und_rechte(self):
		so = create_sales_order(
			KUNDE_A, abrechnungsart="Pauschale", geplante_stunden=10, pauschalpreis=950, pauschalbezeichnung="Test"
		)
		self.einsatz(so, 13, 10)
		zeile = {z.beleg: z for z in auftraege_und_projekte({"customer": KUNDE_A})[1]}[so]
		self.assertEqual((zeile.satz_effektiv, zeile.sollsatz, zeile.satz_abweichung, zeile.satz_farbe), (95.0, 95.0, 0.0, "green"))
		self.assertEqual(get_rentabilitaet(so)["farbe"], "green")
		# Techniker duerfen den Auftrag - und damit Preise - nicht lesen
		frappe.set_user(TECH)
		self.assertIsNone(get_rentabilitaet(so))
