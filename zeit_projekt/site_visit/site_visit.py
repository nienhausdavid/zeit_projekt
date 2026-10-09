import erpnext
import frappe
from frappe import _
from frappe.utils import cint, get_datetime, getdate, nowdate

from zeit_projekt.zeit_projekt.billing import (
	add_rows_to_sales_order,
	as_administrator,
	cancel_timesheet,
	check_sales_order,
	create_timesheet,
	ensure_timesheet_not_invoiced,
	price_rows,
	remove_rows_from_sales_order,
)


def before_submit(doc, method=None):
	"""Legt ein Timesheet an, bucht es und verknuepft es - im selben Request
	wie das Buchen des Site Visit selbst. Serverseitig, damit kein zweiter
	Request und damit kein Zeitfenster fuer "has been modified after you have
	opened it" entsteht (gleiche Begruendung wie
	zeit_projekt.zeit_projekt.sales_order.before_submit).

	customer/activity_type/sales_order/to_time sind absichtlich nicht reqd im
	Feld - ein Entwurf mit nur laufendem Timer waere sonst nicht speicherbar.
	Deshalb hier explizit vor dem Buchen geprueft."""
	if doc.timesheet:
		return

	if not doc.customer:
		frappe.throw(_("Bitte vor dem Buchen einen Kunden auswählen."))
	if not doc.activity_type:
		frappe.throw(_("Bitte vor dem Buchen eine Aktivitätsart auswählen."))
	if not doc.sales_order:
		frappe.throw(_("Bitte vor dem Buchen einen Auftrag auswählen."))
	if not doc.to_time:
		frappe.throw(_("Bitte vor dem Buchen eine Endzeit eintragen."))

	if get_datetime(doc.to_time) <= get_datetime(doc.from_time):
		frappe.throw(_("Das Ende muss nach dem Beginn liegen."))
	abschnitte = doc.get_work_segments()
	if not abschnitte:
		frappe.throw(_("Nach Abzug der Pausen bleibt keine Arbeitszeit übrig."))

	check_sales_order(doc.sales_order, doc.customer)

	doc.timesheet = create_timesheet(
		doc,
		doc.activity_type,
		doc.from_time,
		doc.to_time,
		customer=doc.customer,
		project=doc.project,
		company=doc.company,
		description=doc.description or doc.name,
		segments=abschnitte,
		sales_order=doc.sales_order,
	)
	frappe.msgprint(
		_("Zeitblatt {0} wurde angelegt und gebucht.").format(f"<b>{doc.timesheet}</b>"),
		indicator="green",
		alert=True,
	)

	_sync_extra_items_to_sales_order(doc)


def _sync_extra_items_to_sales_order(doc):
	"""Noch nicht uebernommene Zusatzartikel in den verknuepften Auftrag
	uebernehmen. Zeilen mit added_to_order=1 stecken bereits im Auftrag (bei
	einer Berichtigung oder aus frueheren Versionen der App). Jede Zeile merkt
	sich die erzeugte Auftragsposition (sales_order_item) fuer das Stornieren."""
	pending = [row for row in doc.extra_items if not row.added_to_order]
	if not pending:
		return

	rows = [
		{"item_code": row.item_code, "qty": row.qty, "uom": row.uom, "description": _item_description(doc, row)}
		for row in pending
	]
	new_items = add_rows_to_sales_order(doc.sales_order, doc.customer, rows, source=doc)

	for row, so_item in zip(pending, new_items, strict=True):
		row.added_to_order = 1
		row.sales_order_item = so_item


def _item_description(doc, row):
	"""Eindeutig je Zeile: ERPNext lehnt sonst gleiche Artikel mit gleicher
	Beschreibung im selben Auftrag ab, solange Mehrfachartikel in den
	Verkaufseinstellungen aus sind."""
	item_name = row.item_name or frappe.db.get_value("Item", row.item_code, "item_name") or row.item_code
	return _("{0} (Kundeneinsatz {1}, Zeile {2})").format(item_name, doc.name, row.idx)


@frappe.whitelist()
def get_sales_order_form():
	"""Beschriftung und Pflicht-Status des Feldes, in das die Kommissionsnummer
	geschrieben wird (po_no, je nach Site z. B. "Customer Reference") - fuer
	den "Neuer Auftrag"-Dialog. Techniker duerfen die Metadaten des Auftrags
	selbst nicht lesen."""
	_check_create_access()
	field = frappe.get_meta("Sales Order").get_field("po_no")
	return {"po_no_label": _(field.label), "po_no_reqd": cint(field.reqd)}


@frappe.whitelist()
def create_sales_order(customer, activity_type, po_no=None, project=None, company=None, date=None, site_visit=None):
	"""Fuer den "Neuer Auftrag"-Dialog: legt einen Auftrag (Entwurf) an - auch
	aus einem noch nicht gespeicherten Kundeneinsatz, denn der Auftrag ist dort
	Pflicht. Buchen bleibt Sache des Vertriebs.

	ERPNext verlangt mindestens eine Position. Die Einsatzzeit selbst wird aber
	ueber das Zeitblatt abgerechnet (Zeitimport der Ausgangsrechnung) - die
	Position mit dem Dienstleistungsartikel der Aktivitaetsart steht deshalb mit
	Preis 0 im Auftrag, nur als Hinweis. Zusatzartikel kommen beim Buchen des
	Einsatzes dazu (billing.add_rows_to_sales_order).

	Die Kommissionsnummer landet in po_no."""
	_check_create_access()
	if not frappe.db.exists("Customer", {"name": customer, "disabled": 0}):
		frappe.throw(_("Kunde {0} existiert nicht oder ist gesperrt.").format(frappe.bold(customer)))
	if project:
		projekt_kunde = frappe.db.get_value("Project", project, "customer")
		if projekt_kunde and projekt_kunde != customer:
			frappe.throw(
				_("Projekt {0} gehört zum Kunden {1}, nicht zu {2}.").format(
					frappe.bold(project), frappe.bold(projekt_kunde), frappe.bold(customer)
				)
			)
	service_item = frappe.db.get_value("Activity Type", activity_type, "custom_dienstleistungsartikel")
	if not service_item:
		frappe.throw(
			_(
				"Aktivitätsart {0} hat keinen Dienstleistungsartikel. Er wird als Position des neuen "
				"Auftrags gebraucht - bitte in der Aktivitätsart eintragen."
			).format(frappe.bold(activity_type))
		)

	quelle = None
	if site_visit and frappe.db.exists("Site Visit", site_visit):
		quelle = frappe.get_doc("Site Visit", site_visit)
		quelle.check_permission("write")

	heute = getdate(nowdate())
	nutzer = frappe.utils.get_fullname(frappe.session.user)
	with as_administrator():
		so = frappe.new_doc("Sales Order")
		so.update(
			{
				"customer": customer,
				"company": company or erpnext.get_default_company(),
				"project": project or None,
				"po_no": (po_no or "").strip() or None,
				# Als Text (ISO), nicht als date: ERPNext reicht transaction_date beim
				# Zahlungsplan an get_payment_term_details weiter, und das prueft
				# seit Frappe 16.51 in Web-Requests str | None. Mit einem date
				# scheiterte der Auftrag fuer jeden Kunden mit Zahlungsbedingung
				# (FrappeTypeError), in der Konsole blieb das unbemerkt.
				"transaction_date": str(heute),
				"delivery_date": str(max(getdate(date or heute), heute)),
			}
		)
		zeile = price_rows(
			so,
			[{"item_code": service_item, "qty": 1, "description": _("Einsatzzeit - Abrechnung nach Zeiterfassung")}],
			throw=False,
		)[0]
		zeile.update({"rate": 0, "price_list_rate": 0, "discount_percentage": 0, "margin_rate_or_amount": 0})
		so.append("items", dict(zeile, custom_site_visit=quelle.name if quelle else None))
		so.insert()
		herkunft = (
			frappe.utils.get_link_to_form(quelle.doctype, quelle.name) if quelle else _("einem neuen Kundeneinsatz")
		)
		so.add_comment("Comment", _("Angelegt aus {0} von {1}.").format(herkunft, nutzer))

	return so.name


def _check_create_access():
	if not (frappe.has_permission("Site Visit", "create") or frappe.has_permission("Site Visit", "write")):
		frappe.throw(_("Keine Berechtigung."), frappe.PermissionError)


def on_cancel(doc, method=None):
	"""Nimmt die beim Buchen in den Auftrag uebernommenen Zusatzartikel wieder
	heraus und storniert das verknuepfte Timesheet, sofern es noch nicht
	fakturiert wurde. Zeilen ohne sales_order_item (aus frueheren Versionen
	der App schon vor dem Buchen im Auftrag) bleiben dort."""
	ensure_timesheet_not_invoiced(doc.timesheet)

	synced = [row for row in doc.extra_items if row.sales_order_item]
	remove_rows_from_sales_order(doc.sales_order, [row.sales_order_item for row in synced])
	for row in synced:
		# Damit ein berichtigter Site Visit diese Zeilen beim erneuten Buchen
		# wieder uebernimmt (added_to_order wird beim Berichtigen mitkopiert).
		frappe.db.set_value("Site Visit Item", row.name, {"added_to_order": 0, "sales_order_item": None})

	cancel_timesheet(doc.timesheet)
