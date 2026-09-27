import frappe
from frappe import _
from frappe.utils import cint, format_date

from zeit_projekt.zeit_projekt.billing import add_rows_to_sales_order, remove_rows_from_sales_order


def before_submit(doc, method=None):
	"""Uebernimmt Fahrzeit (immer) und Kilometer (nur falls bill_km) als
	Positionen in den verknuepften Auftrag - im selben Request wie das Buchen
	der Fahrt selbst. Die Namen der neuen Auftragspositionen werden gemerkt,
	damit on_cancel genau diese wieder entfernen kann."""
	if not doc.customer:
		doc.customer = frappe.db.get_value("Sales Order", doc.sales_order, "customer")

	rows = [
		{"item_code": doc.time_item, "qty": doc.duration_hours, "description": _positionstext(doc, _("Fahrzeit"))}
	]
	if doc.bill_km:
		rows.append(
			{"item_code": doc.km_item, "qty": doc.distance_km, "description": _positionstext(doc, _("Kilometer"))}
		)

	doc.sales_order_items = "\n".join(add_rows_to_sales_order(doc.sales_order, doc.customer, rows))


def on_cancel(doc, method=None):
	remove_rows_from_sales_order(doc.sales_order, (doc.sales_order_items or "").split())


def _positionstext(doc, art):
	"""Eindeutig je Fahrt: ERPNext lehnt sonst eine zweite Position mit gleichem
	Artikel und gleicher Beschreibung im selben Auftrag ab ("entered multiple
	times"), solange Mehrfachartikel in den Verkaufseinstellungen aus sind."""
	teile = [f"{art} {doc.name}", format_date(doc.date)]
	if doc.start_location or doc.end_location:
		teile.append(f"{doc.start_location or '?'} → {doc.end_location or '?'}")
	return ", ".join(teile)


@frappe.whitelist()
def get_fahrt_defaults():
	"""Vorbelegungen fuer das Fahrt-Formular. "Fahrtenbuch Einstellungen" darf
	nur der System Manager lesen (API-Schluessel) - Techniker bekommen hier nur
	die drei unkritischen Werte. get_cached_doc liefert bei nie gespeicherten
	Einstellungen die Feld-Defaults (beide Haken an)."""
	if not (frappe.has_permission("Fahrt", "create") or frappe.has_permission("Fahrt", "write")):
		frappe.throw(_("Keine Berechtigung."), frappe.PermissionError)
	settings = frappe.get_cached_doc("Fahrtenbuch Einstellungen")
	return {
		"time_item": settings.time_item,
		"auto_start_timer": cint(settings.auto_start_timer),
		"auto_open_camera": cint(settings.auto_open_camera),
	}


@frappe.whitelist()
def get_odometer_reading(file_url):
	"""Fuer den Foto-Upload im Formular: liest den Kilometerstand per
	Vision-Modell aus (siehe ocr.py). None, wenn nichts Eindeutiges erkannt
	wurde oder das Modell nicht erreichbar ist - der Techniker traegt dann
	manuell ein."""
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
