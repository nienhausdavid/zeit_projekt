// Projekt zum Auftrag wird erst beim Bestaetigen (Buchen) angelegt.
// Die Anlage selbst laeuft serverseitig in zeit_projekt.zeit_projekt.sales_order.before_submit
// (siehe hooks.py -> doc_events), im selben Request wie das Buchen. Dieses
// Skript liefert nur noch Hinweise und springt nach dem Buchen zum Projekt.
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
