def get_data(data):
	"""Verkettet die "Verknuepfungen"-Ergaenzungen von Fahrtenbuch und Site
	Visit fuer das Projekt-Formular.

	Frappes override_doctype_dashboards-Hook nimmt pro Doctype nur einen
	einzigen dotted path entgegen (kein additiver Mechanismus wie bei
	doctype_js/doc_events) - als getrennte Apps haben fahrtenbuch und
	site_visit sich deshalb jeweils selbst registriert und Frappe hat beide
	ueber die App-Reihenfolge nacheinander verkettet. Innerhalb einer einzigen
	App (jetzt zeit_projekt) gibt es diese App-Verkettung nicht mehr, deshalb
	hier explizit beide Erweiterungen nacheinander anwenden."""
	from zeit_projekt.fahrtenbuch.project_dashboard import get_data as fahrtenbuch_get_data
	from zeit_projekt.site_visit.project_dashboard import get_data as site_visit_get_data

	data = fahrtenbuch_get_data(data)
	data = site_visit_get_data(data)
	return data
