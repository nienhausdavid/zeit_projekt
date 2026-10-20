// Abrechnungsansicht: offene Zeiten und Kilometer je Kunde, Auftrag und Projekt.
frappe.query_reports['Abrechnungsansicht'] = {
	filters: [
		{ fieldname: 'customer', label: __('Kunde'), fieldtype: 'Link', options: 'Customer' },
		{
			fieldname: 'project', label: __('Projekt'), fieldtype: 'Link', options: 'Project',
			get_query: () => ({ filters: { customer: frappe.query_report.get_filter_value('customer') || undefined } }),
		},
		{
			fieldname: 'sales_order', label: __('Auftrag'), fieldtype: 'Link', options: 'Sales Order',
			get_query: () => ({ filters: { customer: frappe.query_report.get_filter_value('customer') || undefined, docstatus: ['<', 2] } }),
		},
		{ fieldname: 'from_date', label: __('Von (Datum)'), fieldtype: 'Date' },
		{ fieldname: 'to_date', label: __('Bis (Datum)'), fieldtype: 'Date' },
	],
};
