import erpnext
from frappe.model.document import Document


class SiteVisit(Document):
	def validate(self):
		if not self.company:
			self.company = erpnext.get_default_company()
