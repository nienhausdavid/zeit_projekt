import frappe


def projektname(doc):
	ref = (doc.buyer_reference or "").strip()
	basis = ref or (doc.customer_name or doc.customer or "")
	return f"{basis} - {doc.name}"


def before_submit(doc, method=None):
	"""Legt bei Bedarf ein Projekt an und verknuepft es - im selben Request
	wie das Buchen selbst.

	Laeuft serverseitig innerhalb derselben Transaktion wie das Setzen von
	docstatus=1. Es gibt dadurch keinen separaten Netzwerk-Request und somit
	kein Zeitfenster, in dem der Auftrag zwischen Laden und Buchen von einem
	anderen Request veraendert werden koennte ("has been modified after you
	have opened it"). Frueher lief die Projektanlage per JS in before_submit
	als eigener frappe.call vor dem eigentlichen Buchen-Request - genau das
	Zeitfenster dazwischen verursachte den Konflikt bei einem doppelten Klick
	auf Buchen.
	"""
	if not doc.get("custom_projekt_erstellen") or doc.project:
		return

	projekt = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": projektname(doc),
			"project_type": "External",
			"status": "Open",
			"is_active": "Yes",
			"company": doc.company,
			"customer": doc.customer,
			"sales_order": doc.name,
			"expected_start_date": doc.transaction_date,
			"expected_end_date": doc.delivery_date or None,
		}
	).insert()

	doc.project = projekt.name
	frappe.msgprint(
		f"Projekt <b>{projekt.name}</b> ({projekt.project_name}) angelegt und verknuepft.",
		indicator="green",
		alert=True,
	)
