// Zeiten aus der Zeiterfassung und Fahrt-Kilometer als Einzelpositionen in die
// Ausgangsrechnung importieren. Ausgeliefert über hooks.py -> doctype_js.

(function () {
	const API = 'zeit_projekt.zeit_projekt.sales_invoice.get_billable_time_logs';

	function zeit_import_dialog(frm) {
		if (!frm.doc.customer) {
			frappe.msgprint(__('Bitte zuerst den Kunden der Rechnung wählen – importiert werden nur dessen Zeiten.'));
			return;
		}
		const heute = frappe.datetime.get_today();
		const dlg = new frappe.ui.Dialog({
			title: __('Zeiten aus Zeiterfassung importieren'),
			fields: [
				{ fieldname: 'from_date', fieldtype: 'Date', label: __('Von (Datum)'), reqd: 1, default: frappe.datetime.add_months(heute, -12) },
				{ fieldname: 'to_date', fieldtype: 'Date', label: __('Bis (Datum)'), reqd: 1, default: heute },
				{
					fieldname: 'project', fieldtype: 'Link', options: 'Project', label: __('Projekt'), default: frm.doc.project,
					get_query: () => ({ filters: { customer: frm.doc.customer } }),
				},
				{ fieldname: 'fallback_item', fieldtype: 'Link', options: 'Item', label: __('Ersatz-Artikel (nur für Aktivitätsarten ohne Dienstleistungsartikel)') },
				// Standard aus: ein versehentlicher Import soll keine bestehenden Positionen löschen
				{ fieldname: 'replace', fieldtype: 'Check', label: __('Vorhandene Positionen ersetzen'), default: 0 },
			],
			primary_action_label: __('Importieren'),
			primary_action(v) {
				dlg.hide();
				zeiten_importieren(frm, v);
			},
		});
		dlg.show();
	}

	async function zeiten_importieren(frm, v) {
		frappe.dom.freeze(__('Zeiten werden importiert …'));
		try {
			let cfg = {};
			try {
				const cfg_r = await frappe.call({
					method: 'zeit_projekt.zeit_projekt.doctype.zeit_projekt_einstellungen.zeit_projekt_einstellungen.get_einstellungen',
				});
				cfg = cfg_r.message || {};
			} catch (e) {
				console.error(e);
			}
			const bez_modus = cfg.positionsbezeichnung || 'Nur Datum und Uhrzeit';
			const termin_ende = (cfg.lieferdatum_quelle || '').indexOf('Ende') === 0;

			// Nur Zeiten und Fahrten des Rechnungskunden
			const r = await frappe.call({
				method: API,
				args: {
					customer: frm.doc.customer,
					project: v.project || undefined,
					from_time: v.from_date + ' 00:00:00',
					to_time: v.to_date + ' 23:59:59',
				},
			});
			const antwort = r.message || {};
			const uebersprungen = antwort.skipped || 0;

			// Bereits in dieser Rechnung stehende Zeiten/Fahrten nicht doppelt übernehmen
			const schon_zeiten = new Set((frm.doc.timesheets || []).map((t) => t.timesheet_detail));
			const schon_fahrten = new Set((frm.doc.items || []).map((i) => i.custom_fahrt).filter(Boolean));
			const zeiten = v.replace ? antwort.rows || [] : (antwort.rows || []).filter((t) => !schon_zeiten.has(t.name));
			const fahrten = v.replace
				? antwort.kilometers || []
				: (antwort.kilometers || []).filter((f) => !schon_fahrten.has(f.name));

			if (!zeiten.length && !fahrten.length) {
				frappe.dom.unfreeze();
				let msg = __('Im gewählten Zeitraum gibt es für diesen Kunden keine abrechenbaren, noch nicht abgerechneten Zeiten oder Kilometer.');
				if (uebersprungen) {
					msg += ' ' + __('{0} Zeiten anderer Kunden bzw. ohne Kunde/Projekt wurden ausgelassen.', [uebersprungen]);
				}
				frappe.msgprint({ title: __('Nichts zu importieren'), indicator: 'orange', message: msg });
				return;
			}

			// Aktivitätsarten mit Zuordnung laden
			const arten = [...new Set(zeiten.map((t) => t.activity_type).filter(Boolean))];
			const at_map = {};
			if (arten.length) {
				const at_liste = await frappe.db.get_list('Activity Type', {
					filters: { name: ['in', arten] },
					fields: ['name', 'custom_dienstleistungsartikel', 'custom_rechnungstext', 'billing_rate'],
					limit: 0,
				});
				at_liste.forEach((a) => (at_map[a.name] = a));
			}

			// Positionen vorbereiten. Die Zeitblatt-Tabelle nur beim Ersetzen
			// leeren: timesheet_detail ist der Schlüssel, über den ERPNext die
			// Zeiten nach dem Buchen als abgerechnet markiert.
			if (v.replace) {
				frm.clear_table('items');
				frm.clear_table('timesheets');
			} else {
				(frm.doc.items || []).slice().forEach((d) => {
					if (!d.item_code && !d.item_name && !d.qty) {
						frm.get_field('items').grid.grid_rows_by_docname[d.name].remove();
					}
				});
			}
			zeiten.forEach((t) => {
				frm.add_child('timesheets', {
					activity_type: t.activity_type,
					description: t.description,
					time_sheet: t.time_sheet,
					from_time: t.from_time,
					to_time: t.to_time,
					billing_hours: t.billing_hours,
					billing_amount: t.billing_amount,
					timesheet_detail: t.name,
					project_name: t.project_name,
				});
			});
			frm.refresh_field('timesheets');

			const ohne_artikel = [];
			const ohne_preis = [];
			let quelle_artikel = 0;
			let quelle_aktivitaet = 0;
			const termine = [];

			for (const t of zeiten) {
				const art = at_map[t.activity_type] || {};
				const hat_artikel = !!art.custom_dienstleistungsartikel;
				const artikel = art.custom_dienstleistungsartikel || v.fallback_item;
				if (!artikel) {
					ohne_artikel.push(__(t.activity_type || '?'));
					continue;
				}
				const row = frm.add_child('items', {});
				await frappe.model.set_value(row.doctype, row.name, 'item_code', artikel);
				await frappe.model.set_value(row.doctype, row.name, 'qty', flt(t.billing_hours) || 1);

				// Satz der Aktivitätsart (nur Fallback)
				let akt_satz = 0;
				if (flt(t.billing_hours) && flt(t.billing_amount)) {
					akt_satz = flt(t.billing_amount) / flt(t.billing_hours);
				} else if (flt(art.billing_rate)) {
					akt_satz = flt(art.billing_rate);
				}

				const zeile = locals[row.doctype][row.name];
				const artikel_preis = flt(zeile.price_list_rate) || flt(zeile.rate);

				if (hat_artikel && artikel_preis) {
					// Preis des Artikels gewinnt - Satz der Aktivitätsart wird ignoriert
					quelle_artikel += 1;
					if (flt(zeile.rate) !== artikel_preis) {
						await frappe.model.set_value(row.doctype, row.name, 'rate', artikel_preis);
					}
				} else if (akt_satz) {
					// Kein Artikel verknüpft bzw. kein Artikelpreis vorhanden
					quelle_aktivitaet += 1;
					await frappe.model.set_value(row.doctype, row.name, 'rate', akt_satz);
				} else {
					ohne_preis.push(t.time_sheet + ' (' + __(t.activity_type || '?') + ')');
				}

				// Beschreibung: erste Zeile je nach Einstellung
				let bez = '';
				if (bez_modus.indexOf('Aktivit') === 0) {
					bez = __(t.activity_type || '');
				} else if (bez_modus.indexOf('Bezeichnung') === 0) {
					bez = art.custom_rechnungstext || __(t.activity_type || '');
				}

				let zeit = '';
				if (t.from_time) {
					zeit = __('{0} {1}-{2} Uhr', [
						frappe.datetime.str_to_user(t.from_time).split(' ')[0],
						(t.from_time || '').substr(11, 5),
						(t.to_time || '').substr(11, 5),
					]);
				}

				let text = bez && zeit ? bez + ' – ' + zeit : bez || zeit;
				if (t.description) {
					text = text ? text + '<br>' + t.description : t.description;
				}
				if (text) {
					await frappe.model.set_value(row.doctype, row.name, 'description', text);
				}

				const termin = termin_ende ? t.to_time || t.from_time || '' : t.from_time || '';
				termine.push([row.name, termin.substr(0, 10)]);
			}

			// Kilometer aus Fahrten: Artikel und Menge aus der Fahrt, Preis aus der
			// Preisliste. custom_fahrt markiert die Fahrt beim Buchen als abgerechnet.
			let km_zeilen = 0;
			for (const f of fahrten) {
				const row = frm.add_child('items', {});
				await frappe.model.set_value(row.doctype, row.name, 'item_code', f.km_item);
				await frappe.model.set_value(row.doctype, row.name, 'qty', flt(f.distance_km));
				await frappe.model.set_value(row.doctype, row.name, 'description', f.description);
				await frappe.model.set_value(row.doctype, row.name, 'custom_fahrt', f.name);
				if (!flt(locals[row.doctype][row.name].rate)) {
					ohne_preis.push(f.name + ' (' + f.km_item + ')');
				}
				termine.push([row.name, f.date]);
				km_zeilen += 1;
			}

			// Zweiter Durchgang: Liefertermin setzen (nur wirksam, wenn die
			// Rechnungsposition ein Feld delivery_date hat). Beim Setzen des
			// Artikels holt ERPNext die Artikel-Standards und überschreibt ihn.
			for (const [name, datum] of termine) {
				if (datum) {
					await frappe.model.set_value('Sales Invoice Item', name, 'delivery_date', datum);
				}
			}

			frm.refresh_field('items');
			if (frm.cscript && frm.cscript.calculate_taxes_and_totals) {
				frm.cscript.calculate_taxes_and_totals();
			}
			frappe.dom.unfreeze();

			const hinweise = [];
			if (uebersprungen) {
				hinweise.push(__('{0} Zeiten anderer Kunden bzw. ohne Kunde/Projekt wurden nicht übernommen.', [uebersprungen]));
			}
			if (ohne_artikel.length) {
				hinweise.push(
					__('<b>Kein Dienstleistungsartikel hinterlegt</b> für: {0}. Diese Zeiten wurden nicht als Position übernommen. Bitte in der Aktivitätsart einen Dienstleistungsartikel eintragen oder beim Import einen Ersatz-Artikel wählen.', [
						[...new Set(ohne_artikel)].join(', '),
					])
				);
			}
			if (ohne_preis.length) {
				hinweise.push(
					__('<b>Kein Preis gefunden</b> für: {0}. Bitte Verkaufspreis des Artikels bzw. Stundensatz der Aktivitätsart prüfen.', [
						[...new Set(ohne_preis)].join(', '),
					])
				);
			}
			if (hinweise.length) {
				frappe.msgprint({ title: __('Bitte prüfen'), indicator: 'orange', message: hinweise.join('<br><br>') });
			}

			const quellen = [];
			if (quelle_artikel) quellen.push(__('{0}× Artikelpreis', [quelle_artikel]));
			if (quelle_aktivitaet) quellen.push(__('{0}× Satz der Aktivitätsart', [quelle_aktivitaet]));
			if (km_zeilen) quellen.push(__('{0}× Kilometer', [km_zeilen]));
			frappe.show_alert(
				{
					message:
						__('{0} Positionen übernommen', [quelle_artikel + quelle_aktivitaet + km_zeilen]) +
						(quellen.length ? ' (' + quellen.join(', ') + ')' : ''),
					indicator: 'green',
				},
				7
			);
		} catch (e) {
			frappe.dom.unfreeze();
			console.error(e);
			frappe.msgprint({ title: __('Fehler beim Import'), indicator: 'red', message: (e && e.message) || String(e) });
		}
	}

	frappe.ui.form.on('Sales Invoice', {
		refresh(frm) {
			if (frm.doc.docstatus !== 0) return;
			frm.add_custom_button(__('Zeiten aus Zeiterfassung importieren'), () => zeit_import_dialog(frm));
		},
	});
})();
