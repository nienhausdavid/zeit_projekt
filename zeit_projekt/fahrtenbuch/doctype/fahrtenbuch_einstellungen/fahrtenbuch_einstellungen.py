import re

import frappe
from frappe import _
from frappe.model.document import Document

MIN_KONTEXT, MAX_KONTEXT = 2048, 262144


class FahrtenbuchEinstellungen(Document):
	def validate(self):
		# Zu kleine Fenster schneiden Bild oder Prompt ab, zu grosse sprengen den Speicher
		if self.context_length and not MIN_KONTEXT <= self.context_length <= MAX_KONTEXT:
			frappe.throw(
				_("Das Kontextfenster muss zwischen {0} und {1} Token liegen.").format(MIN_KONTEXT, MAX_KONTEXT)
			)
		if self.keep_alive and not re.fullmatch(r"-?\d+(\.\d+)?(ns|us|µs|ms|s|m|h)?", self.keep_alive.strip()):
			frappe.throw(_("Ungültige Verweildauer. Beispiele: 30m, 2h, 300s oder -1 (dauerhaft)."))
