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
	// Verbrauchte Zeit gegen die geplanten Stunden: gruen im Rahmen, orange ab 80 %, rot ueber 100 %
	formatter(value, row, column, data, default_formatter) {
		const text = default_formatter(value, row, column, data);
		if (column.fieldname !== 'budget_prozent' || !data || !data.budget_farbe) return text;
		const farben = { green: 'var(--green-600)', orange: 'var(--orange-600)', red: 'var(--red-600)' };
		return `<span style="color: ${farben[data.budget_farbe]}; font-weight: 600">${text}</span>`;
	},
};
