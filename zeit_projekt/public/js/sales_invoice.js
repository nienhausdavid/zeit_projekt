// Zeiten aus der Zeiterfassung als Einzelpositionen in die Ausgangsrechnung importieren.
// Ausgeliefert ueber hooks.py -> doctype_js. Kein Client Script noetig.

(function () {
	function zeit_import_dialog(frm) {
		var heute = frappe.datetime.get_today();
		var dlg = new frappe.ui.Dialog({
			title: 'Zeiten aus Zeiterfassung importieren',
			fields: [
				{ fieldname: 'from_date', fieldtype: 'Date', label: 'Von (Datum)', reqd: 1, default: frappe.datetime.add_months(heute, -12) },
				{ fieldname: 'to_date', fieldtype: 'Date', label: 'Bis (Datum)', reqd: 1, default: heute },
				{ fieldname: 'project', fieldtype: 'Link', options: 'Project', label: 'Projekt', default: frm.doc.project },
				{ fieldname: 'fallback_item', fieldtype: 'Link', options: 'Item', label: 'Ersatz-Artikel (nur fuer Aktivitaetsarten ohne Dienstleistungsartikel)' },
				{ fieldname: 'replace', fieldtype: 'Check', label: 'Vorhandene Positionen ersetzen', default: 1 }
			],
			primary_action_label: 'Importieren',
			primary_action: function (v) {
				dlg.hide();
				zeiten_importieren(frm, v);
			}
		});
		dlg.show();
	}

	async function zeiten_importieren(frm, v) {
		frappe.dom.freeze('Zeiten werden importiert ...');
		try {
			// Einstellungen (Zeit Projekt Einstellungen) laden
			var cfg = {};
			try {
				var cfg_r = await frappe.call({
					method: 'zeit_projekt.zeit_projekt.doctype.zeit_projekt_einstellungen.zeit_projekt_einstellungen.get_einstellungen'
				});
				cfg = cfg_r.message || {};
			} catch (e) { console.error(e); }
			var bez_modus = cfg.positionsbezeichnung || 'Nur Datum und Uhrzeit';
			var termin_ende = (cfg.lieferdatum_quelle || '').indexOf('Ende') === 0;

			var r = await frappe.call({
				method: 'erpnext.projects.doctype.timesheet.timesheet.get_projectwise_timesheet_data',
				args: {
					project: v.project || undefined,
					from_time: v.from_date + ' 00:00:00',
					to_time: v.to_date + ' 23:59:59'
				}
			});
			var zeiten = r.message || [];
			if (!zeiten.length) {
				frappe.dom.unfreeze();
				frappe.msgprint({
					title: 'Keine Zeiten gefunden', indicator: 'orange',
					message: 'Im gewaehlten Zeitraum gibt es keine abrechenbaren, noch nicht abgerechneten Zeiterfassungen.'
				});
				return;
			}

			// Aktivitaetsarten mit Zuordnung laden
			var arten = [...new Set(zeiten.map(function (t) { return t.activity_type; }).filter(Boolean))];
			var at_liste = await frappe.db.get_list('Activity Type', {
				filters: { name: ['in', arten] },
				fields: ['name', 'custom_dienstleistungsartikel', 'custom_rechnungstext', 'billing_rate'],
				limit: 0
			});
			var at_map = {};
			at_liste.forEach(function (a) { at_map[a.name] = a; });

			// Zeitblatt-Tabelle neu aufbauen. Das Feld timesheet_detail ist der
			// Schluessel, ueber den ERPNext die Zeiten nach dem Buchen als
			// abgerechnet markiert - ohne ihn koennten sie erneut fakturiert werden.
			frm.clear_table('timesheets');
			zeiten.forEach(function (t) {
				frm.add_child('timesheets', {
					activity_type: t.activity_type,
					description: t.description,
					time_sheet: t.time_sheet,
					from_time: t.from_time,
					to_time: t.to_time,
					billing_hours: t.billing_hours,
					billing_amount: t.billing_amount,
					timesheet_detail: t.name,
					project_name: t.project_name
				});
			});
			frm.refresh_field('timesheets');

			// Positionen vorbereiten
			if (v.replace) {
				frm.clear_table('items');
			} else {
				(frm.doc.items || []).slice().forEach(function (d) {
					if (!d.item_code && !d.item_name && !d.qty) {
						frm.get_field('items').grid.grid_rows_by_docname[d.name].remove();
					}
				});
			}

			var ohne_artikel = [];
			var ohne_preis = [];
			var quelle_artikel = 0;
			var quelle_aktivitaet = 0;
			var termine = [];

			for (var i = 0; i < zeiten.length; i++) {
				var t = zeiten[i];
				var art = at_map[t.activity_type] || {};
				var hat_artikel = !!art.custom_dienstleistungsartikel;
				var artikel = art.custom_dienstleistungsartikel || v.fallback_item;
				if (!artikel) {
					ohne_artikel.push(__(t.activity_type || '?'));
					continue;
				}
				var row = frm.add_child('items', {});
				await frappe.model.set_value(row.doctype, row.name, 'item_code', artikel);
				await frappe.model.set_value(row.doctype, row.name, 'qty', flt(t.billing_hours) || 1);

				// Satz der Aktivitaetsart (nur Fallback)
				var akt_satz = 0;
				if (flt(t.billing_hours) && flt(t.billing_amount)) {
					akt_satz = flt(t.billing_amount) / flt(t.billing_hours);
				} else if (flt(art.billing_rate)) {
					akt_satz = flt(art.billing_rate);
				}

				var zeile = locals[row.doctype][row.name];
				var artikel_preis = flt(zeile.price_list_rate) || flt(zeile.rate);

				if (hat_artikel && artikel_preis) {
					// Preis des Artikels gewinnt - Satz der Aktivitaetsart wird ignoriert
					quelle_artikel += 1;
					if (flt(zeile.rate) !== artikel_preis) {
						await frappe.model.set_value(row.doctype, row.name, 'rate', artikel_preis);
					}
				} else if (akt_satz) {
					// Kein Artikel verknuepft bzw. kein Artikelpreis vorhanden
					quelle_aktivitaet += 1;
					await frappe.model.set_value(row.doctype, row.name, 'rate', akt_satz);
				} else {
					ohne_preis.push(t.time_sheet + ' (' + __(t.activity_type || '?') + ')');
				}

				// Beschreibung: erste Zeile je nach Einstellung
				var bez = '';
				if (bez_modus.indexOf('Aktivit') === 0) {
					bez = __(t.activity_type || '');
				} else if (bez_modus.indexOf('Bezeichnung') === 0) {
					bez = art.custom_rechnungstext || __(t.activity_type || '');
				}

				var zeit = '';
				if (t.from_time) {
					zeit = frappe.datetime.str_to_user(t.from_time).split(' ')[0]
						+ ' ' + (t.from_time || '').substr(11, 5)
						+ '-' + (t.to_time || '').substr(11, 5) + ' Uhr';
				}

				var text = bez && zeit ? (bez + ' – ' + zeit) : (bez || zeit);
				if (t.description) { text = text ? (text + '<br>' + t.description) : t.description; }
				if (text) { await frappe.model.set_value(row.doctype, row.name, 'description', text); }

				var termin = termin_ende ? (t.to_time || t.from_time || '') : (t.from_time || '');
				termine.push([row.name, termin.substr(0, 10)]);
			}

			// Zweiter Durchgang: Lieferdatum setzen. Beim Setzen des Artikels holt
			// ERPNext die Artikel-Standards und ueberschreibt delivery_date wieder.
			for (var j = 0; j < termine.length; j++) {
				if (termine[j][1]) {
					await frappe.model.set_value('Sales Invoice Item', termine[j][0], 'delivery_date', termine[j][1]);
				}
			}

			frm.refresh_field('items');
			if (frm.cscript && frm.cscript.calculate_taxes_and_totals) { frm.cscript.calculate_taxes_and_totals(); }
			frappe.dom.unfreeze();

			var hinweise = [];
			if (ohne_artikel.length) {
				hinweise.push('<b>Kein Dienstleistungsartikel hinterlegt</b> fuer: ' + [...new Set(ohne_artikel)].join(', ')
					+ '. Diese Zeiten wurden nicht als Position uebernommen. Bitte in der Aktivitaetsart einen Dienstleistungsartikel eintragen oder beim Import einen Ersatz-Artikel waehlen.');
			}
			if (ohne_preis.length) {
				hinweise.push('<b>Kein Preis gefunden</b> fuer: ' + [...new Set(ohne_preis)].join(', ')
					+ '. Bitte Verkaufspreis des Artikels bzw. Stundensatz der Aktivitaetsart pruefen.');
			}
			var quellen = [];
			if (quelle_artikel) { quellen.push(quelle_artikel + 'x Artikelpreis'); }
			if (quelle_aktivitaet) { quellen.push(quelle_aktivitaet + 'x Satz der Aktivitaetsart'); }
			if (hinweise.length) {
				frappe.msgprint({ title: 'Bitte pruefen', indicator: 'orange', message: hinweise.join('<br><br>') });
			}
			frappe.show_alert({
				message: (quelle_artikel + quelle_aktivitaet) + ' Zeiteintraege uebernommen'
					+ (quellen.length ? ' (' + quellen.join(', ') + ')' : ''),
				indicator: 'green'
			}, 7);
		} catch (e) {
			frappe.dom.unfreeze();
			console.error(e);
			frappe.msgprint({ title: 'Fehler beim Import', indicator: 'red', message: (e && e.message) || String(e) });
		}
	}

	frappe.ui.form.on('Sales Invoice', {
		refresh: function (frm) {
			if (frm.doc.docstatus !== 0) { return; }
			frm.add_custom_button('Zeiten aus Zeiterfassung importieren', function () {
				zeit_import_dialog(frm);
			});
		}
	});
})();
