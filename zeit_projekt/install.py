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
			"description": "Artikel, der bei der Rechnungsstellung fuer diese Aktivitaetsart verwendet wird",
			"module": MODULE,
		},
		{
			"fieldname": "custom_rechnungstext",
			"label": "Bezeichnung für Rechnung",
			"fieldtype": "Data",
			"insert_after": "custom_dienstleistungsartikel",
			"description": "Optional: Text, der in der Rechnungsposition statt der Aktivitaetsart erscheint",
			"module": MODULE,
		},
	],
	"Sales Order": [
		{
			"fieldname": "custom_projekt_erstellen",
			"label": "Projekt für diesen Auftrag erstellen",
			"fieldtype": "Check",
			"insert_after": "customer_name",
			"description": "Das Projekt wird angelegt und verknuepft, sobald der Auftrag bestaetigt (gebucht) wird",
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


def after_install():
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
	_deaktiviere_alte_client_scripts()
	frappe.db.commit()
	click.secho("Zeit & Projekt: Felder angelegt.", fg="green")


def before_uninstall():
	geloescht = 0
	for doctype, felder in CUSTOM_FIELDS.items():
		for feld in felder:
			name = f"{doctype}-{feld['fieldname']}"
			if frappe.db.exists("Custom Field", name):
				frappe.delete_doc("Custom Field", name, ignore_missing=True, force=True)
				geloescht += 1

	frappe.db.commit()
	click.secho(
		f"Zeit & Projekt: {geloescht} Felder entfernt. "
		"Hinweis: Die darin gepflegten Werte (z. B. die Artikelzuordnung je "
		"Aktivitaetsart) sind damit geloescht. Bereits angelegte Projekte und "
		"gebuchte Rechnungen bleiben unveraendert bestehen.",
		fg="yellow",
	)


def _deaktiviere_alte_client_scripts():
	for name in ALTE_CLIENT_SCRIPTS:
		if frappe.db.exists("Client Script", name):
			frappe.db.set_value("Client Script", name, "enabled", 0)
			click.secho(
				f"Zeit & Projekt: Client Script '{name}' deaktiviert "
				"(Funktion kommt jetzt aus der App). Loeschen kannst du es selbst.",
				fg="yellow",
			)
