// Beim Buchen legt der Server ein Zeitblatt für die Fahrzeit an (siehe
// hooks.py -> doc_events -> zeit_projekt.fahrtenbuch.fahrtenbuch.before_submit);
// Fahrzeit und Kilometer werden über den Zeitimport der Ausgangsrechnung
// abgerechnet. Dieses Skript setzt nur Feld-Defaults, übernimmt Werte aus
// verknüpften Belegen und stößt die Kilometerstand-Erkennung an - keine async
// Calls vor dem Buchen, um die Race Condition aus sales_order.js nicht zu
// wiederholen.

// Techniker (Rolle "Employee") duerfen Kunde, Auftrag, Artikel und Fahrzeug
// nicht lesen - Suche und Vorbelegung laufen deshalb ueber eingeschraenkte
// Server-Methoden (zeit_projekt/zeit_projekt/technician.py).
const TECHNICIAN_API = 'zeit_projekt.zeit_projekt.technician';

function link_details(doctype, name) {
	return frappe
		.call({ method: `${TECHNICIAN_API}.get_link_details`, args: { doctype, name } })
		.then((r) => r.message || {});
}

frappe.ui.form.on('Fahrt', {
	onload(frm) {
		// Auftrag/Projekt auf den gewaehlten Kunden einschraenken (Auftrag
		// zusaetzlich auf das gewaehlte Projekt, falls gesetzt). Dynamischer
		// Filter - wird bei jedem Oeffnen des Dropdowns neu anhand des
		// aktuellen frm.doc ausgewertet.
		frm.set_query('customer', () => ({ query: `${TECHNICIAN_API}.customer_query` }));
		frm.set_query('project', () => {
			return frm.doc.customer ? { filters: { customer: frm.doc.customer } } : {};
		});
		frm.set_query('sales_order', () => {
			const filters = {};
			if (frm.doc.customer) filters.customer = frm.doc.customer;
			if (frm.doc.project) filters.project = frm.doc.project;
			return { query: `${TECHNICIAN_API}.sales_order_query`, filters };
		});
		frm.set_query('site_visit', () => {
			return frm.doc.customer ? { filters: { customer: frm.doc.customer } } : {};
		});
		frm.set_query('km_item', () => ({ query: `${TECHNICIAN_API}.item_query` }));
		frm.set_query('vehicle', () => ({ query: `${TECHNICIAN_API}.vehicle_query` }));

		if (!frm.is_new()) return;
		frappe.call('zeit_projekt.fahrtenbuch.fahrtenbuch.get_fahrt_defaults').then((r) => {
			const d = r.message || {};
			if (d.activity_type && !frm.doc.activity_type) frm.set_value('activity_type', d.activity_type);
			if (d.km_item && !frm.doc.km_item) frm.set_value('km_item', d.km_item);
		});
		// Kein automatischer Default fuer start_time - das uebernimmt der Timer (grosser
		// Knopf oben im Formular) oder die manuelle Eingabe. Ein Default beim Oeffnen
		// wuerde den falschen Zeitpunkt festlegen, falls der Techniker erst spaeter losfaehrt.
	},

	site_visit(frm) {
		if (!frm.doc.site_visit) return;
		link_details('Site Visit', frm.doc.site_visit).then((d) => {
			if (d.customer && !frm.doc.customer) frm.set_value('customer', d.customer);
			if (d.project && !frm.doc.project) frm.set_value('project', d.project);
			if (d.sales_order && !frm.doc.sales_order) frm.set_value('sales_order', d.sales_order);
		});
	},

	project(frm) {
		// Kunde aus dem gewaehlten Projekt uebernehmen, falls noch leer -
		// der Techniker soll das nicht doppelt eintragen muessen.
		if (!frm.doc.project || frm.doc.customer) return;
		link_details('Project', frm.doc.project).then((d) => {
			if (d.customer) frm.set_value('customer', d.customer);
		});
	},

	sales_order(frm) {
		// Kunde (und, falls noch leer, Projekt) aus dem gewaehlten Auftrag
		// uebernehmen - derselbe Grund wie bei project().
		if (!frm.doc.sales_order) return;
		link_details('Sales Order', frm.doc.sales_order).then((d) => {
			if (d.customer && !frm.doc.customer) frm.set_value('customer', d.customer);
			if (d.project && !frm.doc.project) frm.set_value('project', d.project);
		});
	},

	start_odometer_photo(frm) {
		update_timer_toolbar(frm); // Knopf weg, sobald das Foto da ist
		fetch_odometer_reading(frm, 'start_odometer_photo', 'start_odometer');
	},

	end_odometer_photo(frm) {
		update_timer_toolbar(frm);
		fetch_odometer_reading(frm, 'end_odometer_photo', 'end_odometer');
	},

	// Ändert der Techniker einen erkannten Wert, ist die "nicht sicher"-Markierung erledigt.
	vehicle(frm) {
		lade_letzten_stand(frm);
	},

	start_odometer(frm) {
		setze_hinweis(frm, 'start_odometer');
		// Von Hand eingetragen oder korrigiert: die "nicht sicher"-Markierung ist erledigt
		if (frm.__zp_unsicher) frm.__zp_unsicher.start_odometer = false;
		update_timer_toolbar(frm);
		// Handeingabe pruefen (ein von der Erkennung gesetzter Wert wird dort selbst geprueft)
		if (!frm.__zp_erkennung_setzt && frm.doc.docstatus === 0) {
			pruefe_startstand(frm, cint(frm.doc.start_odometer)).then((warnung) => {
				if (!warnung) return;
				setze_hinweis(frm, 'start_odometer', warnung + letzter_stand_text(frm));
				frappe.show_alert({ message: warnung, indicator: 'orange' }, 12);
			});
		}
	},

	end_odometer(frm) {
		setze_hinweis(frm, 'end_odometer');
	},

	refresh(frm) {
		frm.dashboard.clear_headline();
		setze_foto_hinweise(frm);
		update_timer_toolbar(frm);
		fahrzeug_vorbelegen(frm);
		lade_letzten_stand(frm);
		zeige_wartende_fotos(frm);
		window.zeit_projekt.foto_warteschlange.senden(foto_zuordnen);
		mitarbeiter_pruefen(frm);
		frm.toggle_display('section_break_karte', !!frm.doc.route_map);
		standort_nachtragen(frm);
		if (frm.doc.docstatus === 1 && frm.doc.timesheet) {
			frm.add_custom_button(__('Zeitblatt öffnen'), () => frappe.set_route('Form', 'Timesheet', frm.doc.timesheet));
		}
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
// Einstellungen "Knoepfe im Fahrt-Formular": einmal je Seitenaufruf geladen (Techniker duerfen
// die Einstellungen nicht lesen). Bis sie da sind, gelten alle Knoepfe als an.
const KNOPF_SCHALTER = ['knopf_timer', 'knopf_foto', 'knopf_timer_foto', 'knopf_ende_foto'];
const knopf_einstellung = { knopf_timer: 1, knopf_foto: 1, knopf_timer_foto: 1, knopf_ende_foto: 1, max_km_luecke: 500, geladen: false };

function lade_knopf_einstellung(frm) {
	if (knopf_einstellung.geladen) return;
	knopf_einstellung.geladen = true;
	frappe.call('zeit_projekt.fahrtenbuch.fahrtenbuch.get_fahrt_defaults').then((r) => {
		const d = r.message || {};
		const neu = KNOPF_SCHALTER.some((k) => k in d && cint(d[k]) !== knopf_einstellung[k]);
		if ('max_km_luecke' in d) knopf_einstellung.max_km_luecke = cint(d.max_km_luecke);
		KNOPF_SCHALTER.forEach((k) => {
			if (k in d) knopf_einstellung[k] = cint(d[k]);
		});
		if (neu && cur_frm === frm) update_timer_toolbar(frm);
	});
}

function update_timer_toolbar(frm) {
	lade_knopf_einstellung(frm);
	stop_ticking(frm);
	entferne_knopfleiste(frm);
	zeige_foto_knoepfe(frm);
	if (frm.doc.docstatus !== 0) return;

	const jetzt = () => frappe.datetime.now_datetime();
	const knoepfe = [];
	const timer_knoepfe = !!knopf_einstellung.knopf_timer;
	if (!frm.doc.start_time) {
		// Nur einmalig: verschwindet, sobald der Timer laeuft bzw. das Startfoto da ist.
		// Die Kamera wird zuerst geoeffnet (synchron im Klick, sonst blockt sie der
		// Browser am Handy); der Timer startet und speichert gleichzeitig.
		if (knopf_einstellung.knopf_timer_foto && !frm.doc.start_odometer_photo) {
			knoepfe.push([__('Timer starten und Kilometerstand fotografieren'), 'btn-primary', () => {
				capture_photo_for_field(frm, 'start_odometer_photo');
				return frm.set_value('start_time', jetzt()).then(() => frm.save());
			}]);
		}
		if (timer_knoepfe) {
			knoepfe.push([__('Timer starten'), 'btn-primary', () =>
				frm.set_value('start_time', jetzt()).then(() => frm.save()),
			]);
		}
	} else if (!frm.doc.end_time) {
		const pause = open_break(frm);
		if (!timer_knoepfe) {
			// keine Knoepfe: der Timer (Anzeige oben) laeuft trotzdem mit
		} else if (pause) {
			knoepfe.push([__('Timer fortsetzen'), 'btn-success', () =>
				frappe.model.set_value(pause.doctype, pause.name, 'to_time', jetzt()).then(() => frm.save()),
			]);
		} else {
			knoepfe.push([__('Timer pausieren'), 'btn-warning', () => show_pause_dialog(frm)]);
		}
		// Eine laufende Pause endet serverseitig automatisch mit der Fahrt
		// (zeit_projekt/pausen.py, pausen_pruefen).
		// Einmalig: Kamera zuerst (synchron im Klick), gleichzeitig Fahrt beenden und speichern.
		// Wie "Foto Ende" erst, wenn der Startstand feststeht.
		const start_unsicher = !!(frm.__zp_unsicher && frm.__zp_unsicher.start_odometer);
		if (
			knopf_einstellung.knopf_ende_foto &&
			cint(frm.doc.start_odometer) > 0 &&
			!start_unsicher &&
			!frm.doc.end_odometer_photo
		) {
			knoepfe.push([__('Endstand fotografieren und Fahrt beenden'), 'btn-danger', () => {
				capture_photo_for_field(frm, 'end_odometer_photo');
				return frm.set_value('end_time', jetzt()).then(() => frm.save());
			}]);
		}
		if (timer_knoepfe) {
			knoepfe.push([__('Timer stoppen'), 'btn-danger', () =>
				frm.set_value('end_time', jetzt()).then(() => frm.save()),
			]);
		}
		start_ticking(frm);
	}
	zeige_knopfleiste(frm, knoepfe);
}

// Grosse Knoepfe untereinander oben im Formular statt kleiner in der Kopfzeile: gerade
// am Handy sind das die wichtigsten Aktionen der Fahrt und sonst leicht zu uebersehen und
// zu klein zum Treffen. Auf dem Handy bildschirmbreit, am Desktop auf 480 px begrenzt.
function zeige_knopfleiste(frm, knoepfe) {
	if (!knoepfe.length) return;
	const leiste = $('<div class="zp-knopfleiste"></div>').css({
		display: 'flex',
		flexDirection: 'column',
		gap: '10px',
		maxWidth: '480px',
		margin: '12px 0 16px',
	});
	for (const [text, klasse, aktion] of knoepfe) leiste.append(grosser_knopf(text, klasse, aktion));
	$(frm.layout.wrapper).prepend(leiste);
}

function grosser_knopf(text, klasse, aktion) {
	return $(`<button type="button" class="btn ${klasse} btn-lg"></button>`)
		.text(text)
		.css({ width: '100%', minHeight: '64px', fontSize: '1.4rem', fontWeight: '600', whiteSpace: 'normal', lineHeight: '1.25', padding: '10px 14px' })
		.on('click', function () {
			const el = $(this);
			el.prop('disabled', true); // kein Doppelklick: sonst zweimal gespeichert
			// Scheitert die Aktion (z. B. Speichern an einer Pruefung), Knopf wieder freigeben
			Promise.resolve()
				.then(aktion)
				.catch(() => {})
				.finally(() => el.prop('disabled', false));
		});
}

// Die Foto-Knoepfe sitzen im Abschnitt "Kilometerstand", jeder direkt ueber seinem
// Foto-Feld. Am Handy der schnellste Weg zur Kamera (der Tipp auf den Knopf ist zugleich
// die Erlaubnis des Browsers, die Kamera zu oeffnen). Der Knopf verschwindet, sobald das
// Foto vorhanden ist; "Ende" erscheint ab dem Start des Timers.
function zeige_foto_knoepfe(frm) {
	$(frm.layout.wrapper).find('.zp-foto-knopf').remove();
	if (frm.doc.docstatus !== 0 || !knopf_einstellung.knopf_foto) return;
	const start_unsicher = !!(frm.__zp_unsicher && frm.__zp_unsicher.start_odometer);
	// "Foto Ende" erst, wenn der Startstand feststeht: richtig erkannt oder von Hand
	// eingetragen bzw. korrigiert. Ein "nicht sicher" erkannter Wert zaehlt erst, wenn er
	// bestaetigt oder geaendert wurde (die Markierung gilt nur in dieser Sitzung).
	const start_steht = cint(frm.doc.start_odometer) > 0 && !start_unsicher;
	const knoepfe = [
		['start_odometer_photo', __('Foto Kilometerstand Start'), !frm.doc.start_odometer_photo, () =>
			capture_photo_for_field(frm, 'start_odometer_photo'),
		],
		['start_odometer', __('Startstand stimmt'), start_unsicher, () => {
			frm.__zp_unsicher.start_odometer = false;
			setze_hinweis(frm, 'start_odometer');
			update_timer_toolbar(frm);
		}],
		['end_odometer_photo', __('Foto Kilometerstand Ende'), start_steht && !frm.doc.end_odometer_photo, () =>
			capture_photo_for_field(frm, 'end_odometer_photo'),
		],
	];
	for (const [feld, text, anzeigen, aktion] of knoepfe) {
		const control = frm.fields_dict[feld];
		if (!anzeigen || !control) continue;
		grosser_knopf(text, 'btn-default', aktion)
			.addClass('zp-foto-knopf')
			.css({ marginBottom: '12px' })
			.insertBefore($(control.wrapper));
	}
}

function entferne_knopfleiste(frm) {
	$(frm.layout.wrapper).find('.zp-knopfleiste').remove();
}

function open_break(frm) {
	return (frm.doc.breaks || []).find((row) => row.from_time && !row.to_time);
}

function show_pause_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __('Timer pausieren'),
		fields: [
			{
				fieldname: 'reason',
				fieldtype: 'Select',
				label: __('Grund'),
				options: [
					{ value: 'Pause', label: __('Pause') },
					{ value: 'Notfall bei anderem Kunden', label: __('Notfall bei anderem Kunden') },
					{ value: 'Sonstiges', label: __('Sonstiges') },
				],
				default: 'Pause',
				reqd: 1,
			},
			{ fieldname: 'note', fieldtype: 'Small Text', label: __('Notiz') },
		],
		primary_action_label: __('Pausieren'),
		primary_action(values) {
			dialog.hide();
			frm.add_child('breaks', {
				from_time: frappe.datetime.now_datetime(),
				reason: values.reason,
				note: values.note,
			});
			frm.refresh_field('breaks');
			frm.save();
		},
	});
	dialog.show();
}

// Netto-Fahrzeit seit Beginn: abgeschlossene und laufende Pausen abgezogen.
function worked_seconds(frm, now) {
	const ms = (value) => frappe.datetime.str_to_obj(value).getTime();
	let total = now - ms(frm.doc.start_time);
	for (const row of frm.doc.breaks || []) {
		if (!row.from_time) continue;
		total -= (row.to_time ? ms(row.to_time) : now) - ms(row.from_time);
	}
	return Math.max(0, Math.floor(total / 1000));
}

function format_duration(total_seconds) {
	const h = String(Math.floor(total_seconds / 3600)).padStart(2, '0');
	const m = String(Math.floor((total_seconds % 3600) / 60)).padStart(2, '0');
	const s = String(total_seconds % 60).padStart(2, '0');
	return `${h}:${m}:${s}`;
}

function start_ticking(frm) {
	const tick = () => {
		const gefahren = format_duration(worked_seconds(frm, Date.now()));
		const pause = open_break(frm);
		// clear_headline() zuerst: show_message() im Frappe-Layout haengt bei
		// jedem Aufruf nur einen neuen Block an, statt den alten zu ersetzen -
		// ohne das Clear stapeln sich die Meldungen im Sekundentakt.
		frm.dashboard.clear_headline();
		if (pause) {
			const seit = frappe.datetime.str_to_user(pause.from_time).split(' ').pop();
			frm.dashboard.set_headline_alert(
				__('Pausiert seit {0} – Fahrzeit bisher {1}', [seit, gefahren]),
				'blue'
			);
		} else {
			frm.dashboard.set_headline_alert(__('Timer läuft: {0}', [gefahren]), 'orange');
		}
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

// Kilometerstand-Erkennung läuft als Hintergrund-Job (bis zu 45 s) - das
// Formular bleibt bedienbar, das Ergebnis kommt per Realtime-Event zurück.
// Global statt im Skript-Scope: das Formular-Skript kann mehrfach ausgeführt
// werden, der Realtime-Listener soll trotzdem nur einmal existieren.
window.zeit_projekt_ocr = window.zeit_projekt_ocr || { offen: {}, listener: false };
const offene_erkennungen = window.zeit_projekt_ocr.offen;

// Genauer Stand der Erkennung (Phase vom Server) plus mitlaufende Sekunden, in der Statuszeile
// am Foto-Feld. Die Sekunden zaehlen ab dem Hochladen, damit man sieht, dass es weitergeht.
function erkennung_statustext(phase) {
	const m = phase || {};
	switch (m.phase) {
		case 'warteschlange':
			return __('Erkennung wartet in der Warteschlange');
		case 'bild':
			return __('Foto wird für die Erkennung aufbereitet');
		case 'frage':
			return __('Modell {0} liest das Foto (Anfrage {1} von höchstens {2})', [m.modell, m.nr, m.von]);
		case 'antwort':
			return m.wert
				? __('Antwort {0}: {1} – wird mit weiteren Antworten abgeglichen', [m.nr, m.wert])
				: __('Antwort {0}: nichts erkannt – nächste Anfrage', [m.nr]);
		default:
			return __('Erkennung gestartet');
	}
}

function aktualisiere_erkennungsstatus(auftrag) {
	const frm = cur_frm;
	if (!frm || frm.doctype !== 'Fahrt' || frm.doc[auftrag.photo_field] !== auftrag.file_url) return;
	const sek = Math.round((Date.now() - auftrag.start) / 1000);
	if (sek > 900) return clearInterval(auftrag.takt); // Sicherheitsnetz: nie endlos mitzaehlen
	setze_status(frm, auftrag.photo_field, `${erkennung_statustext(auftrag.phase)} … ${sek} s`, null);
}

if (!window.zeit_projekt_ocr.listener) {
	window.zeit_projekt_ocr.listener = true;
	frappe.realtime.on('zeit_projekt_odometer_status', (data) => {
		const auftrag = window.zeit_projekt_ocr.offen[data.request_id];
		if (!auftrag) return;
		auftrag.phase = data;
		aktualisiere_erkennungsstatus(auftrag);
	});
	frappe.realtime.on('zeit_projekt_odometer', (data) => {
		const auftrag = window.zeit_projekt_ocr.offen[data.request_id];
		if (!auftrag) return;
		delete window.zeit_projekt_ocr.offen[data.request_id];
		clearInterval(auftrag.takt);
		zeige_erkennung(auftrag, data);
	});
}

// Plausibilitaet des Startstands gegen den letzten bekannten Stand des Fahrzeugs (Endstand der
// juengsten Fahrt, sonst Fahrzeugdaten). Auffaellig: Stand unter dem letzten Stand oder mehr als
// "Groesste erwartete Luecke" darueber (Einstellung, 0 = Luecke nicht pruefen) - meist ein Lesefehler
// (TRIP statt ODO, fehlende Ziffer).
function letzter_stand_text(frm) {
	const l = frm.__zp_letzter;
	if (!l) return '';
	return ' ' + __('Letzter Stand dieses Fahrzeugs: {0} km{1}.', [l.stand, l.fahrt ? ` (${l.fahrt})` : '']);
}

function lade_letzten_stand(frm) {
	if (frm.doc.docstatus !== 0 || !frm.doc.vehicle) {
		frm.__zp_letzter = null;
		setze_hinweis(frm, 'start_odometer');
		return Promise.resolve(null);
	}
	return frappe
		.call({
			method: 'zeit_projekt.fahrtenbuch.fahrtenbuch.get_letzter_stand',
			args: { vehicle: frm.doc.vehicle, fahrt: frm.is_new() ? null : frm.doc.name },
		})
		.then((r) => {
			frm.__zp_letzter = r.message || null;
			if (!(frm.__zp_unsicher && frm.__zp_unsicher.start_odometer)) setze_hinweis(frm, 'start_odometer');
			return frm.__zp_letzter;
		});
}

// Warntext, wenn der Startstand nicht zum letzten Stand des Fahrzeugs passt, sonst null.
function pruefe_startstand(frm, wert) {
	if (!wert || !frm.doc.vehicle) return Promise.resolve(null);
	return lade_letzten_stand(frm).then((l) => {
		if (!l) return null;
		const luecke = cint(knopf_einstellung.max_km_luecke);
		if (wert < l.stand) {
			return __('Startstand {0} liegt unter dem letzten Stand dieses Fahrzeugs ({1} km).', [wert, l.stand]);
		}
		if (luecke > 0 && wert - l.stand > luecke) {
			return __('Startstand {0} liegt {1} km über dem letzten Stand dieses Fahrzeugs ({2} km).', [
				wert,
				wert - l.stand,
				l.stand,
			]);
		}
		return null;
	});
}

// Neue Fahrt: das zuletzt genutzte Fahrzeug des Benutzers vorschlagen (Standardfahrzeug).
function fahrzeug_vorbelegen(frm) {
	if (!frm.is_new() || frm.doc.vehicle || frm.__zp_fahrzeug_geholt) return;
	frm.__zp_fahrzeug_geholt = true;
	frappe.call('zeit_projekt.fahrtenbuch.fahrtenbuch.get_letztes_fahrzeug').then((r) => {
		if (r.message && !frm.doc.vehicle) frm.set_value('vehicle', r.message);
	});
}

// Beschreibung eines Kilometerstand-Feldes ändern und später auf den
// ursprünglichen Text aus dem Doctype zurücksetzen (text weglassen).
const ursprungstexte = {};
function setze_hinweis(frm, fieldname, text) {
	const feld = frm.fields_dict[fieldname];
	if (!feld) return;
	if (!(fieldname in ursprungstexte)) ursprungstexte[fieldname] = feld.df.description;
	const standard = ursprungstexte[fieldname] + (fieldname === 'start_odometer' ? letzter_stand_text(frm) : '');
	frm.set_df_property(fieldname, 'description', text === undefined ? standard : text);
}

// Fotohilfe: was auf das Bild gehört, steht an den Foto-Feldern - die
// Erkennung liest sonst gern den Tageszähler (TRIP) statt des Gesamtstands.
function setze_foto_hinweise(frm) {
	const hinweis = __(
		'Foto vom Gesamt-Kilometerzähler (ODO) - nicht vom Tageszähler (TRIP) und nicht von der Temperatur. Zahl formatfüllend, ohne Spiegelung. Der Stand wird automatisch erkannt und kann danach jederzeit von Hand korrigiert werden.'
	);
	['start_odometer_photo', 'end_odometer_photo'].forEach((f) => frm.set_df_property(f, 'description', hinweis));
}

function zeige_erkennung(auftrag, data) {
	const frm = cur_frm;
	// Formular inzwischen verlassen, anderes Foto oder Wert schon von Hand
	// eingetragen? (Der Name einer neuen Fahrt ändert sich beim Speichern,
	// deshalb wird am Foto erkannt, ob es noch dieselbe Fahrt ist.)
	if (frm && frm.__zp_erkennung_laeuft) frm.__zp_erkennung_laeuft[auftrag.photo_field] = false;
	if (frm) entferne_status(frm, auftrag.photo_field);
	if (!frm || frm.doctype !== 'Fahrt' || frm.doc[auftrag.photo_field] !== auftrag.file_url) return;
	// Gar keine Antwort (zu langsam, Modell nicht erreichbar ...): ausdruecklich melden, statt
	// still "nicht erkannt" zu sagen - sonst wartet der Techniker auf etwas, das nicht kommt.
	if (data.fehler) {
		const texte = {
			timeout: __(
				'Zeitüberschreitung: Das Erkennungsmodell hat nicht innerhalb von {0} Sekunden geantwortet. Bitte den Kilometerstand von Hand eintragen.',
				[data.limit]
			),
			nicht_erreichbar: __('Das Erkennungsmodell ist nicht erreichbar oder hat einen Fehler gemeldet. Bitte den Kilometerstand von Hand eintragen.'),
			antwort_unlesbar: __('Die Antwort des Erkennungsmodells war nicht lesbar. Bitte den Kilometerstand von Hand eintragen.'),
			bild_unlesbar: __('Das Foto konnte nicht gelesen werden. Bitte den Kilometerstand von Hand eintragen.'),
			free_nur_in_opencode: __('Dieses kostenlose Modell darf der Anbieter nur innerhalb von OpenCode nutzen. Bitte ein anderes Modell einstellen und den Kilometerstand von Hand eintragen.'),
			zugang_abgelehnt: __('Die Erkennung wurde abgelehnt (API-Schlüssel oder Abo prüfen). Bitte den Kilometerstand von Hand eintragen.'),
			limit_erreicht: __('Das Nutzungslimit oder Guthaben der Erkennung ist erschöpft. Bitte den Kilometerstand von Hand eintragen.'),
			modell_ohne_bild: __('Das gewählte Modell kann keine Bilder lesen. Bitte ein anderes Modell einstellen und den Kilometerstand von Hand eintragen.'),
			modell_freigabe_noetig: __('Dieses Modell trainiert mit den gesendeten Daten und ist nicht freigegeben. Bitte ein anderes Modell einstellen und den Kilometerstand von Hand eintragen.'),
			modell_nicht_unterstuetzt: __('Das gewählte Modell wird von dieser Schnittstelle nicht unterstützt. Bitte ein anderes Modell einstellen und den Kilometerstand von Hand eintragen.'),
		};
		frappe.show_alert({ message: texte[data.fehler] || __('Die Erkennung ist fehlgeschlagen. Bitte den Kilometerstand von Hand eintragen.'), indicator: 'red' }, 20);
		return;
	}
	// Ein Endstand unter dem Startstand kann nicht stimmen (das Buchen würde ihn
	// ohnehin ablehnen) - dann lieber nichts eintragen als einen falschen Wert.
	if (
		data.reading &&
		data.fieldname === 'end_odometer' &&
		frm.doc.start_odometer &&
		data.reading < frm.doc.start_odometer
	) {
		frappe.show_alert({
			message: __('Erkannter Endstand {0} liegt unter dem Startstand {1}. Bitte manuell eintragen.', [
				data.reading,
				frm.doc.start_odometer,
			]),
			indicator: 'orange',
		});
	} else if (data.reading && !frm.doc[data.fieldname]) {
		frm.__zp_erkennung_setzt = true; // das Feld-Ereignis soll die Handeingabe-Pruefung auslassen
		frm.set_value(data.fieldname, data.reading).then(() => {
			frm.__zp_erkennung_setzt = false;
			if (data.unsicher) {
				// Die Modellantworten waren nicht einhellig: Wert eintragen, aber
				// sichtbar markieren, bis der Techniker ihn bestätigt oder ändert.
				setze_hinweis(frm, data.fieldname, __('Automatisch erkannt, aber nicht sicher - bitte mit dem Foto vergleichen.'));
				if (data.fieldname === 'start_odometer') {
					frm.__zp_unsicher = { ...frm.__zp_unsicher, start_odometer: true };
					update_timer_toolbar(frm); // "Foto Ende" bleibt aus, bis der Startstand bestaetigt ist
				}
				frappe.show_alert(
					{
						message: __('Kilometerstand erkannt: {0} - nicht sicher, bitte mit dem Foto vergleichen.', [data.reading]),
						indicator: 'orange',
					},
					10
				);
			} else {
				frappe.show_alert({ message: __('Kilometerstand erkannt: {0}', [data.reading]), indicator: 'green' });
			}
			// Erkannten Stand gleich speichern (nur Entwurf; gebuchte Fahrten bleiben unberuehrt).
			if (frm.doc.docstatus === 0 && frm.is_dirty()) frm.save().catch(() => {});
			// Passt der erkannte Startstand zum letzten Stand des Fahrzeugs? Sonst als fraglich
			// markieren (wie "nicht sicher"): "Foto Ende" bleibt aus, bis er bestaetigt oder geaendert ist.
			if (data.fieldname === 'start_odometer') {
				pruefe_startstand(frm, data.reading).then((warnung) => {
					if (!warnung) return;
					setze_hinweis(frm, 'start_odometer', warnung + ' ' + __('Bitte mit dem Foto vergleichen.') + letzter_stand_text(frm));
					frm.__zp_unsicher = { ...frm.__zp_unsicher, start_odometer: true };
					update_timer_toolbar(frm);
					frappe.show_alert({ message: warnung, indicator: 'orange' }, 15);
				});
			}
		}, () => (frm.__zp_erkennung_setzt = false));
	} else if (!data.reading) {
		frappe.show_alert({
			message: __('Konnte den Kilometerstand nicht erkennen, bitte manuell eintragen.'),
			indicator: 'orange',
		});
	}
}

function fetch_odometer_reading(frm, photo_field, odometer_field) {
	const file_url = frm.doc[photo_field];
	if (!file_url) return;

	frappe
		.call({
			method: 'zeit_projekt.fahrtenbuch.fahrtenbuch.get_odometer_reading',
			args: { file_url, fieldname: odometer_field },
		})
		.then((r) => {
			const res = r.message || {};
			if (!res.queued) {
				entferne_status(frm, photo_field); // Erkennung nicht eingerichtet
				return;
			}
			const auftrag = { photo_field, file_url, start: Date.now(), phase: { phase: 'warteschlange' } };
			offene_erkennungen[res.request_id] = auftrag;
			frm.__zp_erkennung_laeuft = { ...frm.__zp_erkennung_laeuft, [photo_field]: true };
			setze_status(frm, photo_field, __('Erkennung wartet in der Warteschlange …'), null);
			auftrag.takt = setInterval(() => aktualisiere_erkennungsstatus(auftrag), 1000);
		});
}


// Standort bei Beginn und Ende der Fahrt (nur diese beiden Zeitpunkte, keine
// laufende Aufzeichnung). Der Browser fragt den Standort beim ersten Mal
// selbst ab; ohne HTTPS, ohne Erlaubnis oder ohne Empfang bleibt die Karte
// einfach leer - die Fahrt ist trotzdem ganz normal buch- und speicherbar.
//
// Ausgeloest nicht an den Knoepfen, sondern bei jedem Oeffnen des Entwurfs,
// wenn Beginn bzw. Ende gerade erst gesetzt wurden (hoechstens 5 Minuten
// her) und dafuer noch kein Punkt vorliegt. So greift es fuer den Timer im
// Fahrt-Formular, den Knopf im Projekt und das Eintragen von Hand, ohne dass
// der Projekt-Knopf (project.js) etwas davon wissen muss. Alte Zeiten, die
// jemand nachtraeglich korrigiert, bekommen keinen Standort.
const STANDORT_MAX_ALTER_MIN = 5;

// Einstellung "Standort bei Beginn und Ende erfassen" (Fahrtenbuch
// Einstellungen, standardmaessig aus). Einmal je Seitenaufruf abgefragt; die
// Einstellungen selbst duerfen Techniker nicht lesen.
let standort_einstellung = null;

function standort_aktiv() {
	if (!standort_einstellung) {
		standort_einstellung = frappe
			.call('zeit_projekt.fahrtenbuch.fahrtenbuch.get_fahrt_defaults')
			.then((r) => !!(r.message && r.message.capture_location));
	}
	return standort_einstellung;
}

function standort_nachtragen(frm) {
	if (frm.doc.docstatus !== 0 || frm.is_new() || frm._standort_laeuft) return;
	if (!navigator.geolocation) return;
	standort_aktiv().then((aktiv) => {
		if (aktiv) standort_erfassen(frm);
	});
}

function standort_erfassen(frm) {
	if (frm._standort_laeuft) return;

	const karte = parse_standorte(frm.doc.route_map);
	for (const [art, feld] of [['start', 'start_time'], ['ende', 'end_time']]) {
		const zeit = frm.doc[feld];
		frm._standort_versucht = frm._standort_versucht || {};
		if (!zeit || frm._standort_versucht[art]) continue;
		if (karte.features.some((f) => f.properties && f.properties.art === art)) continue;
		const alter_min = (Date.now() - frappe.datetime.str_to_obj(zeit).getTime()) / 60000;
		if (alter_min < 0 || alter_min > STANDORT_MAX_ALTER_MIN) continue;

		frm._standort_laeuft = true;
		frm._standort_versucht[art] = true; // je Formular nur ein Versuch, auch bei Fehler
		navigator.geolocation.getCurrentPosition(
			(pos) => {
				const aktuell = parse_standorte(frm.doc.route_map);
				aktuell.features = aktuell.features.filter((f) => !(f.properties && f.properties.art === art));
				aktuell.features.push({
					type: 'Feature',
					properties: {
						art,
						zeit,
						genauigkeit_m: Math.round(pos.coords.accuracy),
					},
					geometry: { type: 'Point', coordinates: [pos.coords.longitude, pos.coords.latitude] },
				});
				frm.set_value('route_map', JSON.stringify(aktuell))
					.then(() => frm.save())
					.finally(() => (frm._standort_laeuft = false));
			},
			(err) => {
				frm._standort_laeuft = false;
				frappe.show_alert({
					message: __('Standort konnte nicht ermittelt werden ({0}). Die Fahrt ist trotzdem gespeichert.', [
						err.message || err.code,
					]),
					indicator: 'orange',
				});
			},
			{ enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 }
		);
		return; // jeweils nur ein Punkt pro Aufruf; der nachfolgende Save loest refresh erneut aus
	}
}

function parse_standorte(wert) {
	try {
		const fc = JSON.parse(wert || '');
		if (fc && fc.type === 'FeatureCollection' && Array.isArray(fc.features)) return fc;
	} catch (e) {
		// leer oder ungueltig: neu beginnen
	}
	return { type: 'FeatureCollection', features: [] };
}

// Zeit & Projekt: von mehreren Formularen genutzte Funktionen
window.zeit_projekt = window.zeit_projekt || {};

window.zeit_projekt.foto_aufnehmen = (frm, fieldname) => capture_photo_for_field(frm, fieldname);

function capture_photo_for_field(frm, fieldname) {
	// Nutzt Frappes eigene frappe.ui.Capture-Klasse direkt (dieselbe, die
	// auch der Kamera-Knopf im normalen Anhaenge-Dialog verwendet) statt des
	// vollen Datei-Upload-Dialogs - auf dem Handy oeffnet das sofort die
	// Kamera-App (kein Zwischenschritt), am Desktop den Webcam-Stream direkt.
	// Kein automatischer Fallback ohne Kamera (z. B. Desktop ohne Webcam):
	// frappe.ui.Capture zeigt dann selbst eine Fehlermeldung (options.error).
	const capture = new frappe.ui.Capture({ animate: false, error: true });
	capture.show();
	hide_and_cleanup_mobile_capture_input(capture);
	// Hinweis im Kamera-Dialog (Desktop/Webcam; auf dem Handy übernimmt die
	// Kamera-App, dort steht derselbe Text am Foto-Feld der Fahrt): Die
	// Erkennung liest sonst gern den Tageszähler statt des Gesamtstands.
	if (capture.dialog && capture.dialog.$body) {
		$('<div class="text-muted small" style="margin-bottom: 8px;"></div>')
			.text(
				__(
					'Bitte den Gesamt-Kilometerzähler (ODO) formatfüllend fotografieren - nicht den Tageszähler (TRIP) und nicht die Temperatur. Spiegelungen vermeiden.'
				)
			)
			.prependTo(capture.dialog.$body);
	}
	capture.submit((data_urls) => {
		if (!data_urls || !data_urls.length) return;
		upload_captured_image(frm, fieldname, data_urls[0]);
	});
}

function hide_and_cleanup_mobile_capture_input(capture) {
	// Workaround fuer einen Kern-Bug in frappe.ui.Capture (capture.js): auf
	// dem Handy haengt es ein <input type="file"> direkt an <body> und will
	// es per Klasse "visually-hidden" verstecken - die ist aber nur
	// innerhalb von ".awesomplete" definiert (siehe
	// scss/common/awesomeplete.scss) und greift hier ueberhaupt nicht. Beim
	// erfolgreichen Foto faellt das nicht auf, weil das Element im
	// onchange-Handler sofort wieder entfernt wird - bricht man den
	// Kamera-/Datei-Dialog aber ab, feuert kein "change"-Event, das Element
	// bleibt also nie entfernt UND sichtbar als kaputtes Formularfeld auf
	// der Seite stehen (genau das vom Nutzer beobachtete Bild).
	//
	// this.input existiert nur im Mobil-Pfad (show_for_mobile) und wird dort
	// synchron gesetzt, bevor click() das native Kamera-/Datei-Menue oeffnet
	// - direkt danach ist es also bereits verfuegbar.
	const input = capture.input;
	if (!input) return;

	Object.assign(input.style, {
		position: 'fixed',
		top: '-9999px',
		left: '-9999px',
		opacity: '0',
		pointerEvents: 'none',
	});

	const remove_if_cancelled = () => {
		window.removeEventListener('focus', remove_if_cancelled);
		// Verzoegert, weil der Fokus schon zurueck ist, bevor der Browser
		// files/onchange bei einer echten Auswahl fertig verarbeitet hat.
		setTimeout(() => {
			if (input.isConnected && !input.files.length) {
				input.remove();
			}
		}, 500);
	};
	window.addEventListener('focus', remove_if_cancelled, { once: true });
}

// Statuszeile direkt am Foto-Feld statt eines Fensters: blockiert nichts, das Formular bleibt
// bedienbar, und derselbe Platz zeigt nacheinander Upload, Speichern und Erkennung an.
// prozent = null -> Balken laeuft unbestimmt; farbe: 'info' | 'success' | 'danger'.
function setze_status(frm, fieldname, text, prozent, farbe, vorschau) {
	const control = frm.fields_dict[fieldname];
	if (!control) return;
	let zeile = $(frm.layout.wrapper).find(`.zp-status[data-feld="${fieldname}"]`);
	if (!zeile.length) {
		zeile = $(
			`<div class="zp-status" data-feld="${fieldname}" style="margin: 0 0 12px;">
				<div class="progress" style="height: 8px; margin-bottom: 4px;">
					<div class="progress-bar" role="progressbar"></div>
				</div>
				<div class="zp-status-text small"></div>
			</div>`
		).insertBefore($(control.wrapper));
	}
	const balken = zeile.find('.progress-bar');
	balken
		.removeClass('bg-info bg-success bg-danger bg-warning progress-bar-striped progress-bar-animated')
		.addClass(`bg-${farbe || 'info'}`)
		.css('width', prozent == null ? '100%' : `${prozent}%`);
	if (prozent == null) balken.addClass('progress-bar-striped progress-bar-animated');
	zeile.find('.zp-status-text').text(text);
	// Vorschau des wartenden Fotos (Blob), damit man sieht, dass es noch da ist
	zeile.find('.zp-vorschau').remove();
	if (vorschau) {
		$('<img class="zp-vorschau" alt="">')
			.attr('src', URL.createObjectURL(vorschau))
			.css({ maxHeight: '90px', maxWidth: '100%', borderRadius: '6px', marginTop: '6px', display: 'block' })
			.appendTo(zeile);
	}
}

function entferne_status(frm, fieldname) {
	$(frm.layout.wrapper).find(`.zp-status[data-feld="${fieldname}"]`).remove();
}

// Beim Oeffnen einer Fahrt zeigen, welche Fotos noch auf Verbindung warten (sonst sieht es nach dem
// Neuladen so aus, als waere das Foto weg - es liegt aber sicher im Browser).
function zeige_wartende_fotos(frm) {
	if (frm.doc.docstatus !== 0) return;
	window.zeit_projekt.foto_warteschlange
		.alle()
		.then((liste) =>
			liste
				.filter(
					(e) =>
						e.doctype === frm.doctype &&
						!frm.doc[e.fieldname] &&
						(e.docname ? e.docname === frm.doc.name : true)
				)
				.forEach((e) =>
					setze_status(
						frm,
						e.fieldname,
						__('Foto von {0} wartet auf Verbindung und wird automatisch gesendet.', [
							new Date(e.angelegt).toLocaleTimeString(),
						]),
						100,
						'warning',
						e.blob
					)
				)
		)
		.catch(() => {});
}

// Ein aus der Warteschlange gesendetes Foto der Fahrt zuordnen. Ist die Fahrt gerade offen,
// laeuft alles wie beim normalen Upload (Speichern, Erkennung, Statuszeile). Sonst wird das Foto
// serverseitig am Entwurf eingetragen; eine Fahrt, die offline noch gar nicht angelegt war,
// bekommt es nur, wenn sie offen ist oder der juengste eigene Entwurf das Feld noch leer hat.
function foto_zuordnen(eintrag, file_url) {
	const frm = cur_frm;
	const feld = eintrag.fieldname;
	if (
		frm &&
		frm.doctype === eintrag.doctype &&
		frm.doc.docstatus === 0 &&
		!frm.doc[feld] &&
		(eintrag.docname ? frm.doc.name === eintrag.docname : true)
	) {
		return frm.set_value(feld, file_url).then(() => frm.save());
	}
	const setze = (name) =>
		frappe
			.call('frappe.client.set_value', { doctype: eintrag.doctype, name, fieldname: feld, value: file_url })
			.then(() =>
				frappe.show_alert(
					{
						message: __('Wartendes Foto an {0} angehängt. Bitte den Kilometerstand beim Öffnen prüfen oder eintragen.', [name]),
						indicator: 'green',
					},
					12
				)
			);
	if (eintrag.docname) return setze(eintrag.docname);
	return frappe.db
		.get_list(eintrag.doctype, {
			filters: { owner: frappe.session.user, docstatus: 0, [feld]: ['is', 'not set'] },
			fields: ['name'],
			order_by: 'creation desc',
			limit: 1,
		})
		.then((liste) => {
			if (liste && liste.length) return setze(liste[0].name);
			frappe.show_alert(
				{ message: __('Ein wartendes Foto wurde hochgeladen, konnte aber keiner Fahrt zugeordnet werden.'), indicator: 'orange' },
				20
			);
		});
}

// Foto (Data-URL der Kamera) in eine Datei umwandeln - ohne fetch(), das offline haengen koennte.
function data_url_zu_blob(data_url) {
	const [kopf, daten] = data_url.split(',');
	const typ = (kopf.match(/:(.*?)[;,]/) || [])[1] || 'image/jpeg';
	if (!/;base64/.test(kopf)) return new Blob([decodeURIComponent(daten)], { type: typ });
	const roh = atob(daten);
	const bytes = new Uint8Array(roh.length);
	for (let i = 0; i < roh.length; i++) bytes[i] = roh.charCodeAt(i);
	return new Blob([bytes], { type: typ });
}

function upload_captured_image(frm, fieldname, data_url) {
	const filename = `kilometerstand_${frappe.datetime
		.now_datetime()
		.replace(/[: -]/g, '_')}.jpg`;

	let foto_blob = null;
	// Netzfehler (kein Empfang, Gateway nicht erreichbar): Foto im Browser aufheben und spaeter senden
	const netzfehler = (e) => !!e && (e.netz || !navigator.onLine);
	const in_warteschlange = () =>
		window.zeit_projekt.foto_warteschlange
			.ablegen({
				doctype: frm.doctype,
				docname: frm.is_new() ? null : frm.doc.name,
				fieldname,
				filename,
				blob: foto_blob,
				angelegt: Date.now(),
			})
			.then(() => window.zeit_projekt.foto_warteschlange.anzahl())
			.then((n) => {
				setze_status(
					frm,
					__('Kein Netz – das Foto ist gespeichert und wird automatisch gesendet, sobald wieder Verbindung besteht – auch nach einem Neuladen der Seite ({0} wartend).', [n]),
					100,
					'warning',
					foto_blob
				);
				window.zeit_projekt.foto_warteschlange.starte_takt();
			});
	const fehler = (e) => {
		if (netzfehler(e) && foto_blob) {
			return in_warteschlange().catch(() => fehler_anzeigen());
		}
		fehler_anzeigen();
	};
	const fehler_anzeigen = () => {
		setze_status(frm, fieldname, __('Foto konnte nicht hochgeladen werden.'), 100, 'danger');
		setTimeout(() => entferne_status(frm, fieldname), 15000);
	};
	setze_status(frm, fieldname, __('Foto wird vorbereitet …'), null);

	Promise.resolve()
		.then(() => data_url_zu_blob(data_url))
		.then(
			(blob) =>
				new Promise((resolve, reject) => {
					foto_blob = blob;
					// Offline (Flugmodus, kein Empfang): gar nicht erst senden - ein Upload ohne Netz
					// kann lange haengen, statt sofort zu scheitern.
					if (!navigator.onLine) return reject({ netz: true });
					const form_data = new FormData();
					form_data.append('file', blob, filename);
					form_data.append('is_private', 1);
					form_data.append('folder', 'Home');
					form_data.append('doctype', frm.doctype);
					if (!frm.is_new()) {
						form_data.append('docname', frm.doc.name);
					}
					form_data.append('fieldname', fieldname);

					const xhr = new XMLHttpRequest();
					xhr.open('POST', '/api/method/upload_file');
					xhr.timeout = 90000; // haengende Verbindung (schlechtes Netz) -> Warteschlange
					xhr.setRequestHeader('X-Frappe-CSRF-Token', frappe.csrf_token);
					xhr.upload.onprogress = (e) => {
						if (!e.lengthComputable) return;
						const prozent = Math.round((100 * e.loaded) / e.total);
						const mb = (n) => (n / 1048576).toFixed(1);
						setze_status(
							frm,
							fieldname,
							__('Foto wird hochgeladen: {0} von {1} MB ({2} %)', [mb(e.loaded), mb(e.total), prozent]),
							prozent
						);
					};
					xhr.upload.onload = () => setze_status(frm, fieldname, __('Foto wird gespeichert …'), null);
					xhr.onload = () => {
						try {
							// 0 und Gateway-Fehler: keine Verbindung zum Server -> spaeter erneut senden
							if ([0, 502, 503, 504].includes(xhr.status)) return reject({ netz: true });
							if (xhr.status < 200 || xhr.status >= 300) return reject(new Error(xhr.status));
							resolve(JSON.parse(xhr.responseText));
						} catch (e) {
							reject(e);
						}
					};
					xhr.onerror = () => reject({ netz: true });
					xhr.ontimeout = () => reject({ netz: true });
					const offline = () => xhr.abort();
					window.addEventListener('offline', offline, { once: true });
					xhr.onabort = () => reject({ netz: true });
					xhr.onloadend = () => window.removeEventListener('offline', offline);
					xhr.send(form_data);
				})
		)
		.then((result) => {
			if (result && result.message && result.message.file_url) {
				// Die Erkennung (fetch_odometer_reading) uebernimmt die Statuszeile; ist sie nicht
				// eingerichtet, verschwindet sie hier nach kurzer Bestaetigung.
				setze_status(frm, fieldname, __('Foto hochgeladen.'), 100, 'success');
				setTimeout(() => {
					if (!frm.__zp_erkennung_laeuft || !frm.__zp_erkennung_laeuft[fieldname]) entferne_status(frm, fieldname);
				}, 4000);
				// Foto sofort mitspeichern (nur Entwurf): sonst steht es nur im offenen Formular und
				// ist weg, wenn die Erkennung nichts findet und die Seite neu geladen wird.
				frm.set_value(fieldname, result.message.file_url).then(() => {
					if (frm.doc.docstatus === 0 && frm.is_dirty()) frm.save().catch(() => {});
				});
			} else {
				fehler();
			}
		})
		.catch(fehler);
}

// Eigener Mitarbeiter: Name und Freigabe der Selbstanlage liefert der Server (auch ohne
// Leserecht auf Employee). Gibt es keinen und ist die Selbstanlage erlaubt, erscheint der
// Knopf "Mich als Mitarbeiter anlegen" (Fragebogen). Der Mitarbeiter ist freiwillig - der
// Knopf ist nur ein Angebot, kein Muss.
function mitarbeiter_pruefen(frm) {
	if (frm.doc.docstatus !== 0) return;
	const zeige = (status) => {
		if (status.employee) {
			$(frm.layout.wrapper).find('.zp-mitarbeiter-knopf').remove();
			if (frm.is_new() && !frm.doc.employee) frm.set_value('employee', status.employee);
			return;
		}
		$(frm.layout.wrapper).find('.zp-mitarbeiter-knopf').remove();
		if (!status.self_service) return;
		const oeffnen = () =>
			frappe.require('/assets/zeit_projekt/js/mitarbeiter_fragebogen.js', () =>
				window.zeit_projekt.mitarbeiter_fragebogen()
			);
		// Am Handy verschwinden normale Knoepfe im "..."-Menue - deshalb gut sichtbar im Formular
		$('<button type="button" class="btn btn-warning btn-lg zp-mitarbeiter-knopf"></button>')
			.text(__('Mich als Mitarbeiter anlegen'))
			.css({ display: 'block', width: 'min(100%, 480px)', minHeight: '64px', fontSize: '1.4rem', fontWeight: '600', margin: '12px 0 16px' })
			.on('click', oeffnen)
			.prependTo($(frm.layout.wrapper));
	};
	if (frm.__mitarbeiter_status) return zeige(frm.__mitarbeiter_status);
	frappe
		.call('zeit_projekt.zeit_projekt.technician.get_employee_status')
		.then((r) => {
			frm.__mitarbeiter_status = r.message || {};
			zeige(frm.__mitarbeiter_status);
		})
		.catch(() => {});
}
