// Formular "Zeit Projekt Einstellungen": Auswahl in der Tabelle
// "Aktivitätsarten" auf aktive Verkaufsartikel beschränken.
frappe.ui.form.on('Zeit Projekt Einstellungen', {
	setup(frm) {
		frm.set_query('dienstleistungsartikel', 'aktivitaetsarten', () => ({
			filters: { disabled: 0, is_sales_item: 1, has_variants: 0 },
		}));
		frm.set_query('activity_type', 'aktivitaetsarten', () => ({ filters: { disabled: 0 } }));
	},
});
