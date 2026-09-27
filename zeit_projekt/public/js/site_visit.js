// Zeitblatt wird erst beim Buchen angelegt (serverseitig, siehe hooks.py ->
// doc_events -> zeit_projekt.site_visit.site_visit.before_submit). Dieses
// Skript setzt nur Feld-Defaults und liefert nach dem Buchen einen Link
// dorthin - keine async Calls vor dem Buchen, um die Race Condition aus
// zeit_projekt/sales_order.js nicht zu wiederholen.

// Techniker (Rolle "Employee") duerfen Kunde, Auftrag und Artikel nicht lesen
// - Suche und Vorbelegung laufen deshalb ueber eingeschraenkte
// Server-Methoden (zeit_projekt/zeit_projekt/technician.py).
const TECHNICIAN_API = 'zeit_projekt.zeit_projekt.technician';

function link_details(doctype, name) {
	return frappe
		.call({ method: `${TECHNICIAN_API}.get_link_details`, args: { doctype, name } })
		.then((r) => r.message || {});
}

frappe.ui.form.on('Site Visit', {
	onload(frm) {
		// Auftrag-Auswahl auf offene Auftraege des gewaehlten Kunden (und,
		// falls gesetzt, Projekts) einschraenken. Dynamischer Filter - wird
		// bei jedem Oeffnen des Dropdowns neu anhand von frm.doc ausgewertet.
		frm.set_query('customer', () => ({ query: `${TECHNICIAN_API}.customer_query` }));
		frm.set_query('sales_order', () => {
			const filters = {};
			if (frm.doc.customer) filters.customer = frm.doc.customer;
			if (frm.doc.project) filters.project = frm.doc.project;
			return { query: `${TECHNICIAN_API}.sales_order_query`, filters };
		});
		frm.set_query('item_code', 'extra_items', () => ({ query: `${TECHNICIAN_API}.item_query` }));

		if (!frm.is_new()) return;
		if (!frm.doc.employee) {
			frappe.db.get_value('Employee', { user_id: frappe.session.user, status: 'Active' }, 'name')
				.then((r) => {
					if (r.message && r.message.name) frm.set_value('employee', r.message.name);
				});
		}
		// Kein automatischer Default fuer from_time mehr - das uebernimmt
		// jetzt der Timer (oder die manuelle Eingabe), siehe update_timer_toolbar
		// unten. Ein Default hier wuerde bei Formularoeffnung den falschen
		// Zeitpunkt festlegen, falls der Techniker den Einsatz erst spaeter
		// tatsaechlich beginnt.

		// Ueber die Verknuepfungen-Liste des Projekts angelegt ("+" bei Site
		// Visit): project ist dann schon vorbelegt, aber das Feldevent
		// project() unten feuert dabei nicht (Frappe setzt route_options beim
		// Neuanlegen direkt als Feldwert, nicht ueber set_value). Deshalb hier
		// dieselbe Logik einmal explizit anstossen.
		if (frm.doc.project) fill_from_project(frm);
	},

	project(frm) {
		if (!frm.doc.project) return;
		fill_from_project(frm);
	},

	sales_order(frm) {
		// Kunde (und, falls noch leer, Projekt) aus dem gewaehlten Auftrag
		// uebernehmen - derselbe Grund wie bei project(): der Techniker soll
		// das nicht doppelt eintragen muessen.
		if (!frm.doc.sales_order) return;
		link_details('Sales Order', frm.doc.sales_order).then((d) => {
			if (d.customer) frm.set_value('customer', d.customer);
			if (d.project && !frm.doc.project) frm.set_value('project', d.project);
		});
	},

	customer(frm) {
		// Ersatz fuer fetch_from (liest im Browser mit Nutzerrechten).
		if (!frm.doc.customer) {
			frm.set_value('customer_name', '');
			return;
		}
		link_details('Customer', frm.doc.customer).then((d) => {
			frm.set_value('customer_name', d.customer_name || '');
		});
	},

	refresh(frm) {
		frm.dashboard.clear_headline();
		update_timer_toolbar(frm);
		if (frm.doc.docstatus === 0 && !frm.doc.customer_signature) {
			frm.dashboard.set_headline_alert(__('Noch keine Kundenunterschrift erfasst.'), 'orange');
		}
		if (frm.doc.docstatus === 1 && frm.doc.timesheet) {
			frm.add_custom_button(__('Zeitblatt öffnen'), () => {
				frappe.set_route('Form', 'Timesheet', frm.doc.timesheet);
			});
		}
		if (frm.doc.docstatus === 0 && !frm.doc.sales_order) {
			frm.add_custom_button(__('Neuer Auftrag'), () => show_create_sales_order_dialog(frm));
		}
	},
});

// Timer fuer die Einsatzzeit - reine Komfortfunktion obendrauf auf from_time/
// to_time, die ganz normale, jederzeit von Hand editierbare Felder bleiben
// (kein read-only). "Start"/"Stopp" speichern sofort (wie ERPNexts eigener
// Timesheet-Timer in erpnext/public/js/projects/timer.js: frm.save() direkt
// nach dem Setzen von from_time) - deshalb sind customer/company/
// activity_type/sales_order/to_time nicht mehr reqd im Feld, sondern erst in
// before_submit (site_visit.py) Pflicht, sonst waere ein Entwurf mit nur
// laufendem Timer gar nicht speicherbar. Ohne das sofortige Speichern ginge
// der Timer bei einem Reload/Schliessen der Seite verloren, weil ein neues,
// ungespeichertes Dokument nur im Browser existiert. 1:1 uebernommen aus
// fahrtenbuch.js (dort ausfuehrlicher kommentiert).
function update_timer_toolbar(frm) {
	stop_ticking(frm);
	if (frm.doc.docstatus !== 0) return;

	if (!frm.doc.from_time) {
		frm.page.add_button(__('Timer starten'), () => {
			frm.set_value('from_time', frappe.datetime.now_datetime()).then(() => frm.save());
		});
	} else if (!frm.doc.to_time) {
		frm.page.add_button(__('Timer stoppen'), () => {
			frm.set_value('to_time', frappe.datetime.now_datetime()).then(() => frm.save());
		});
		start_ticking(frm);
	}
}

function start_ticking(frm) {
	const started_at = frappe.datetime.str_to_obj(frm.doc.from_time).getTime();
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
	frm.__site_visit_timer = setInterval(tick, 1000);
}

function stop_ticking(frm) {
	if (frm.__site_visit_timer) {
		clearInterval(frm.__site_visit_timer);
		frm.__site_visit_timer = null;
	}
}

// Preis und Betrag der Zusatzartikel ermittelt der Server beim Speichern aus
// der Preisliste (siehe SiteVisit.set_extra_item_rates) - hier nichts rechnen.

function show_create_sales_order_dialog(frm) {
	if (!frm.doc.customer) {
		frappe.msgprint(__('Bitte zuerst einen Kunden auswählen.'));
		return;
	}
	if (!(frm.doc.extra_items || []).length) {
		frappe.msgprint(__('Bitte zuerst mindestens einen Artikel hinzufügen, bevor ein neuer Auftrag angelegt wird.'));
		return;
	}
	const dialog = new frappe.ui.Dialog({
		title: __('Neuer Auftrag'),
		fields: [{ fieldname: 'po_no', fieldtype: 'Data', label: __('Kundenreferenz') }],
		primary_action_label: __('Create'),
		primary_action(values) {
			// Der Server liest Kunde, Projekt und Artikel aus dem gespeicherten
			// Site Visit - deshalb vorher speichern.
			const saved = frm.is_new() || frm.is_dirty() ? frm.save() : Promise.resolve();
			saved.then(() =>
				frappe.call({
					method: 'zeit_projekt.site_visit.site_visit.create_sales_order',
					args: { site_visit: frm.doc.name, po_no: values.po_no },
					freeze: true,
					freeze_message: __('Auftrag wird angelegt...'),
					callback(r) {
						if (!r.message) return;
						dialog.hide();
						frm.reload_doc();
					},
				})
			);
		},
	});
	dialog.show();
}

// Ersatz fuer fetch_from bei Artikelname/Einheit (s. customer() oben).
frappe.ui.form.on('Site Visit Item', {
	item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item_code) return;
		link_details('Item', row.item_code).then((d) => {
			frappe.model.set_value(cdt, cdn, 'item_name', d.item_name || '');
			frappe.model.set_value(cdt, cdn, 'uom', d.stock_uom || '');
		});
	},
});

function fill_from_project(frm) {
	if (!frm.doc.customer) {
		link_details('Project', frm.doc.project).then((d) => {
			if (d.customer) frm.set_value('customer', d.customer);
		});
	}
	// Genau ein offener Auftrag zum gewaehlten Projekt? Dann gleich
	// uebernehmen. Bei mehreren zeigt der Filter aus onload() nur noch die
	// passenden im Dropdown - der Techniker waehlt dann selbst.
	if (!frm.doc.sales_order) {
		frappe
			.call({
				method: `${TECHNICIAN_API}.get_open_sales_orders`,
				args: { project: frm.doc.project, customer: frm.doc.customer || null },
			})
			.then((r) => {
				const names = r.message || [];
				if (names.length === 1) frm.set_value('sales_order', names[0]);
			});
	}
}
