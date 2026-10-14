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
		const employee_geladen = frm.doc.employee
			? Promise.resolve()
			: frappe.db
					.get_value('Employee', { user_id: frappe.session.user, status: 'Active' }, 'name')
					.then((r) => {
						if (r.message && r.message.name) frm.set_value('employee', r.message.name);
					})
					.catch(() => {});
		const defaults_geladen = frappe.call('zeit_projekt.fahrtenbuch.fahrtenbuch.get_fahrt_defaults').then((r) => {
			const d = r.message || {};
			if (d.activity_type && !frm.doc.activity_type) frm.set_value('activity_type', d.activity_type);
			if (d.km_item && !frm.doc.km_item) frm.set_value('km_item', d.km_item);
		});

		// Kam das Formular vom Knopf "Neu mit Timer und Kamera" (fahrt_list.js)? Dann nach
		// dem Laden von Mitarbeiter und Vorbelegung Timer und Kamera starten.
		const wunsch = window.zeit_projekt && window.zeit_projekt.neu_mit_timer_kamera;
		if (window.zeit_projekt) window.zeit_projekt.neu_mit_timer_kamera = null;
		if (wunsch && Date.now() - wunsch < 15000 && !frm.doc.start_time) {
			Promise.all([employee_geladen, defaults_geladen]).then(() => {
				// onload laeuft noch vor dem fertigen Aufbau des Formulars: erst danach speichern
				setTimeout(() => timer_und_kamera_starten(frm), 400);
			});
		}
		// Sonst kein automatischer Default fuer start_time - das uebernimmt der
		// Timer (oder die manuelle Eingabe). Ein Default beim Oeffnen wuerde den
		// falschen Zeitpunkt festlegen, falls der Techniker erst spaeter losfaehrt.
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
		fetch_odometer_reading(frm, 'start_odometer_photo', 'start_odometer');
	},

	end_odometer_photo(frm) {
		fetch_odometer_reading(frm, 'end_odometer_photo', 'end_odometer');
	},

	// Ändert der Techniker einen erkannten Wert, ist die "nicht sicher"-Markierung erledigt.
	start_odometer(frm) {
		setze_hinweis(frm, 'start_odometer');
	},

	end_odometer(frm) {
		setze_hinweis(frm, 'end_odometer');
	},

	refresh(frm) {
		frm.dashboard.clear_headline();
		setze_foto_hinweise(frm);
		update_timer_toolbar(frm);
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
function update_timer_toolbar(frm) {
	stop_ticking(frm);
	entferne_timer_knopf(frm);
	if (frm.doc.docstatus !== 0) return;

	if (!frm.doc.start_time) {
		zeige_timer_knopf(frm, __('Timer starten'), 'btn-primary', () => {
			frm.set_value('start_time', frappe.datetime.now_datetime()).then(() => frm.save());
		});
	} else if (!frm.doc.end_time) {
		zeige_timer_knopf(frm, __('Timer stoppen'), 'btn-danger', () => {
			frm.set_value('end_time', frappe.datetime.now_datetime()).then(() => frm.save());
		});
		start_ticking(frm);
	}
}

// Grosser Knopf oben im Formular statt eines kleinen in der Kopfzeile: gerade am Handy
// ist der wichtigste Knopf der Fahrt sonst leicht zu uebersehen und zu klein zum Treffen.
// Auf dem Handy bildschirmbreit, am Desktop auf 480 px begrenzt.
function zeige_timer_knopf(frm, text, klasse, aktion) {
	const knopf = $(`<button type="button" class="btn ${klasse} btn-lg zp-timer-knopf"></button>`)
		.text(text)
		.css({
			display: 'block',
			width: 'min(100%, 480px)',
			minHeight: '64px',
			margin: '12px 0 16px',
			fontSize: '1.4rem',
			fontWeight: '600',
		})
		.on('click', function () {
			const el = $(this);
			el.prop('disabled', true); // kein Doppelklick: sonst zweimal gespeichert
			// Scheitert das Speichern (z. B. an einer Pruefung), den Knopf wieder freigeben
			Promise.resolve(aktion()).finally(() => el.prop('disabled', false));
		});
	$(frm.layout.wrapper).prepend(knopf);
}

function entferne_timer_knopf(frm) {
	$(frm.layout.wrapper).find('.zp-timer-knopf').remove();
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

// Kilometerstand-Erkennung läuft als Hintergrund-Job (bis zu 45 s) - das
// Formular bleibt bedienbar, das Ergebnis kommt per Realtime-Event zurück.
// Global statt im Skript-Scope: das Formular-Skript kann mehrfach ausgeführt
// werden, der Realtime-Listener soll trotzdem nur einmal existieren.
window.zeit_projekt_ocr = window.zeit_projekt_ocr || { offen: {}, listener: false };
const offene_erkennungen = window.zeit_projekt_ocr.offen;

if (!window.zeit_projekt_ocr.listener) {
	window.zeit_projekt_ocr.listener = true;
	frappe.realtime.on('zeit_projekt_odometer', (data) => {
		const auftrag = window.zeit_projekt_ocr.offen[data.request_id];
		if (!auftrag) return;
		delete window.zeit_projekt_ocr.offen[data.request_id];
		zeige_erkennung(auftrag, data);
	});
}

// Beschreibung eines Kilometerstand-Feldes ändern und später auf den
// ursprünglichen Text aus dem Doctype zurücksetzen (text weglassen).
const ursprungstexte = {};
function setze_hinweis(frm, fieldname, text) {
	const feld = frm.fields_dict[fieldname];
	if (!feld) return;
	if (!(fieldname in ursprungstexte)) ursprungstexte[fieldname] = feld.df.description;
	frm.set_df_property(fieldname, 'description', text === undefined ? ursprungstexte[fieldname] : text);
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
	if (!frm || frm.doctype !== 'Fahrt' || frm.doc[auftrag.photo_field] !== auftrag.file_url) return;
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
		frm.set_value(data.fieldname, data.reading).then(() => {
			if (data.unsicher) {
				// Die Modellantworten waren nicht einhellig: Wert eintragen, aber
				// sichtbar markieren, bis der Techniker ihn bestätigt oder ändert.
				setze_hinweis(frm, data.fieldname, __('Automatisch erkannt, aber nicht sicher - bitte mit dem Foto vergleichen.'));
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
		});
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
			if (!res.queued) return; // Erkennung nicht eingerichtet
			offene_erkennungen[res.request_id] = { photo_field, file_url };
			frappe.show_alert({ message: __('Kilometerstand wird im Hintergrund erkannt …'), indicator: 'blue' });
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

// Startzeit auf jetzt setzen, sofort speichern (eine neue, ungespeicherte Fahrt ginge
// beim Schliessen der Seite verloren) und die Kamera fuer das Start-Kilometerstand-Foto
// oeffnen. Ausgeloest vom Knopf "Neu mit Timer und Kamera" in der Fahrten-Liste -
// bewusst immer beides, unabhaengig von den Einstellungen fuer den Projekt-Knopf.
function timer_und_kamera_starten(frm) {
	frm.set_value('start_time', frappe.datetime.now_datetime())
		.then(() => frm.save())
		.then(() => capture_photo_for_field(frm, 'start_odometer_photo'))
		.catch(() => {
			// Speichern fehlgeschlagen: Frappe zeigt den Grund selbst an.
		});
}

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

function upload_captured_image(frm, fieldname, data_url) {
	const filename = `kilometerstand_${frappe.datetime
		.now_datetime()
		.replace(/[: -]/g, '_')}.jpg`;

	fetch(data_url)
		.then((res) => res.blob())
		.then((blob) => {
			const form_data = new FormData();
			form_data.append('file', blob, filename);
			form_data.append('is_private', 1);
			form_data.append('folder', 'Home');
			form_data.append('doctype', frm.doctype);
			if (!frm.is_new()) {
				form_data.append('docname', frm.doc.name);
			}
			form_data.append('fieldname', fieldname);

			return fetch('/api/method/upload_file', {
				method: 'POST',
				headers: { 'X-Frappe-CSRF-Token': frappe.csrf_token },
				body: form_data,
			});
		})
		.then((response) => response.json())
		.then((result) => {
			if (result && result.message && result.message.file_url) {
				frm.set_value(fieldname, result.message.file_url);
			}
		})
		.catch(() => {
			frappe.show_alert({
				message: __('Foto konnte nicht hochgeladen werden.'),
				indicator: 'red',
			});
		});
}
