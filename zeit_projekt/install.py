import click
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

MODULE = "Zeit Projekt"

# ---------------------------------------------------------------------------
# Custom Fields, die diese App mitbringt.
#
# "module" ist wichtig: Damit gehoeren die Felder der App und wuerden selbst
# dann beim Deinstallieren geloescht, wenn before_uninstall nicht liefe.
# ---------------------------------------------------------------------------
CUSTOM_FIELDS = {
	"Activity Type": [
		{
			"fieldname": "custom_dienstleistungsartikel",
			"label": "Dienstleistungsartikel",
			"fieldtype": "Link",
			"options": "Item",
			"insert_after": "billing_rate",
			"description": "Artikel, der bei der Rechnungsstellung für diese Aktivitätsart verwendet wird",
			"module": MODULE,
		},
		{
			"fieldname": "custom_rechnungstext",
			"label": "Bezeichnung für Rechnung",
			"fieldtype": "Data",
			"insert_after": "custom_dienstleistungsartikel",
			"description": "Optional: Text, der in der Rechnungsposition statt der Aktivitätsart erscheint",
			"module": MODULE,
		},
	],
	"Sales Order": [
		{
			"fieldname": "custom_projekt_erstellen",
			"label": "Projekt für diesen Auftrag erstellen",
			"fieldtype": "Check",
			"insert_after": "customer_name",
			"description": "Das Projekt wird angelegt und verknüpft, sobald der Auftrag bestätigt (gebucht) wird",
			"module": MODULE,
		},
	],
	"Sales Order Item": [
		{
			"fieldname": "custom_site_visit",
			"label": "Kundeneinsatz",
			"fieldtype": "Link",
			"options": "Site Visit",
			"insert_after": "prevdoc_docname",
			"read_only": 1,
			"no_copy": 1,
			"description": "Kundeneinsatz, aus dem diese Position als Zusatzartikel übernommen wurde",
			"module": MODULE,
		},
	],
	"Sales Invoice Item": [
		{
			"fieldname": "custom_fahrt",
			"label": "Fahrt (Kilometer)",
			"fieldtype": "Link",
			"options": "Fahrt",
			"insert_after": "sales_order",
			"read_only": 1,
			"no_copy": 1,
			"description": "Vom Zeitimport gesetzt - die Kilometer dieser Fahrt gelten mit dem Buchen der Rechnung als abgerechnet",
			"module": MODULE,
		},
	],
}

# Client Scripts aus der manuellen Einrichtung. Werden bei der Installation
# deaktiviert, damit die Funktionen nicht doppelt laufen (zwei Knoepfe).
ALTE_CLIENT_SCRIPTS = [
	"Zeiterfassung als Einzelpositionen",
	"Auftrag: Projekt erstellen",
	"Auftrag: Kommission und Projekt",
]


SITE_VISIT_DOCUMENT_TYPE = "Site Visit"
SITE_VISIT_PRINT_FORMAT = "Site Visit Report"

# Die frueheren Einzel-Apps bringen dieselben Module und Doctypes mit. Parallel
# installiert gewinnt nur eine der beiden Definitionen, die Hooks laufen aber
# doppelt (z. B. Fahrzeit zweimal im Auftrag).
KONFLIKT_APPS = ("fahrtenbuch", "site_visit")


def before_install():
	installiert = [app for app in KONFLIKT_APPS if app in frappe.get_installed_apps()]
	if installiert:
		frappe.throw(
			"Zeit & Projekt enthält die Module der Apps {0} bereits. Bitte diese zuerst "
			"entfernen. Achtung: uninstall-app löscht dabei deren Tabellen samt Daten."
			.format(", ".join(installiert))
		)


def before_app_install(app_name):
	if app_name in KONFLIKT_APPS:
		frappe.throw(
			f"Die App {app_name} ist bereits vollständig in Zeit & Projekt enthalten "
			"und darf nicht zusätzlich installiert werden."
		)


def after_migrate():
	"""Neue oder geaenderte Custom Fields auch auf bereits installierten Sites
	anlegen - after_install laeuft nur einmal."""
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True, update=True)
	_desk_abgleichen()


def after_install():
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
	_deaktiviere_alte_client_scripts()
	_site_visit_pdf_on_submit_enable()
	_desk_abgleichen()
	click.secho("Zeit & Projekt: Felder angelegt.", fg="green")


def _desk_abgleichen():
	"""Desktop-Symbole und Seitenleisten exakt wie in desktop_icon/ und
	workspace_sidebar/ herstellen.

	Frappe importiert diese Dateien beim migrate nur, wenn der Datensatz fehlt
	oder aelter als die Datei ist (frappe/modules/import_file.py,
	import_file_by_path). Auf Sites mit einer frueheren Version der App
	existieren "Zeit & Projekt" und "Site Visits" aber schon - automatisch beim
	Installieren erzeugt und damit juenger als die Datei. Sie blieben dann
	unveraendert stehen (alter Link, kein Bezug zur App), nur das neue Symbol
	"Fahrtenbuch" entstuende. Deshalb jeden Datensatz, dessen Zeitstempel nicht
	dem der Datei entspricht, aus der Datei neu laden (force). Der alte
	Datensatz wird dabei "for_reload" geloescht, also ohne on_trash - die
	Dateien in der App bleiben auch im developer_mode unangetastet."""
	import os

	from frappe.modules.import_file import import_file_by_path, read_doc_from_file
	from frappe.utils import get_datetime

	geaendert = []
	for ordner in ("workspace_sidebar", "desktop_icon"):
		pfad = frappe.get_app_path("zeit_projekt", ordner)
		if not os.path.isdir(pfad):
			continue
		for datei in sorted(os.listdir(pfad)):
			if not datei.endswith(".json"):
				continue
			datei = os.path.join(pfad, datei)
			doc = read_doc_from_file(datei)
			if not frappe.db.table_exists(doc["doctype"]):
				continue
			in_db = frappe.db.get_value(doc["doctype"], doc["name"], "modified")
			if in_db and get_datetime(in_db) == get_datetime(doc["modified"]):
				continue
			import_file_by_path(datei, force=True, ignore_version=True)
			geaendert.append(doc["name"])

	if geaendert:
		from frappe.desk.doctype.desktop_icon.desktop_icon import clear_desktop_icons_cache

		frappe.cache.delete_key("desktop_icons")
		frappe.cache.delete_key("bootinfo")
		clear_desktop_icons_cache()
		click.secho(f"Zeit & Projekt: Desk abgeglichen ({', '.join(geaendert)}).", fg="green")


def before_uninstall():
	# Kein frappe.db.commit() hier: bench haengt diesen Hook in seine eigene
	# Transaktion um `uninstall-app` ein. Ein eigener commit() wuerde die
	# Loeschung sofort fest schreiben - auch bei `--dry-run`, das sich sonst
	# auf ein Rollback am Ende verlaesst (beobachtet am 12.09.2026: drei
	# Felder blieben nach einem Dry-Run tatsaechlich geloescht).
	geloescht = 0
	for doctype, felder in CUSTOM_FIELDS.items():
		for feld in felder:
			name = f"{doctype}-{feld['fieldname']}"
			if frappe.db.exists("Custom Field", name):
				frappe.delete_doc("Custom Field", name, ignore_missing=True, force=True)
				geloescht += 1

	click.secho(
		f"Zeit & Projekt: {geloescht} Felder entfernt. "
		"Hinweis: Die darin gepflegten Werte (z. B. die Artikelzuordnung je "
		"Aktivitaetsart) sind damit geloescht. Bereits angelegte Projekte und "
		"gebuchte Rechnungen bleiben unveraendert bestehen.",
		fg="yellow",
	)
	_site_visit_pdf_on_submit_disable()
	_entferne_desktop_symbole()


def _deaktiviere_alte_client_scripts():
	for name in ALTE_CLIENT_SCRIPTS:
		if frappe.db.exists("Client Script", name):
			frappe.db.set_value("Client Script", name, "enabled", 0)
			click.secho(
				f"Zeit & Projekt: Client Script '{name}' deaktiviert "
				"(Funktion kommt jetzt aus der App). Loeschen kannst du es selbst.",
				fg="yellow",
			)


def _entferne_desktop_symbole():
	"""Frappe legt beim Installieren ein App-Symbol mit dem Titel "Zeit &
	Projekt" an, sucht es beim Deinstallieren aber unter dem App-Namen
	"zeit_projekt" (frappe/utils/install.py, delete_desktop_icon_and_sidebar) -
	es bliebe als toter Link auf dem Desk stehen. Untergeordnete Symbole
	zuerst, sie verweisen per parent_icon auf das App-Symbol."""
	if not frappe.db.table_exists("Desktop Icon"):
		return
	app_title = frappe.get_hooks("app_title", app_name="zeit_projekt")[0]
	kinder = frappe.get_all("Desktop Icon", filters={"parent_icon": app_title}, pluck="name")
	eigene = frappe.get_all(
		"Desktop Icon",
		or_filters=[["app", "=", "zeit_projekt"], ["name", "=", app_title]],
		pluck="name",
	)
	# ignore_on_trash: on_trash von Desktop Icon und Workspace Sidebar loescht
	# im developer_mode die zugehoerige JSON-Datei in der App - beim
	# Deinstallieren auf einem Entwicklungssystem waeren desktop_icon/ und
	# workspace_sidebar/ danach leer.
	for name in kinder + [n for n in eigene if n not in kinder]:
		frappe.delete_doc("Desktop Icon", name, ignore_permissions=True, force=True, ignore_on_trash=True)
	if kinder or eigene:
		click.secho("Zeit & Projekt: Desktop-Symbole entfernt.", fg="yellow")

	# Frappe entfernt die Seitenleisten zwar selbst (after_app_uninstall,
	# frappe/utils/install.py, delete_desktop_icon_and_sidebar), schreibt das
	# aber nur bei --dry-run fest - sonst blieben sie stehen.
	seitenleisten = frappe.get_all("Workspace Sidebar", filters={"app": "zeit_projekt"}, pluck="name")
	for name in seitenleisten:
		frappe.delete_doc(
			"Workspace Sidebar", name, ignore_permissions=True, force=True, ignore_on_trash=True
		)
	if kinder or eigene or seitenleisten:
		frappe.cache.delete_key("desktop_icons")
		frappe.cache.delete_key("bootinfo")


def _site_visit_pdf_on_submit_enable():
	"""Traegt Site Visit automatisch in PDF on Submit Settings ein, damit
	beim Buchen automatisch ein PDF am Einsatz haengt - nur falls die
	optionale App pdf_on_submit ueberhaupt installiert ist (siehe
	README.md "Automatische PDF-Erzeugung")."""
	if "pdf_on_submit" not in frappe.get_installed_apps():
		return

	settings = frappe.get_single("PDF on Submit Settings")
	if any(row.document_type == SITE_VISIT_DOCUMENT_TYPE for row in settings.enabled_for):
		return

	settings.append(
		"enabled_for",
		{"document_type": SITE_VISIT_DOCUMENT_TYPE, "print_format": SITE_VISIT_PRINT_FORMAT},
	)
	settings.save(ignore_permissions=True)
	click.secho(
		f"Zeit & Projekt: Site Visit in PDF on Submit Settings eingetragen "
		f"({SITE_VISIT_DOCUMENT_TYPE} / {SITE_VISIT_PRINT_FORMAT}).",
		fg="green",
	)


def _site_visit_pdf_on_submit_disable():
	if "pdf_on_submit" not in frappe.get_installed_apps():
		return
	if not frappe.db.exists("DocType", "PDF on Submit Settings"):
		return

	settings = frappe.get_single("PDF on Submit Settings")
	remaining = [row for row in settings.enabled_for if row.document_type != SITE_VISIT_DOCUMENT_TYPE]
	if len(remaining) == len(settings.enabled_for):
		return

	settings.enabled_for = []
	for row in remaining:
		settings.append("enabled_for", row)
	settings.save(ignore_permissions=True)
	click.secho("Zeit & Projekt: Eintrag Site Visit in PDF on Submit Settings entfernt.", fg="yellow")
