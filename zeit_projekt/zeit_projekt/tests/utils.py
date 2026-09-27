"""Gemeinsame Testdaten fuer die Integrationstests der App.

Voraussetzung: eine Site mit ERPNext und abgeschlossenem Einrichtungsassistenten
(Firma, Geschaeftsjahr, Standard-Preisliste) - in der CI erledigt das
setup_ci.complete_setup. Alles hier Angelegte wird von IntegrationTestCase nach
jeder Testklasse zurueckgerollt."""

from contextlib import contextmanager

import frappe
from frappe.utils import add_days, nowdate

TECH = "zp-tech@example.com"
BUCHHALTUNG = "zp-buchhaltung@example.com"
KUNDE_A = "ZP Kunde A"
KUNDE_B = "ZP Kunde B"
FAHRZEIT = "ZP Fahrzeit"
MONTAGE = "ZP Montage"


def ensure_fixtures():
	frappe.set_user("Administrator")
	company = frappe.db.get_single_value("Global Defaults", "default_company")
	abbr = frappe.db.get_value("Company", company, "abbr")
	if not frappe.db.get_single_value("Stock Settings", "default_warehouse"):
		frappe.db.set_single_value("Stock Settings", "default_warehouse", f"Stores - {abbr}")
	frappe.db.set_single_value("Selling Settings", "allow_multiple_items", 0)

	for uom in ("Hour", "Nos"):
		if not frappe.db.exists("UOM", uom):
			frappe.get_doc({"doctype": "UOM", "uom_name": uom}).insert()
	frappe.db.set_value("UOM", "Hour", "must_be_whole_number", 0)

	item_group = frappe.db.get_value("Item Group", {"is_group": 0})
	for code, uom, preis in (
		("ZP-FAHRZEIT", "Hour", 80),
		("ZP-MONTAGE", "Hour", 95),
		("ZP-KM", "Nos", 0.5),
		("ZP-ADAPTER", "Nos", 15),
		("ZP-OHNEPREIS", "Nos", 0),
	):
		if not frappe.db.exists("Item", code):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": code,
					"item_name": code,
					"item_group": item_group,
					"stock_uom": uom,
					"is_stock_item": 0,
					"is_sales_item": 1,
				}
			).insert()
		if preis and not frappe.db.exists("Item Price", {"item_code": code, "price_list": "Standard Selling"}):
			frappe.get_doc(
				{"doctype": "Item Price", "item_code": code, "price_list": "Standard Selling", "price_list_rate": preis}
			).insert()

	for name, rate, item in ((FAHRZEIT, 60, "ZP-FAHRZEIT"), (MONTAGE, 90, "ZP-MONTAGE")):
		if not frappe.db.exists("Activity Type", name):
			frappe.get_doc(
				{"doctype": "Activity Type", "activity_type": name, "billing_rate": rate, "custom_dienstleistungsartikel": item}
			).insert()

	customer_group = frappe.db.get_value("Customer Group", {"is_group": 0})
	territory = frappe.db.get_value("Territory", {"is_group": 0})
	for kunde in (KUNDE_A, KUNDE_B):
		if not frappe.db.exists("Customer", kunde):
			frappe.get_doc(
				{"doctype": "Customer", "customer_name": kunde, "customer_group": customer_group, "territory": territory}
			).insert()

	for mail, rolle in ((TECH, "Employee"), (BUCHHALTUNG, "Accounts User")):
		if not frappe.db.exists("User", mail):
			user = frappe.get_doc(
				{"doctype": "User", "email": mail, "first_name": mail.split("@")[0], "send_welcome_email": 0}
			)
			user.insert()
			user.add_roles(rolle)

	employee = frappe.db.get_value("Employee", {"user_id": TECH})
	if not employee:
		employee = (
			frappe.get_doc(
				{
					"doctype": "Employee",
					"first_name": "ZP Tech",
					"gender": frappe.db.get_value("Gender", {}) or "Male",
					"date_of_birth": "1990-01-01",
					"date_of_joining": "2020-01-01",
					"company": company,
					"user_id": TECH,
					"status": "Active",
				}
			)
			.insert()
			.name
		)
	return frappe._dict(company=company, employee=employee)


def make_sales_order(company, customer=KUNDE_A, submit=True):
	so = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"customer": customer,
			"company": company,
			"transaction_date": nowdate(),
			"delivery_date": add_days(nowdate(), 7),
			"items": [{"item_code": "ZP-ADAPTER", "qty": 1}],
		}
	).insert()
	if submit:
		so.submit()
	return so


def sales_order_rows(name):
	return frappe.get_all(
		"Sales Order Item",
		filters={"parent": name},
		fields=["name", "item_code", "qty", "rate", "description"],
		order_by="idx",
	)


@contextmanager
def expect_error(testcase, exc=frappe.ValidationError):
	"""Wie assertRaises, setzt aber die Datenbank auf den Stand davor zurueck -
	ein fehlgeschlagenes Buchen/Stornieren hat den docstatus sonst schon
	geschrieben (im echten Request rollt Frappe den ganzen Request zurueck)."""
	frappe.db.savepoint("zp_expect_error")
	try:
		with testcase.assertRaises(exc) as ctx:
			yield ctx
	finally:
		frappe.db.rollback(save_point="zp_expect_error")
		frappe.clear_messages()
