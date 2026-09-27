import copy
from contextlib import contextmanager

import frappe


@contextmanager
def _as_administrator():
	"""Fuehrt den with-Block als Administrator aus - fuer den Abrechnungs-
	Schritt, auf den der Techniker (Employee) i. d. R. keine eigenen
	Sales-Order-Rechte hat. Die eigentliche Berechtigungspruefung ist die auf
	die Fahrt selbst.

	frappe.set_user() leert local.form_dict komplett - ohne Sicherung wuerde
	das den umgebenden Request (das Buchen der Fahrt selbst, das nach diesem
	Hook weiterlaeuft) seiner eigenen Parameter berauben. Deshalb hier
	explizit gesichert und danach wiederhergestellt (1:1 uebernommen aus
	site_visit.site_visit.site_visit - dort ausfuehrlicher kommentiert)."""
	current_user = frappe.session.user
	form_dict_backup = copy.deepcopy(frappe.local.form_dict)
	frappe.set_user("Administrator")
	try:
		yield
	finally:
		frappe.set_user(current_user)
		frappe.local.form_dict = form_dict_backup


def before_submit(doc, method=None):
	"""Uebernimmt Fahrzeit (immer) und Kilometer (nur falls bill_km) als
	Positionen in den verknuepften Auftrag - im selben Request wie das Buchen
	der Fahrt selbst, aus demselben Grund wie in site_visit (siehe
	_as_administrator oben).

	Nutzt erpnext.controllers.accounts_controller.update_child_qty_rate -
	dieselbe Funktion, die auch der "Update Items"-Dialog im Auftrag selbst
	verwendet: das uebernimmt auch bei bereits gebuchten Auftraegen korrekt
	Steuer-/Summenneuberechnung, Kreditlimitpruefung usw."""
	from erpnext.controllers.accounts_controller import update_child_qty_rate

	so = frappe.get_doc("Sales Order", doc.sales_order)
	trans_items = []
	for row in so.items:
		item = row.as_dict()
		item["docname"] = row.name
		trans_items.append(item)

	trans_items.append({"item_code": doc.time_item, "qty": doc.duration_hours})
	if doc.bill_km:
		trans_items.append({"item_code": doc.km_item, "qty": doc.distance_km})

	with _as_administrator():
		update_child_qty_rate("Sales Order", frappe.as_json(trans_items), so.name)


@frappe.whitelist()
def get_odometer_reading(file_url):
	"""Fuer den Foto-Upload im Formular: liest den Kilometerstand per
	Ollama-Vision-Modell aus (siehe ocr.py). None, wenn nichts Eindeutiges
	erkannt wurde oder das Modell nicht erreichbar ist - der Techniker
	traegt dann manuell ein."""
	from zeit_projekt.fahrtenbuch.ocr import read_odometer

	return read_odometer(file_url)


@frappe.whitelist()
def get_available_models(api_url=None, api_key=None):
	"""Fuer den "Modelle abrufen"-Button in Fahrtenbuch Einstellungen -
	api_url/api_key optional, damit ein gerade eingetipptes, noch nicht
	gespeichertes Feld direkt getestet werden kann."""
	from zeit_projekt.fahrtenbuch.ocr import list_models

	return list_models(api_url=api_url, api_key=api_key)


def check_app_permission():
	"""Fuer add_to_apps_screen in hooks.py: wer die App-Kachel im Desk sehen darf."""
	if frappe.session.user == "Administrator":
		return True
	roles = frappe.get_roles()
	return any(role in roles for role in ("System Manager", "Projects Manager", "Employee"))
