import math

import frappe
from frappe import _
from frappe.utils import cint, flt, format_date

from zeit_projekt.zeit_projekt.billing import cancel_timesheet, create_timesheet


def before_submit(doc, method=None):
	"""Bucht die Fahrzeit als Zeitblatt - wie die Einsatzzeit aus dem Site
	Visit. Abgerechnet wird beides ueber den Zeitimport der Ausgangsrechnung;
	die Kilometer (falls bill_km) holt derselbe Import direkt aus der Fahrt."""
	doc.timesheet = create_timesheet(
		doc,
		doc.activity_type,
		doc.start_time,
		doc.end_time,
		customer=doc.customer,
		project=doc.project,
		description=positionstext(doc, _("Fahrzeit")),
		billing_hours=abrechenbare_stunden(doc.duration_hours),
	)


def on_cancel(doc, method=None):
	if doc.km_sales_invoice and frappe.db.get_value("Sales Invoice", doc.km_sales_invoice, "docstatus") == 1:
		frappe.throw(
			_("Die Kilometer dieser Fahrt wurden bereits in {0} abgerechnet.").format(doc.km_sales_invoice)
		)
	cancel_timesheet(doc.timesheet)


def abrechenbare_stunden(stunden):
	"""Taktung aus "Fahrtenbuch Einstellungen": auf volle Schritte aufrunden.
	0 = keine Taktung (None -> das Zeitblatt nimmt die tatsaechliche Dauer)."""
	schritt = cint(frappe.db.get_single_value("Fahrtenbuch Einstellungen", "rounding_minutes"))
	if schritt <= 0:
		return None
	minuten = math.ceil(round(flt(stunden) * 60, 4) / schritt) * schritt
	return flt(minuten / 60, 4)


def positionstext(doc, art):
	"""Beschreibung fuer Zeitbuchung bzw. Rechnungsposition, z. B.
	"Fahrzeit FB-2026-00001, 20.09.2026, Werkstatt → Kunde"."""
	teile = [f"{art} {doc.name}", format_date(doc.date)]
	if doc.start_location or doc.end_location:
		teile.append(f"{doc.start_location or '?'} → {doc.end_location or '?'}")
	return ", ".join(teile)


@frappe.whitelist()
def get_fahrt_defaults():
	"""Vorbelegungen fuer das Fahrt-Formular. "Fahrtenbuch Einstellungen" darf
	nur der System Manager lesen (API-Schluessel) - Techniker bekommen hier nur
	die unkritischen Werte. get_cached_doc liefert bei nie gespeicherten
	Einstellungen die Feld-Defaults (beide Haken an)."""
	if not (frappe.has_permission("Fahrt", "create") or frappe.has_permission("Fahrt", "write")):
		frappe.throw(_("Keine Berechtigung."), frappe.PermissionError)
	settings = frappe.get_cached_doc("Fahrtenbuch Einstellungen")
	return {
		"activity_type": settings.activity_type,
		"km_item": settings.km_item,
		"auto_start_timer": cint(settings.auto_start_timer),
		"auto_open_camera": cint(settings.auto_open_camera),
	}


@frappe.whitelist()
def get_odometer_reading(file_url, fieldname):
	"""Fuer den Foto-Upload im Formular: stoesst die Kilometerstand-Erkennung
	per Vision-Modell (siehe ocr.py) als Hintergrund-Job an - die Anfrage kann
	bis zu 45 s dauern und soll das Formular nicht blockieren. Das Ergebnis
	kommt per Realtime-Event "zeit_projekt_odometer" an den Nutzer zurueck.

	Rueckgabe: {"request_id": ...} oder {"queued": False}, wenn die Erkennung
	nicht eingerichtet ist (dann traegt der Techniker manuell ein)."""
	from zeit_projekt.fahrtenbuch.ocr import is_configured

	if not (frappe.has_permission("Fahrt", "create") or frappe.has_permission("Fahrt", "write")):
		frappe.throw(_("Keine Berechtigung."), frappe.PermissionError)
	if not is_configured():
		return {"queued": False}

	# Nur Dateien, die der Nutzer selbst lesen darf - sonst liesse sich jede
	# private Datei an die externe Erkennungs-API schicken.
	for name in frappe.get_all("File", filters={"file_url": file_url}, pluck="name"):
		if frappe.get_doc("File", name).has_permission("read"):
			request_id = frappe.generate_hash(length=12)
			frappe.enqueue(
				"zeit_projekt.fahrtenbuch.fahrtenbuch.run_odometer_ocr",
				queue="short",
				timeout=120,
				enqueue_after_commit=True,
				file_name=name,
				fieldname=fieldname,
				request_id=request_id,
				user=frappe.session.user,
			)
			return {"queued": True, "request_id": request_id}
	frappe.throw(_("Keine Berechtigung für diese Datei."), frappe.PermissionError)


def run_odometer_ocr(file_name, fieldname, request_id, user):
	"""Hintergrund-Job: Erkennung ausfuehren und das Ergebnis (oder None) an
	das offene Formular des Nutzers melden."""
	from zeit_projekt.fahrtenbuch.ocr import read_odometer

	reading = read_odometer(frappe.get_doc("File", file_name))
	frappe.publish_realtime(
		"zeit_projekt_odometer",
		{"request_id": request_id, "fieldname": fieldname, "reading": reading},
		user=user,
		after_commit=False,
	)


@frappe.whitelist()
def get_available_models(api_url=None, api_key=None):
	"""Fuer den "Modelle abrufen"-Button in Fahrtenbuch Einstellungen -
	api_url/api_key optional, damit ein gerade eingetipptes, noch nicht
	gespeichertes Feld direkt getestet werden kann. Nur System Manager: der
	Server ruft dabei eine frei angegebene URL ab."""
	from zeit_projekt.fahrtenbuch.ocr import list_models

	frappe.only_for("System Manager")

	return list_models(api_url=api_url, api_key=api_key)
