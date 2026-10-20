// Auftrags- und Projektansicht: Projekte mit ihren Aufträgen, dazu Aufträge ohne Projekt.
frappe.query_reports['Auftrags- und Projektansicht'] = {
	filters: [
		{ fieldname: 'customer', label: __('Kunde'), fieldtype: 'Link', options: 'Customer' },
		{
			fieldname: 'project', label: __('Projekt'), fieldtype: 'Link', options: 'Project',
			get_query: () => ({ filters: { customer: frappe.query_report.get_filter_value('customer') || undefined } }),
		},
		{
			fieldname: 'abgeschlossene_ausblenden', label: __('Abgeschlossene ausblenden'),
			fieldtype: 'Check', default: 1,
		},
	],
};
