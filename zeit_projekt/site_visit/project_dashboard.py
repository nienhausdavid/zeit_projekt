from frappe import _


def get_data(data):
	"""Ergaenzt die "Verknuepfungen"-Liste des Projekt-Formulars um Site Visit.

	Additiv ueber override_doctype_dashboards (siehe hooks.py) - data enthaelt
	bereits das Ergebnis von erpnext.projects.doctype.project.project_dashboard.
	get_data(). fieldname bleibt "project", das reicht fuer die automatische
	Vorbelegung beim Anlegen ueber die "+"-Verknuepfung, da das Feld auf Site
	Visit ebenfalls "project" heisst.
	"""
	data.setdefault("transactions", []).append(
		{"label": _("Site Visits"), "items": ["Site Visit"]}
	)
	return data
