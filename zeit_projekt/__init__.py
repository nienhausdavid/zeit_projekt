__version__ = "0.0.1"


def _patch_pdf_on_submit_for_chrome():
	"""pdf_on_submit.attach_pdf.get_pdf_data() ruft frappe.utils.pdf.get_pdf()
	direkt auf - den rohen wkhtmltopdf-Pfad, ohne den pdf_generator-Mechanismus
	von frappe.get_print(). Die automatische PDF-Anlage beim Buchen deckt
	force_chrome_pdf (zeit_projekt/zeit_projekt/pdf.py) nicht ab, weil sie
	ohne HTTP-Request (ggf. im Queue-Worker) laeuft.

	Der Chrome-Weg greift nur, wenn "PDFs immer mit Chrome erzeugen" in
	"Zeit Projekt Einstellungen" aktiv ist - sonst bleibt pdf_on_submit
	unveraendert. Steht bewusst hier statt in hooks.py: Frappe importiert
	hooks.py nur lazy, das Paket-__init__.py dagegen in jedem Prozesstyp (Web,
	Queue-Worker, Scheduler), bevor irgendein Untermodul geladen wird."""
	try:
		from pdf_on_submit import attach_pdf
	except ImportError:
		return

	import frappe

	original = attach_pdf.get_pdf_data

	def get_pdf_data(doctype, name, print_format=None, letterhead=None):
		from zeit_projekt.zeit_projekt.pdf import chrome_enabled

		if not chrome_enabled():
			return original(doctype, name, print_format, letterhead)
		return frappe.get_print(
			doctype, name, print_format, letterhead=letterhead, as_pdf=True, pdf_generator="chrome"
		)

	attach_pdf.get_pdf_data = get_pdf_data


_patch_pdf_on_submit_for_chrome()
