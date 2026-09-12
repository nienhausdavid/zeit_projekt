app_name = "zeit_projekt"
app_title = "Zeit & Projekt"
app_publisher = "Dein Name"
app_description = "Zeiterfassung als Einzelpositionen in der Ausgangsrechnung und automatische Projektanlage aus dem Auftrag"
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
}

# ---------------------------------------------------------------------------
# Projektanlage aus dem Auftrag
#
# Laeuft serverseitig, innerhalb derselben Transaktion wie das Buchen selbst
# (kein separater Request mehr davor). Verhindert den "has been modified
# after you have opened it"-Konflikt, der bei einem eigenen frappe.call vor
# dem Buchen-Request auftreten konnte, und greift auch bei API-Zugriffen und
# Massenbuchungen.
# ---------------------------------------------------------------------------
doc_events = {
	"Sales Order": {
		"before_submit": "zeit_projekt.zeit_projekt.sales_order.before_submit",
	},
}

# ---------------------------------------------------------------------------
# Installation / Deinstallation
#
# after_install legt die Custom Fields an, before_uninstall entfernt sie
# wieder. Damit ist der Zustand vor der Installation vollstaendig
# wiederhergestellt (Nutzdaten ausgenommen, siehe README).
# ---------------------------------------------------------------------------
after_install = "zeit_projekt.install.after_install"
before_uninstall = "zeit_projekt.install.before_uninstall"
