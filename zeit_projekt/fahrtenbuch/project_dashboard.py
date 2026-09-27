from frappe import _


def get_data(data):
	"""Ergaenzt die "Verknuepfungen"-Liste des Projekt-Formulars um Fahrt.

	Additiv ueber override_doctype_dashboards (siehe hooks.py) - site_visit
	haengt sich hier bereits genauso ein, Frappe verkettet alle registrierten
	Hooks nacheinander, keine Kollision. fieldname bleibt "project" (Standard
	aus erpnext.projects.doctype.project.project_dashboard), das reicht fuer
	die automatische Vorbelegung beim Anlegen ueber die "+"-Verknuepfung, da
	das Feld auf Fahrt ebenfalls "project" heisst."""
	data.setdefault("transactions", []).append({"label": _("Fahrten"), "items": ["Fahrt"]})
	return data
