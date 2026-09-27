import frappe


def execute():
	"""Die neuen Haken "Timer automatisch starten"/"Kamera automatisch
	oeffnen" sollen sich wie das bisherige (fest eingebaute) Verhalten
	verhalten: an. Ein Feld-Default in der DocType-JSON greift dafuer nicht,
	da er nur bei neu angelegten Dokumenten zieht - nicht rueckwirkend bei
	einem bereits bestehenden "Fahrtenbuch Einstellungen"-Singleton."""
	frappe.db.set_single_value("Fahrtenbuch Einstellungen", "auto_start_timer", 1)
	frappe.db.set_single_value("Fahrtenbuch Einstellungen", "auto_open_camera", 1)
