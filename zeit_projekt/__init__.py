__version__ = "0.0.1"


def _patch_pdf_on_submit_for_chrome():
	"""pdf_on_submit.attach_pdf.get_pdf_data() ruft frappe.utils.pdf.get_pdf()
	direkt auf - den rohen wkhtmltopdf-Pfad, ohne den pdf_generator-Mechanismus
	von frappe.get_print() (siehe zeit_projekt.site_visit.site_visit.force_chrome_pdf
	fuer den Hintergrund: wkhtmltopdf scheitert auf diesem Server grundsaetzlich).
	Betrifft damit auch die automatische PDF-Anlage beim Buchen, die
	force_chrome_pdf nicht abdeckt (kein HTTP-Request an download_pdf/
	printview, laeuft ggf. sogar in einem Queue-Worker ganz ohne
	Request-Kontext).

	pdf_on_submit ist ein Drittanbieter-Modul - hier gezielt nur die eine
	Funktion ersetzt, statt es zu forken. Steht bewusst hier statt in
	hooks.py: Frappe importiert hooks.py nur lazy, sobald ein konkreter Hook
	abgefragt wird (bestaetigt per bench console - attach_pdf.get_pdf_data
	blieb unveraendert, bis zeit_projekt.hooks explizit importiert wurde). Das
	Paket-__init__.py dagegen muss Python zwingend zuerst importieren, bevor
	irgendein Untermodul dieser App ueberhaupt referenzierbar ist - das
	garantiert den Patch in jedem Prozesstyp (Web, Queue-Worker, Scheduler),
	nicht nur dort, wo zufaellig zuerst ein zeit_projekt-Hook gezogen wird."""
	try:
		from pdf_on_submit import attach_pdf
	except ImportError:
		return

	import frappe

	def get_pdf_data(doctype, name, print_format=None, letterhead=None):
		return frappe.get_print(
			doctype, name, print_format, letterhead=letterhead, as_pdf=True, pdf_generator="chrome"
		)

	attach_pdf.get_pdf_data = get_pdf_data


_patch_pdf_on_submit_for_chrome()
