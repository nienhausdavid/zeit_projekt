// Fragebogen fuer den eigenen Mitarbeiter: Techniker legen ihren Mitarbeiter selbst an
// (mitarbeiter_fragebogen()) oder passen ihre Angaben an (mitarbeiter_fragebogen(fertig, true)),
// ohne Rechte auf Employee zu bekommen. Pruefung und Speichern passieren serverseitig
// (zeit_projekt/technician.py: create_own_employee / update_own_employee) - hier nur die Maske.
// Wird bei Bedarf von der Seite und den Formularen nachgeladen (frappe.require).
window.zeit_projekt = window.zeit_projekt || {};

window.zeit_projekt.mitarbeiter_fragebogen = function (fertig, bearbeiten) {
	frappe
		.call({
			method: 'zeit_projekt.zeit_projekt.technician.get_employee_form_data',
			args: { bearbeiten: bearbeiten ? 1 : 0 },
		})
		.then((r) => {
			const d = r.message || {};
			const intro = bearbeiten
				? __(
						'Hier können Sie Ihre eigenen Mitarbeiterangaben ändern. Firma, Status und alles Weitere bleibt der Verwaltung vorbehalten.'
				  )
				: __(
						'Dieser kurze Fragebogen legt Ihren eigenen Mitarbeitereintrag an (nur für Ihren Benutzer). Dabei erhalten Sie die Rolle „Employee“ mit den normalen Techniker-Rechten (eigene Fahrten, Einsätze und Zeitblätter), keine weiteren Rechte.'
				  );
			const dialog = new frappe.ui.Dialog({
				title: bearbeiten ? __('Meine Mitarbeiterdaten anpassen') : __('Mich als Mitarbeiter anlegen'),
				fields: [
					{
						fieldtype: 'HTML',
						options: `<p class="text-muted">${intro}</p>${
							d.company ? `<p class="text-muted">${__('Firma')}: <b>${frappe.utils.escape_html(d.company)}</b></p>` : ''
						}`,
					},
					{ fieldname: 'first_name', fieldtype: 'Data', label: __('Vorname'), reqd: 1, default: d.first_name },
					{ fieldname: 'last_name', fieldtype: 'Data', label: __('Nachname'), default: d.last_name },
					{
						fieldname: 'gender',
						fieldtype: 'Select',
						label: __('Geschlecht'),
						reqd: 1,
						default: d.gender,
						options: ['', ...(d.genders || [])].join('\n'),
					},
					// Data-Felder, die unten zu nativen Datumsfeldern werden (Werte im Format JJJJ-MM-TT,
					// wie der Server sie erwartet). Frappes eigener Datumswaehler blaettert die Jahre in
					// Zehnerbloecken und oeffnet am Handy die Tastatur - der Dialog sprang dabei nach unten.
					{ fieldname: 'date_of_birth', fieldtype: 'Data', label: __('Geburtsdatum'), reqd: 1, default: d.date_of_birth },
					{
						fieldname: 'date_of_joining',
						fieldtype: 'Data',
						label: __('Eintrittsdatum'),
						default: d.date_of_joining || frappe.datetime.get_today(),
					},
				],
				primary_action_label: bearbeiten ? __('Speichern') : __('Anlegen'),
				primary_action(values) {
					frappe.call({
						method: bearbeiten
							? 'zeit_projekt.zeit_projekt.technician.update_own_employee'
							: 'zeit_projekt.zeit_projekt.technician.create_own_employee',
						args: values,
						freeze: true,
						callback(res) {
							if (!res.message) return;
							dialog.hide();
							frappe.show_alert({
								message: bearbeiten
									? __('Mitarbeiterdaten gespeichert.')
									: __('Mitarbeiter {0} angelegt.', [res.message]),
								indicator: 'green',
							});
							if (fertig) fertig(res.message);
							// Neu angelegt: die Rolle Employee kommt erst durch den Eintrag dazu, also neu laden,
							// damit der Desk die neuen Rechte kennt. Beim Aendern nur die Seite auffrischen.
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
