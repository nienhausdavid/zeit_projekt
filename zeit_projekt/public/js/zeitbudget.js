// Zeitbudget: wie viel der für den Auftrag geplanten Zeit schon gebucht ist, als farbiger Balken mit
// Prozent im Auftrag, im Kundeneinsatz und in der Fahrt. Die Zahlen liefert der Server
// (zeitbudget.get_zeitbudget); ohne geplante Stunden im Auftrag erscheint nichts.
// Farben: grün im Rahmen, orange ab 80 %, rot über 100 %.
(function () {
	const FARBKLASSEN = { green: 'progress-bar-success', orange: 'progress-bar-warning', red: 'progress-bar-danger' };

	function entfernen(frm) {
		if (frm.__zp_budget) {
			frm.__zp_budget.remove();
			frm.__zp_budget = null;
		}
	}

	function zeigen(frm) {
		entfernen(frm);
		const auftrag = frm.doctype === 'Sales Order' ? (frm.is_new() ? null : frm.doc.name) : frm.doc.sales_order;
		frm.__zp_budget_stand = auftrag;
		if (!auftrag) return;

		frappe
			.call({ method: 'zeit_projekt.zeit_projekt.zeitbudget.get_zeitbudget', args: { sales_order: auftrag } })
			.then((r) => {
				// Auftrag inzwischen gewechselt? Dann gehört die Antwort nicht mehr hierher.
				if (frm.__zp_budget_stand !== auftrag) return;
				const b = r.message;
				entfernen(frm);
				if (!b) return;
				const zahl = (wert) => format_number(wert, null, 2);
				let text = __('{0} von {1} Std. verbraucht ({2} %)', [zahl(b.verbraucht), zahl(b.geplant), zahl(b.prozent)]);
				if (b.rest < 0) text += ' – ' + __('{0} Std. über Plan', [zahl(-b.rest)]);
				else text += ' – ' + __('noch {0} Std.', [zahl(b.rest)]);
				frm.__zp_budget = frm.dashboard.add_progress(
					__('Geplante Zeit'),
					[{ title: text, width: Math.min(b.prozent, 100) + '%', progress_class: FARBKLASSEN[b.farbe] }],
					text
				);
			});
	}

	window.zeit_projekt = window.zeit_projekt || {};
	window.zeit_projekt.zeitbudget = { zeigen };

	['Sales Order', 'Site Visit', 'Fahrt'].forEach((doctype) => {
		frappe.ui.form.on(doctype, {
			refresh: zeigen,
			// Fahrt und Kundeneinsatz: anderer Auftrag gewählt
			sales_order: (frm) => doctype !== 'Sales Order' && zeigen(frm),
		});
	});
})();
