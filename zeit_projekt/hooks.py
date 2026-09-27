app_name = "zeit_projekt"
app_title = "Zeit & Projekt"
app_publisher = "Dein Name"
app_description = "Zeiterfassung als Einzelpositionen, automatische Projektanlage aus dem Auftrag und Fahrtenbuch"
app_email = "info@example.com"
app_license = "mit"

required_apps = ["frappe/erpnext"]

# ---------------------------------------------------------------------------
# Formular-Skripte
#
# Statt Client-Script-Datensaetzen in der Datenbank werden die Skripte als
# echte Dateien ausgeliefert. Vorteile: sie verschwinden restlos mit der App,
# sind versionierbar und unterliegen nicht dem Client-Script-Cache im Browser.
# ---------------------------------------------------------------------------
doctype_js = {
	"Sales Invoice": "public/js/sales_invoice.js",
	"Sales Order": "public/js/sales_order.js",
	"Fahrt": "public/js/fahrtenbuch.js",
	"Fahrtenbuch Einstellungen": "public/js/fahrtenbuch_einstellungen.js",
	"Project": "public/js/project.js",
}

# ---------------------------------------------------------------------------
# Projektanlage aus dem Auftrag / Abrechnung aus der Fahrt
#
# Laeuft jeweils serverseitig, innerhalb derselben Transaktion wie das Buchen
# selbst (kein separater Request mehr davor). Verhindert den "has been
# modified after you have opened it"-Konflikt, der bei einem eigenen
# frappe.call vor dem Buchen-Request auftreten konnte, und greift auch bei
# API-Zugriffen und Massenbuchungen.
# ---------------------------------------------------------------------------
doc_events = {
	"Sales Order": {
		"before_submit": "zeit_projekt.zeit_projekt.sales_order.before_submit",
	},
	"Fahrt": {
		"before_submit": "zeit_projekt.fahrtenbuch.fahrtenbuch.before_submit",
	},
}

# ---------------------------------------------------------------------------
# Fahrt in der Verknuepfungen-Liste des Projekt-Formulars
#
# fieldname bleibt "project" (Standard aus
# erpnext.projects.doctype.project.project_dashboard), das reicht fuer die
# automatische Vorbelegung beim Anlegen ueber die "+"-Verknuepfung, da das
# Feld auf Fahrt ebenfalls "project" heisst.
# ---------------------------------------------------------------------------
override_doctype_dashboards = {
	"Project": "zeit_projekt.fahrtenbuch.project_dashboard.get_data",
}

# ---------------------------------------------------------------------------
# Fahrtenbuch im Apps-Uebersicht (/apps) - eigene Kachel mit Sprung in die
# Fahrt-Liste, wie in der urspruenglichen Fahrtenbuch-App.
# ---------------------------------------------------------------------------
add_to_apps_screen = [
	{
		"name": "fahrtenbuch",
		"logo": "/assets/zeit_projekt/images/fahrtenbuch-logo.svg",
		"title": "Fahrtenbuch",
		"route": "/app/fahrt",
		"has_permission": "zeit_projekt.fahrtenbuch.fahrtenbuch.check_app_permission",
	}
]

# ---------------------------------------------------------------------------
# Installation / Deinstallation
#
# after_install legt die Custom Fields an, before_uninstall entfernt sie
# wieder. Damit ist der Zustand vor der Installation vollstaendig
# wiederhergestellt (Nutzdaten ausgenommen, siehe README).
# ---------------------------------------------------------------------------
after_install = "zeit_projekt.install.after_install"
before_uninstall = "zeit_projekt.install.before_uninstall"
