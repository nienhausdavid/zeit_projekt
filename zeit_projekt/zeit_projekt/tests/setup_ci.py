"""Einrichtung einer frischen Test-Site (CI oder lokal):

    bench --site <site> execute zeit_projekt.zeit_projekt.tests.setup_ci.complete_setup

Schliesst den ERPNext-Einrichtungsassistenten ab (Firma, Geschaeftsjahr,
Standard-Preisliste) - die Integrationstests setzen das voraus."""

import frappe


def complete_setup():
	if frappe.db.get_single_value("Global Defaults", "default_company"):
		print("Einrichtung bereits abgeschlossen")
		return

	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	setup_complete(
		{
			"currency": "EUR",
			"full_name": "Test User",
			"company_name": "ZP Test GmbH",
			"company_abbr": "ZPT",
			"timezone": "Europe/Berlin",
			"country": "Germany",
			"fy_start_date": f"{frappe.utils.getdate().year}-01-01",
			"fy_end_date": f"{frappe.utils.getdate().year}-12-31",
			"language": "English",
			"email": "test@example.com",
			"password": "Test-1234-xyz",
			"chart_of_accounts": "Standard",
			"enable_telemetry": 0,
			"setup_demo": 0,
		}
	)
	frappe.db.commit()
	print("Firma:", frappe.db.get_single_value("Global Defaults", "default_company"))
