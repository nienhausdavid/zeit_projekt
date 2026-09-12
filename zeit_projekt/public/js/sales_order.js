// Projekt zum Auftrag wird erst beim Bestaetigen (Buchen) angelegt.
// Ausgeliefert ueber hooks.py -> doctype_js. Kein Client Script noetig.

(function () {
	// Nach dem Routing baut das Formular den ersten Reiter erneut auf. Ein
	// einmaliges set_active() verliert dieses Rennen, deshalb wiederholen wir
	// begrenzt, bis der Reiter mehrfach hintereinander stabil aktiv war.
	function zeige_verknuepfungen(projekt, versuch, treffer) {
		versuch = versuch || 0;
		treffer = treffer || 0;
		try {
			if (cur_frm && cur_frm.doc && cur_frm.doc.doctype === 'Project' && cur_frm.doc.name === projekt
				&& cur_frm.layout && cur_frm.layout.tabs && cur_frm.layout.tabs.length) {
				var tab = cur_frm.layout.tabs.find(function (t) { return t.df && t.df.fieldname === 'connections_tab'; });
				if (tab) {
					if (!tab.is_active()) { tab.set_active(); treffer = 0; } else { treffer += 1; }
				}
			}
		} catch (e) { console.error(e); }
		if (treffer < 4 && versuch < 20) {
			setTimeout(function () { zeige_verknuepfungen(projekt, versuch + 1, treffer); }, 400);
		}
	}

	function projektname(frm) {
		var ref = (frm.doc.buyer_reference || '').trim();
		return ref ? (ref + ' - ' + frm.doc.name)
			: ((frm.doc.customer_name || frm.doc.customer || '') + ' - ' + frm.doc.name);
	}

	frappe.ui.form.on('Sales Order', {
		custom_projekt_erstellen: function (frm) {
			if (!frm.doc.custom_projekt_erstellen) { return; }
			if (frm.doc.project) {
				frappe.msgprint({
					title: 'Projekt bereits verknuepft',
					indicator: 'orange',
					message: 'Mit diesem Auftrag ist bereits das Projekt <b>' + frm.doc.project + '</b> verknuepft. Es wird kein neues Projekt angelegt.'
				});
				frm.set_value('custom_projekt_erstellen', 0);
				return;
			}
			frappe.show_alert({ message: 'Das Projekt wird angelegt, sobald der Auftrag bestaetigt (gebucht) wird.', indicator: 'blue' }, 6);
		},

		refresh: function (frm) {
			if (frm.doc.docstatus === 0 && frm.doc.custom_projekt_erstellen && !frm.doc.project) {
				frm.dashboard.clear_headline();
				frm.dashboard.set_headline_alert('Beim Bestaetigen dieses Auftrags wird automatisch ein Projekt angelegt.', 'blue');
			}
		},

		// Anlage im before_submit, weil das Feld project im Auftrag
		// allow_on_submit = 0 hat und nach dem Buchen gesperrt ist. So geht die
		// Verknuepfung in dieselbe Speicheroperation - kein zweites Speichern,
		// damit auch kein "has been modified after you have opened it".
		before_submit: async function (frm) {
			if (!frm.doc.custom_projekt_erstellen || frm.doc.project) { return; }
			try {
				frappe.dom.freeze('Projekt wird angelegt ...');
				var bezeichnung = projektname(frm);
				var doc = {
					doctype: 'Project',
					project_name: bezeichnung,
					project_type: 'External',
					status: 'Open',
					is_active: 'Yes',
					company: frm.doc.company,
					customer: frm.doc.customer,
					sales_order: frm.doc.name,
					expected_start_date: frm.doc.transaction_date
				};
				if (frm.doc.delivery_date) { doc.expected_end_date = frm.doc.delivery_date; }
				var r = await frappe.call({ method: 'frappe.client.insert', args: { doc: doc } });
				var neu = r.message.name;
				await frm.set_value('project', neu);
				frappe.dom.unfreeze();
				frappe.show_alert({
					message: 'Projekt <b>' + neu + '</b> (' + bezeichnung + ') angelegt und verknuepft',
					indicator: 'green'
				}, 8);
			} catch (e) {
				frappe.dom.unfreeze();
				console.error(e);
				// Auftrag bleibt Entwurf - keine gebuchten Auftraege ohne Projekt.
				frappe.validated = false;
				frappe.msgprint({
					title: 'Projekt konnte nicht angelegt werden',
					indicator: 'red',
					message: 'Der Auftrag wurde nicht bestaetigt. Bitte pruefen Sie die Angaben und versuchen es erneut.'
				});
			}
		},

		on_submit: function (frm) {
			if (!frm.doc.custom_projekt_erstellen || !frm.doc.project) { return; }
			var neu = frm.doc.project;
			setTimeout(function () {
				try { frappe.set_route('Form', 'Project', neu); } catch (e) { console.error(e); }
				zeige_verknuepfungen(neu, 0, 0);
			}, 400);
		}
	});
})();
