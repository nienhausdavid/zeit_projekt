import frappe
from frappe.utils import cint


def chrome_enabled():
	return cint(frappe.db.get_single_value("Zeit Projekt Einstellungen", "force_chrome_pdf"))


def force_chrome_pdf():
	"""before_request: erzwingt pdf_generator=chrome fuer PDF-Download und
	Druckansicht - nur wenn in "Zeit Projekt Einstellungen" aktiviert.

	Hintergrund: frappe.utils.print_format.download_pdf faellt ohne
	expliziten Parameter hart auf wkhtmltopdf zurueck und ignoriert das
	pdf_generator-Feld des Print Format. Auf Servern, auf denen wkhtmltopdf
	grundsaetzlich scheitert (z. B. "ProtocolUnknownError" bei der relativen
	print.bundle.css-URL), ist das der einzige Weg ohne die App print_designer.
	Wirkt fuer alle Doctypes der Site, deshalb abschaltbar und standardmaessig
	aus."""
	request = getattr(frappe.local, "request", None)
	if not request or request.path not in (
		"/api/method/frappe.utils.print_format.download_pdf",
		"/printview",
	):
		return
	if chrome_enabled():
		frappe.local.form_dict.pdf_generator = "chrome"
