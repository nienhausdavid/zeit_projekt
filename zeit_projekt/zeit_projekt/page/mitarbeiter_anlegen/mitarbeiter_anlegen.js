// Seite "Mitarbeiter anlegen": Techniker legen sich mit einem kurzen Fragebogen selbst als
// Mitarbeiter an. Offen fuer jeden angemeldeten Desk-Benutzer; ob es klappt, entscheidet der
// Server (technician.py: Einstellung "Benutzer duerfen sich selbst als Mitarbeiter anlegen").
frappe.pages['mitarbeiter-anlegen'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Mitarbeiter anlegen'),
		single_column: true,
	});
	const body = $('<div></div>').css({ maxWidth: '480px', margin: '16px auto', padding: '0 16px' }).appendTo(page.main);
	const text = (html) => $('<p></p>').html(html).appendTo(body);
	const knopf = (label, aktion) =>
		$('<button type="button" class="btn btn-primary btn-lg"></button>')
			.text(label)
			.css({ width: '100%', minHeight: '64px', fontSize: '1.4rem', fontWeight: '600', marginTop: '12px' })
			.on('click', aktion)
			.appendTo(body);

	frappe.call('zeit_projekt.zeit_projekt.technician.get_employee_status').then((r) => {
		const status = r.message || {};
		if (status.employee) {
			text(__('Sie sind bereits als Mitarbeiter angelegt: {0}.', [frappe.utils.escape_html(status.employee)]));
			knopf(__('Zum Fahrtenbuch'), () => frappe.set_route('List', 'Fahrt'));
		} else if (status.self_service) {
			text(
				__(
					'Mit einem kurzen Fragebogen legen Sie Ihren eigenen Mitarbeitereintrag an. Danach können Sie Fahrten, Kundeneinsätze und Zeiten erfassen.'
				)
			);
			knopf(__('Fragebogen ausfüllen'), () => {
				frappe.require('/assets/zeit_projekt/js/mitarbeiter_fragebogen.js?v=2', () =>
					window.zeit_projekt.mitarbeiter_fragebogen()
				);
			});
		} else {
			text(__('Die Selbstanlage ist nicht freigeschaltet. Bitte die Verwaltung informieren.'));
		}
	});
};
