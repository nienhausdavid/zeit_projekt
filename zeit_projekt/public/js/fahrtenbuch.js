// Abrechnung passiert serverseitig beim Buchen (siehe hooks.py -> doc_events
// -> zeit_projekt.fahrtenbuch.fahrtenbuch.before_submit). Dieses Skript setzt
// nur Feld-Defaults, uebernimmt Werte aus einer verknuepften Site Visit und
// stoesst die Kilometerstand-Erkennung nach einem Foto-Upload an - keine
// async Calls vor dem Buchen, um die Race Condition aus
// zeit_projekt/sales_order.js nicht zu wiederholen.

frappe.ui.form.on('Fahrt', {
	onload(frm) {
		// Auftrag/Projekt auf den gewaehlten Kunden einschraenken (Auftrag
		// zusaetzlich auf das gewaehlte Projekt, falls gesetzt). Dynamischer
		// Filter - wird bei jedem Oeffnen des Dropdowns neu anhand des
		// aktuellen frm.doc ausgewertet.
		frm.set_query('project', () => {
			return frm.doc.customer ? { filters: { customer: frm.doc.customer } } : {};
		});
		frm.set_query('sales_order', () => {
			const filters = {};
			if (frm.doc.customer) filters.customer = frm.doc.customer;
			if (frm.doc.project) filters.project = frm.doc.project;
			return { filters };
		});
		frm.set_query('site_visit', () => {
			return frm.doc.customer ? { filters: { customer: frm.doc.customer } } : {};
		});

		if (!frm.is_new()) return;
		if (!frm.doc.employee) {
			frappe.db.get_value('Employee', { user_id: frappe.session.user, status: 'Active' }, 'name')
				.then((r) => {
					if (r.message && r.message.name) frm.set_value('employee', r.message.name);
				});
		}
		if (!frm.doc.time_item) {
			frappe.db.get_single_value('Fahrtenbuch Einstellungen', 'time_item').then((value) => {
				if (value) frm.set_value('time_item', value);
			});
		}
		// Kein automatischer Default fuer start_time mehr - das uebernimmt
		// jetzt der Timer (oder die manuelle Eingabe). Ein Default hier wuerde
		// bei Formularoeffnung den falschen Zeitpunkt festlegen, falls der
		// Techniker erst spaeter tatsaechlich losfaehrt.
	},

	site_visit(frm) {
		if (!frm.doc.site_visit) return;
		frappe.db.get_value('Site Visit', frm.doc.site_visit, ['customer', 'project', 'sales_order'])
			.then((r) => {
				if (!r.message) return;
				if (r.message.customer && !frm.doc.customer) frm.set_value('customer', r.message.customer);
				if (r.message.project && !frm.doc.project) frm.set_value('project', r.message.project);
				if (r.message.sales_order && !frm.doc.sales_order) {
					frm.set_value('sales_order', r.message.sales_order);
				}
			});
	},

	project(frm) {
		// Kunde aus dem gewaehlten Projekt uebernehmen, falls noch leer -
		// der Techniker soll das nicht doppelt eintragen muessen.
		if (!frm.doc.project || frm.doc.customer) return;
		frappe.db.get_value('Project', frm.doc.project, 'customer').then((r) => {
			if (r.message && r.message.customer) frm.set_value('customer', r.message.customer);
		});
	},

	sales_order(frm) {
		// Kunde (und, falls noch leer, Projekt) aus dem gewaehlten Auftrag
		// uebernehmen - derselbe Grund wie bei project().
		if (!frm.doc.sales_order) return;
		frappe.db.get_value('Sales Order', frm.doc.sales_order, ['customer', 'project']).then((r) => {
			if (!r.message) return;
			if (r.message.customer && !frm.doc.customer) frm.set_value('customer', r.message.customer);
			if (r.message.project && !frm.doc.project) frm.set_value('project', r.message.project);
		});
	},

	start_odometer_photo(frm) {
		fetch_odometer_reading(frm, 'start_odometer_photo', 'start_odometer');
	},

	end_odometer_photo(frm) {
		fetch_odometer_reading(frm, 'end_odometer_photo', 'end_odometer');
	},

	refresh(frm) {
		frm.dashboard.clear_headline();
		update_timer_toolbar(frm);
		if (frm.doc.start_odometer && frm.doc.end_odometer && frm.doc.distance_km) {
			frm.dashboard.set_headline_alert(
				__('Strecke: {0} km, Dauer: {1} Std.', [frm.doc.distance_km, frm.doc.duration_hours]),
				'blue'
			);
		}
	},
});

// Timer fuer die Fahrzeit - reine Komfortfunktion obendrauf auf start_time/
// end_time, die ganz normale, jederzeit von Hand editierbare Felder bleiben
// (kein read-only). "Start"/"Stopp" speichern sofort (wie ERPNexts eigener
// Timesheet-Timer in erpnext/public/js/projects/timer.js: frm.save() direkt
// nach dem Setzen von from_time) - end_time/Kilometerstaende/Auftrag/Artikel
// sind deshalb nicht mehr reqd im Feld, sondern erst in Fahrt.before_submit
// (fahrt.py) Pflicht, sonst waere ein Entwurf mit nur laufendem Timer gar
// nicht speicherbar. Ohne das sofortige Speichern ginge der Timer bei einem
// Reload/Schliessen der Seite verloren, weil ein neues, ungespeichertes
// Dokument nur im Browser existiert.
function update_timer_toolbar(frm) {
	stop_ticking(frm);
	if (frm.doc.docstatus !== 0) return;

	if (!frm.doc.start_time) {
		frm.page.add_button(__('Timer starten'), () => {
			frm.set_value('start_time', frappe.datetime.now_datetime()).then(() => frm.save());
		});
	} else if (!frm.doc.end_time) {
		frm.page.add_button(__('Timer stoppen'), () => {
			frm.set_value('end_time', frappe.datetime.now_datetime()).then(() => frm.save());
		});
		start_ticking(frm);
	}
}

function start_ticking(frm) {
	const started_at = frappe.datetime.str_to_obj(frm.doc.start_time).getTime();
	const tick = () => {
		const total_seconds = Math.max(0, Math.floor((Date.now() - started_at) / 1000));
		const h = String(Math.floor(total_seconds / 3600)).padStart(2, '0');
		const m = String(Math.floor((total_seconds % 3600) / 60)).padStart(2, '0');
		const s = String(total_seconds % 60).padStart(2, '0');
		// clear_headline() zuerst: show_message() im Frappe-Layout haengt bei
		// jedem Aufruf nur einen neuen Block an, statt den alten zu ersetzen -
		// ohne das Clear stapeln sich die Meldungen im Sekundentakt.
		frm.dashboard.clear_headline();
		frm.dashboard.set_headline_alert(__('Timer läuft: {0}', [`${h}:${m}:${s}`]), 'orange');
	};
	tick();
	frm.__fahrtenbuch_timer = setInterval(tick, 1000);
}

function stop_ticking(frm) {
	if (frm.__fahrtenbuch_timer) {
		clearInterval(frm.__fahrtenbuch_timer);
		frm.__fahrtenbuch_timer = null;
	}
}

function fetch_odometer_reading(frm, photo_field, odometer_field) {
	const file_url = frm.doc[photo_field];
	if (!file_url) return;

	frappe.call({
		method: 'zeit_projekt.fahrtenbuch.fahrtenbuch.get_odometer_reading',
		args: { file_url },
		freeze: true,
		freeze_message: __('Kilometerstand wird erkannt...'),
		callback(r) {
			if (r.message) {
				frm.set_value(odometer_field, r.message);
				frappe.show_alert({ message: __('Kilometerstand erkannt: {0}', [r.message]), indicator: 'green' });
			} else {
				frappe.show_alert({
					message: __('Konnte den Kilometerstand nicht erkennen, bitte manuell eintragen.'),
					indicator: 'orange',
				});
			}
		},
	});
}
