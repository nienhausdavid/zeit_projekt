// Ergaenzt das bestehende Projekt-Formular um "Projekt abrechnen" (siehe
// projekt_abrechnen unten) und um einen Schnellzugriff, der eine neue Fahrt
// anlegt - optional mit sofort laufendem Timer (start_time = jetzt) und
// optional mit sofort geoeffneter Kamera fuer das Start-Kilometerstand-Foto. Beides einzeln umschaltbar in "Zeit Projekt Einstellungen"
// (auto_start_timer/auto_open_camera), Standard fuer beide: an.
//
// Zwei Wege dorthin, beide ausgeloest von start_fahrt_aus_projekt():
// 1. Eigener Button oben im Formular - frm.page.add_button() statt
//    frm.add_custom_button(), damit er als eigenstaendiger Button sichtbar
//    bleibt statt in der "..."-Sammelablage zu landen (gleiches Muster wie
//    der PDF-Button von pdf_on_submit).
// 2. Die "+"-Verknuepfung bei "Fahrten" unten in den Verknuepfungen -
//    frm.make_methods ist Frappes eigener Erweiterungspunkt dafuer (siehe
//    Form.make_new() im Frappe-Kern): ohne diesen Eintrag wuerde die
//    Verknuepfung nur das Projekt-Feld vorbelegen, keine Startzeit setzen.
frappe.ui.form.on('Project', {
	refresh(frm) {
		if (frm.is_new()) return;

		if (frappe.model.can_create('Sales Invoice')) {
			frm.add_custom_button(__('Projekt abrechnen'), () => projekt_abrechnen(frm), __('Create'));
		}

		if (!frappe.model.can_create('Fahrt')) return;

		frm.page.add_button(__('Fahrt mit Timer starten'), () => start_fahrt_aus_projekt(frm));

		frm.make_methods = frm.make_methods || {};
		frm.make_methods['Fahrt'] = () => start_fahrt_aus_projekt(frm);
	},
});

// "Projekt abrechnen": neue Ausgangsrechnung fuer Kunde und Projekt, in die
// gleich alle noch nicht abgerechneten Zeiten (aus Kundeneinsaetzen, Fahrten
// und Zeitblaettern) und Fahrt-Kilometer des Projekts geholt werden - derselbe
// Import wie der Knopf "Zeiten aus Zeiterfassung importieren" in der Rechnung
// (sales_invoice.js), nur ohne Datumsgrenzen. Die Rechnung bleibt ein Entwurf
// zum Pruefen; Kunde und Projekt kommen als Vorbelegung (ohne Feldereignisse,
// damit ERPNext nicht von sich aus Zeiten nachlaedt).
function projekt_abrechnen(frm) {
	if (!frm.doc.customer) {
		frappe.msgprint(__('Bitte zuerst einen Kunden im Projekt eintragen – er ist der Rechnungskunde.'));
		return;
	}
	frappe.new_doc('Sales Invoice', { customer: frm.doc.customer, project: frm.doc.name, company: frm.doc.company }).then(() => {
		const rechnung = cur_frm;
		if (!rechnung || rechnung.doctype !== 'Sales Invoice' || !rechnung.is_new()) return;
		if (!window.zeit_projekt || !window.zeit_projekt.zeiten_importieren) return;
		window.zeit_projekt.zeiten_importieren(rechnung, { project: frm.doc.name, replace: 0 });
	});
}

function start_fahrt_aus_projekt(frm) {
	// Mitarbeiter (falls dem Benutzer einer zugeordnet ist) zuerst holen und gleich
	// mitgeben: das Fahrt-Formular sucht ihn selbst erst asynchron beim Oeffnen,
	// das sofortige Speichern unten kaeme dem zuvor - ist "Mitarbeiter ist Pflicht"
	// an, scheiterte es, und die Kamera oeffnete nie. Ohne Mitarbeiter geht es
	// trotzdem weiter (er ist freiwillig).
	frappe.call('zeit_projekt.zeit_projekt.technician.get_employee_status').then(
		(r) => fahrt_anlegen(frm, r.message && r.message.employee),
		() => fahrt_anlegen(frm) // ohne Mitarbeiter weitermachen
	);
}

function fahrt_anlegen(frm, employee) {
	// Nicht frappe.db.get_single_value: "Zeit Projekt Einstellungen" darf nur der
	// System Manager lesen, Techniker bekaemen einen Rechte-Fehler.
	frappe.call('zeit_projekt.fahrtenbuch.fahrtenbuch.get_fahrt_defaults').then((r) => {
		const { auto_start_timer, auto_open_camera } = r.message || {};
		const values = { project: frm.doc.name, customer: frm.doc.customer };
		if (employee) values.employee = employee;
		if (auto_start_timer) {
			values.start_time = frappe.datetime.now_datetime();
		}

		// frappe.new_doc navigiert direkt zum vollen Formular (kein Quick-
		// Entry-Popup, das ist bei "Fahrt" nicht aktiviert) und loest sein
		// Promise erst, wenn diese Navigation fertig ist - cur_frm zeigt
		// danach zuverlaessig auf das neue Fahrt-Formular.
		frappe.new_doc('Fahrt', values).then(() => {
			if (!cur_frm || cur_frm.doctype !== 'Fahrt' || !cur_frm.is_new()) return;

			// Sofortiges Speichern, aus demselben Grund wie der Timer im
			// Fahrt-Formular selbst (siehe fahrtenbuch.js): eine neue,
			// ungespeicherte Fahrt existiert nur im Browser und ginge bei
			// einem Reload/Schliessen der Seite verloren.
			const after_create = auto_start_timer ? cur_frm.save() : Promise.resolve();
			after_create
				.then(() => {
					if (auto_open_camera) {
						window.zeit_projekt.foto_aufnehmen(cur_frm, 'start_odometer_photo');
					}
				})
				.catch(() => {
					// Speichern fehlgeschlagen: Frappe zeigt den Grund selbst an.
				});
		});
	});
}
