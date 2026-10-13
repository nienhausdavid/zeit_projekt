app_name = "zeit_projekt"
app_title = "Zeit & Projekt"
app_publisher = "Dein Name"
app_description = "Zeiterfassung als Einzelpositionen, automatische Projektanlage aus dem Auftrag, Fahrtenbuch und Site Visit"
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
	"Site Visit": "public/js/site_visit.js",
}

# ---------------------------------------------------------------------------
# Projektanlage aus dem Auftrag / Abrechnung aus der Fahrt / Zeitblatt aus
# dem Site Visit
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
		"on_submit": "zeit_projekt.zeit_projekt.billing_status.on_sales_order_submit",
	},
	# Abrechnungsstand des Auftrags inkl. Zeitbuchungen (billing_status.py)
	"Timesheet": {
		"on_submit": "zeit_projekt.zeit_projekt.billing_status.on_timesheet_change",
		"on_cancel": "zeit_projekt.zeit_projekt.billing_status.on_timesheet_change",
	},
	"Fahrt": {
		"before_submit": "zeit_projekt.fahrtenbuch.fahrtenbuch.before_submit",
		"on_cancel": "zeit_projekt.fahrtenbuch.fahrtenbuch.on_cancel",
	},
	"Site Visit": {
		"before_submit": "zeit_projekt.site_visit.site_visit.before_submit",
		"on_cancel": "zeit_projekt.site_visit.site_visit.on_cancel",
	},
	# Fahrt-Kilometer aus dem Zeitimport: nur einmal abrechenbar; danach
	# Abrechnungsstand der betroffenen Auftraege
	"Sales Invoice": {
		"validate": "zeit_projekt.zeit_projekt.sales_invoice.validate",
		"on_submit": "zeit_projekt.zeit_projekt.sales_invoice.on_submit",
		"on_cancel": "zeit_projekt.zeit_projekt.sales_invoice.on_cancel",
	},
}

# ---------------------------------------------------------------------------
# Fahrt/Site Visit in der Verknuepfungen-Liste des Projekt-Formulars
#
# Frappe ruft alle Eintraege der Liste nacheinander auf und reicht das
# Ergebnis weiter (frappe/model/meta.py, get_dashboard_data). fieldname
# bleibt jeweils "project" (Standard aus
# erpnext.projects.doctype.project.project_dashboard), das reicht fuer die
# automatische Vorbelegung beim Anlegen ueber die "+"-Verknuepfung.
# ---------------------------------------------------------------------------
override_doctype_dashboards = {
	"Project": [
		"zeit_projekt.fahrtenbuch.project_dashboard.get_data",
		"zeit_projekt.site_visit.project_dashboard.get_data",
	],
}

# ---------------------------------------------------------------------------
# PDF-Generator auf "chrome" erzwingen - nur wenn in "Zeit Projekt
# Einstellungen" aktiviert (siehe zeit_projekt/zeit_projekt/pdf.py).
# ---------------------------------------------------------------------------
before_request = ["zeit_projekt.zeit_projekt.pdf.force_chrome_pdf"]

# ---------------------------------------------------------------------------
# Desk: eine Kachel auf /apps und ein App-Symbol "Zeit & Projekt" mit den
# Seitenleisten "Fahrtenbuch" und "Site Visits" darunter (mitgeliefert unter
# desktop_icon/, <modul>/sidebar/ (Doctype "Sidebar", Frappe >= 16.51) und
# workspace_sidebar/ (aeltere Staende); Frappe synchronisiert sie bei
# install/migrate, install.py gleicht Abweichungen aus).
# ---------------------------------------------------------------------------
app_logo_url = "/assets/zeit_projekt/images/zeit_projekt-logo.svg"

add_to_apps_screen = [
	{
		"name": "zeit_projekt",
		"logo": app_logo_url,
		"title": app_title,
		"route": "/desk/fahrt?sidebar=Fahrtenbuch",
		"has_permission": "zeit_projekt.zeit_projekt.desk.check_app_permission",
	},
]

# ---------------------------------------------------------------------------
# Installation / Deinstallation
#
# after_install legt die Custom Fields an, before_uninstall entfernt sie
# wieder. Damit ist der Zustand vor der Installation vollstaendig
# wiederhergestellt (Nutzdaten ausgenommen, siehe README).
# ---------------------------------------------------------------------------
before_install = "zeit_projekt.install.before_install"
after_install = "zeit_projekt.install.after_install"
after_migrate = "zeit_projekt.install.after_migrate"
before_uninstall = "zeit_projekt.install.before_uninstall"

# Wird von Frappe bei der Installation jeder anderen App aufgerufen - verhindert,
# dass fahrtenbuch/site_visit nachtraeglich parallel installiert werden.
before_app_install = "zeit_projekt.install.before_app_install"
