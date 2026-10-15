"""Link-Suchen und Detail-Abfragen fuer die Formulare Fahrt und Site Visit.

Techniker haben mit der Standardrolle "Employee" keine Leserechte auf
Kunde, Auftrag, Artikel und Fahrzeug - die Pflichtfelder waeren sonst nicht
auswaehlbar. Statt ihnen diese Doctypes komplett freizugeben, liefern die
Funktionen hier nur das Noetigste (Name + Bezeichnung) und nur an Nutzer, die
Fahrten oder Site Visits anlegen/bearbeiten duerfen.

Frappe ruft eigene Link-Queries (set_query mit query=...) ohne eigene
Rollenpruefung auf (frappe/desk/search.py -> search_widget) - die Pruefung
passiert deshalb hier in _check_access()."""

import erpnext
import frappe
from frappe import _
from frappe.utils import add_years, getdate, nowdate

from zeit_projekt.zeit_projekt.billing import GESCHLOSSENE_STATUS

LINK_DETAILS = {
	"Sales Order": ("customer", "customer_name", "project"),
	"Project": ("customer",),
	"Customer": ("customer_name",),
	"Item": ("item_name", "stock_uom"),
	"Site Visit": ("customer", "project", "sales_order"),
}


def _check_access():
	for doctype in ("Fahrt", "Site Visit"):
		for ptype in ("create", "write"):
			if frappe.has_permission(doctype, ptype):
				return
	frappe.throw(_("Keine Berechtigung."), frappe.PermissionError)


def _as_dict(filters):
	if isinstance(filters, dict):
		return filters
	# Listenform [[doctype, fieldname, "=", value], ...] - nur Gleichheit
	return {f[1]: f[3] for f in filters or [] if len(f) >= 4 and f[2] == "="}


def _search(doctype, txt, fields, filters, start, page_len, search_fields):
	or_filters = [[doctype, f, "like", f"%{txt}%"] for f in search_fields] if txt else None
	return frappe.get_all(
		doctype,
		filters=filters,
		or_filters=or_filters,
		fields=fields,
		start=start,
		limit=page_len,
		order_by="modified desc",
		as_list=True,
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def customer_query(doctype, txt, searchfield, start, page_len, filters, **kwargs):
	_check_access()
	return _search(
		"Customer", txt, ["name", "customer_name"], {"disabled": 0}, start, page_len, ["name", "customer_name"]
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def sales_order_query(doctype, txt, searchfield, start, page_len, filters, **kwargs):
	_check_access()
	filters = _as_dict(filters)
	conditions = {"docstatus": ["<", 2], "status": ["not in", GESCHLOSSENE_STATUS]}
	for key in ("customer", "project"):
		if filters.get(key):
			conditions[key] = filters[key]
	return _search(
		"Sales Order",
		txt,
		["name", "customer_name", "po_no"],
		conditions,
		start,
		page_len,
		["name", "customer_name", "po_no"],
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def item_query(doctype, txt, searchfield, start, page_len, filters, **kwargs):
	from zeit_projekt.zeit_projekt.doctype.zeit_projekt_einstellungen.zeit_projekt_einstellungen import (
		excluded_item_groups,
	)

	_check_access()
	conditions = {"disabled": 0, "is_sales_item": 1, "has_variants": 0}
	ausgeschlossen = excluded_item_groups()
	if ausgeschlossen:
		conditions["item_group"] = ["not in", list(ausgeschlossen)]
	return _search(
		"Item",
		txt,
		["name", "item_name"],
		conditions,
		start,
		page_len,
		["name", "item_name"],
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def vehicle_query(doctype, txt, searchfield, start, page_len, filters, **kwargs):
	_check_access()
	return _search("Vehicle", txt, ["name", "make", "model"], {}, start, page_len, ["name", "make", "model"])


@frappe.whitelist()
def get_link_details(doctype, name):
	"""Nur die fuer das automatische Vorbelegen noetigen Felder."""
	_check_access()
	fields = LINK_DETAILS.get(doctype)
	if not fields:
		frappe.throw(_("Keine Berechtigung."), frappe.PermissionError)
	return frappe.db.get_value(doctype, name, list(fields), as_dict=True) or {}


@frappe.whitelist()
def get_open_sales_orders(project, customer=None):
	"""Offene Auftraege zum Projekt (neueste zuerst) - bei genau einem wird er
	im Formular direkt uebernommen, bei mehreren erscheint ein Auswahldialog
	mit Kommissionsnummer und Datum."""
	_check_access()
	filters = {"project": project, "docstatus": ["<", 2], "status": ["not in", GESCHLOSSENE_STATUS]}
	if customer:
		filters["customer"] = customer
	return frappe.get_all(
		"Sales Order",
		filters=filters,
		fields=["name", "po_no", "transaction_date", "customer_name"],
		order_by="transaction_date desc, creation desc",
		limit=20,
	)


# --- Eigenen Mitarbeiter anlegen ("Fragebogen") -----------------------------------------
# Techniker duerfen Mitarbeiter nicht anlegen und nicht lesen. Statt ihnen Rechte auf
# Employee zu geben, legt diese Methode genau EINEN Mitarbeiter an: den eigenen (Benutzer-ID
# = angemeldeter Benutzer), mit wenigen Pflichtangaben. Weder Benutzer noch Firma, Abteilung,
# Vorgesetzte oder Gehalt sind waehlbar.
#
# ERPNext haengt die Rolle "Employee" an den Mitarbeiter-Eintrag: beim Speichern mit
# Benutzer-ID wird sie automatisch vergeben (und ohne Eintrag bei jedem Speichern des
# Benutzers wieder entfernt, erpnext.setup.doctype.employee.employee.validate_employee_role).
# Ein Benutzer ohne Mitarbeiter hat sie also nicht - die Selbstanlage kann deshalb keine
# Rolle voraussetzen. Stattdessen: nur Desk-Benutzer (keine Website-Benutzer, kein Gast), nur
# der eigene Eintrag, nur einmal, und nur wenn die Verwaltung es in den Zeit Projekt
# Einstellungen freigeschaltet hat ("employee_self_service", Standard aus). Dazu legt ERPNext
# Benutzerberechtigungen auf den eigenen Mitarbeiter und die Firma an (schraenkt ein).


def _check_desk_user():
	user = frappe.session.user
	if user == "Guest" or frappe.db.get_value("User", user, "user_type") != "System User":
		frappe.throw(_("Keine Berechtigung."), frappe.PermissionError)


def _check_self_service():
	_check_desk_user()
	if not frappe.get_cached_doc("Zeit Projekt Einstellungen").employee_self_service:
		frappe.throw(
			_("Die Selbstanlage ist nicht freigeschaltet. Bitte die Verwaltung informieren."),
			frappe.PermissionError,
		)


def _check_self_edit():
	"""Eigene Mitarbeiterdaten aendern: Desk-Benutzer, Einstellung an, eigener Mitarbeiter da."""
	_check_desk_user()
	if not frappe.get_cached_doc("Zeit Projekt Einstellungen").employee_self_edit:
		frappe.throw(
			_("Das Ändern der eigenen Mitarbeiterdaten ist nicht freigeschaltet. Bitte die Verwaltung informieren."),
			frappe.PermissionError,
		)
	name = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	if not name:
		frappe.throw(_("Für Ihren Benutzer gibt es noch keinen Mitarbeiter."))
	return name


@frappe.whitelist()
def get_employee_status():
	"""Eigener Mitarbeiter und was moeglich ist (Selbstanlage, eigene Daten aendern) - nur
	Angaben zum eigenen Benutzer, auch ohne Leserecht auf Employee."""
	_check_desk_user()
	name = frappe.db.get_value("Employee", {"user_id": frappe.session.user, "status": "Active"}, "name")
	einstellungen = frappe.get_cached_doc("Zeit Projekt Einstellungen")
	return {
		"employee": name,
		"self_service": bool(einstellungen.employee_self_service) and not name,
		"self_edit": bool(einstellungen.employee_self_edit) and bool(name),
	}


@frappe.whitelist()
def get_employee_form_data(bearbeiten: int = 0):
	"""Vorbelegung und Auswahl fuer den Fragebogen. Mit bearbeiten=1 die Daten des eigenen
	Mitarbeiters (nur die aenderbaren Felder), sonst Name aus dem Benutzer."""
	if int(bearbeiten):
		name = _check_self_edit()
		emp = frappe.db.get_value(
			"Employee", name, ["first_name", "last_name", "gender", "date_of_birth", "date_of_joining"], as_dict=True
		)
		daten = {k: (str(v) if v else None) for k, v in emp.items()}
	else:
		_check_self_service()
		user = frappe.db.get_value("User", frappe.session.user, ["first_name", "last_name"], as_dict=True)
		daten = {"first_name": user.first_name, "last_name": user.last_name}
	return {
		**daten,
		"genders": frappe.get_all("Gender", pluck="name", order_by="name asc"),
		"company": erpnext.get_default_company(),
	}


def _pruefe_angaben(first_name, gender, date_of_birth, last_name, date_of_joining):
	"""Gemeinsame Pruefung fuer Anlegen und Aendern; gibt die bereinigten Werte zurueck."""
	first_name = (first_name or "").strip()
	if not first_name:
		frappe.throw(_("Bitte einen Vornamen angeben."), frappe.MandatoryError)
	if not frappe.db.exists("Gender", gender):
		frappe.throw(_("Ungültiges Geschlecht: {0}").format(frappe.bold(gender)))

	heute = getdate(nowdate())
	geburt = getdate(date_of_birth)
	if geburt >= add_years(heute, -14) or geburt.year < 1900:
		frappe.throw(_("Bitte ein plausibles Geburtsdatum angeben."))
	eintritt = getdate(date_of_joining) if date_of_joining else heute
	if eintritt > heute:
		frappe.throw(_("Das Eintrittsdatum darf nicht in der Zukunft liegen."))
	return {
		"first_name": first_name,
		"last_name": (last_name or "").strip() or None,
		"gender": gender,
		"date_of_birth": geburt,
		"date_of_joining": eintritt,
	}


@frappe.whitelist()
def create_own_employee(
	first_name: str,
	gender: str,
	date_of_birth: str,
	last_name: str | None = None,
	date_of_joining: str | None = None,
):
	"""Legt den Mitarbeiter fuer den angemeldeten Benutzer an (genau einmal)."""
	_check_self_service()

	vorhanden = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	if vorhanden:
		frappe.throw(_("Für Ihren Benutzer gibt es schon einen Mitarbeiter ({0}).").format(vorhanden))

	angaben = _pruefe_angaben(first_name, gender, date_of_birth, last_name, date_of_joining)
	company = erpnext.get_default_company()
	if not company:
		frappe.throw(_("Es ist keine Standardfirma eingerichtet. Bitte die Verwaltung informieren."))

	employee = frappe.get_doc(
		{
			"doctype": "Employee",
			**angaben,
			"company": company,
			"status": "Active",
			"user_id": frappe.session.user,
			# ERPNext beschraenkt den Benutzer damit per Benutzerberechtigung auf seinen eigenen
			# Mitarbeiter und die Firma - fuer Techniker gewollt, fuer einen System Manager eine
			# Falle (er saehe danach nur noch sich selbst).
			"create_user_permission": 0 if "System Manager" in frappe.get_roles() else 1,
		}
	)
	employee.flags.ignore_permissions = True
	employee.insert()
	return employee.name


@frappe.whitelist()
def update_own_employee(
	first_name: str,
	gender: str,
	date_of_birth: str,
	last_name: str | None = None,
	date_of_joining: str | None = None,
):
	"""Aendert die erlaubten Angaben des EIGENEN Mitarbeiters (nur mit freigeschalteter
	Einstellung). Firma, Status, Benutzer und alles andere bleiben unberuehrt."""
	name = _check_self_edit()
	angaben = _pruefe_angaben(first_name, gender, date_of_birth, last_name, date_of_joining)
	employee = frappe.get_doc("Employee", name)
	employee.update(angaben)
	employee.flags.ignore_permissions = True
	employee.save()
	return employee.name
