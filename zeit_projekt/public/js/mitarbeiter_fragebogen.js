// Fragebogen "Mitarbeiter fuer mich anlegen": Techniker legen ihren eigenen Mitarbeiter an,
// ohne Rechte auf Employee zu bekommen. Die Pruefung und das Anlegen passieren serverseitig
// (zeit_projekt/technician.py: create_own_employee) - hier nur die Eingabemaske.
// Wird bei Bedarf von fahrtenbuch.js / site_visit.js nachgeladen (frappe.require).
window.zeit_projekt = window.zeit_projekt || {};

window.zeit_projekt.mitarbeiter_fragebogen = function (fertig) {
	frappe.call('zeit_projekt.zeit_projekt.technician.get_employee_form_data').then((r) => {
		const d = r.message || {};
		const dialog = new frappe.ui.Dialog({
			title: __('Mich als Mitarbeiter anlegen'),
			fields: [
				{
					fieldtype: 'HTML',
					options: `<p class="text-muted">${__(
						'Dieser kurze Fragebogen legt Ihren eigenen Mitarbeitereintrag an (nur für Ihren Benutzer). Dabei erhalten Sie die Rolle „Employee“ mit den normalen Techniker-Rechten (eigene Fahrten, Einsätze und Zeitblätter), keine weiteren Rechte.'
					)}</p>${d.company ? `<p class="text-muted">${__('Firma')}: <b>${frappe.utils.escape_html(d.company)}</b></p>` : ''}`,
				},
				{ fieldname: 'first_name', fieldtype: 'Data', label: __('Vorname'), reqd: 1, default: d.first_name },
				{ fieldname: 'last_name', fieldtype: 'Data', label: __('Nachname'), default: d.last_name },
				{
					fieldname: 'gender',
					fieldtype: 'Select',
					label: __('Geschlecht'),
					reqd: 1,
					options: ['', ...(d.genders || [])].join('\n'),
				},
				// Data-Felder, die unten zu nativen Datumsfeldern werden (Werte im Format JJJJ-MM-TT,
				// wie der Server sie erwartet). Frappes eigener Datumswaehler blaettert die Jahre in
				// Zehnerbloecken und oeffnet am Handy die Tastatur - der Dialog sprang dabei nach unten.
				{ fieldname: 'date_of_birth', fieldtype: 'Data', label: __('Geburtsdatum'), reqd: 1 },
				{
					fieldname: 'date_of_joining',
					fieldtype: 'Data',
					label: __('Eintrittsdatum'),
					default: frappe.datetime.get_today(),
				},
			],
			primary_action_label: __('Anlegen'),
			primary_action(values) {
				frappe.call({
					method: 'zeit_projekt.zeit_projekt.technician.create_own_employee',
					args: values,
					freeze: true,
					callback(res) {
						if (!res.message) return;
						dialog.hide();
						frappe.show_alert({ message: __('Mitarbeiter {0} angelegt.', [res.message]), indicator: 'green' });
						if (fertig) fertig(res.message);
						// Die Rolle Employee kommt erst durch den neuen Eintrag dazu: neu laden,
						// damit der Desk die neuen Rechte kennt.
						setTimeout(() => window.location.reload(), 1500);
					},
				});
			},
		});
		dialog.show();
		// Natives Datumsfeld des Browsers: am Handy das Standard-Datumsrad, keine Tastatur, schnelle
		// Jahresauswahl. min/max halten die Eingabe plausibel (der Server prueft sie ebenfalls).
		const heute = frappe.datetime.get_today();
		const nativ = (feld, min) => {
			const $input = dialog.fields_dict[feld].$input;
			if ($input) $input.attr({ type: 'date', min, max: heute, placeholder: '' });
		};
		nativ('date_of_birth', '1900-01-01');
		nativ('date_of_joining', '1990-01-01');
	});
};
