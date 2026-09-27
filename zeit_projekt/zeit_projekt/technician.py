"""Link-Suchen und Detail-Abfragen fuer die Formulare Fahrt und Site Visit.

Techniker haben mit der Standardrolle "Employee" keine Leserechte auf
Kunde, Auftrag, Artikel und Fahrzeug - die Pflichtfelder waeren sonst nicht
auswaehlbar. Statt ihnen diese Doctypes komplett freizugeben, liefern die
Funktionen hier nur das Noetigste (Name + Bezeichnung) und nur an Nutzer, die
Fahrten oder Site Visits anlegen/bearbeiten duerfen.

Frappe ruft eigene Link-Queries (set_query mit query=...) ohne eigene
Rollenpruefung auf (frappe/desk/search.py -> search_widget) - die Pruefung
passiert deshalb hier in _check_access()."""

import frappe
from frappe import _

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
		page_length=page_len,
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
	_check_access()
	return _search(
		"Item",
		txt,
		["name", "item_name"],
		{"disabled": 0, "is_sales_item": 1, "has_variants": 0},
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
	"""Hoechstens zwei offene Auftraege zum Projekt - bei genau einem wird er
	im Formular direkt uebernommen."""
	_check_access()
	filters = {"project": project, "docstatus": ["<", 2], "status": ["not in", GESCHLOSSENE_STATUS]}
	if customer:
		filters["customer"] = customer
	return frappe.get_all("Sales Order", filters=filters, pluck="name", limit=2)
