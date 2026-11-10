// Zeitbudget: wie viel der für den Auftrag geplanten Zeit schon gebucht ist, als farbiger Balken mit
// Prozent im Auftrag, im Kundeneinsatz und in der Fahrt. Die Zahlen liefert der Server
// (zeitbudget.get_zeitbudget); ohne geplante Stunden im Auftrag erscheint nichts.
// Farben: grün im Rahmen, orange ab 80 %, rot über 100 %.
(function () {
	const FARBKLASSEN = { green: 'progress-bar-success', orange: 'progress-bar-warning', red: 'progress-bar-danger' };

	function entfernen(frm) {
		['__zp_budget', '__zp_rent'].forEach((feld) => {
			if (frm[feld]) {
				frm[feld].remove();
				frm[feld] = null;
			}
		});
	}

	// Pauschale: Preis je Stunde gegen den Sollsatz (nur für Nutzer mit Leserecht am Auftrag)
	function rentabilitaet_zeigen(frm, auftrag) {
		frappe
			.call({ method: 'zeit_projekt.zeit_projekt.rentabilitaet.get_rentabilitaet', args: { sales_order: auftrag } })
			.then((r) => {
				if (frm.__zp_budget_stand !== auftrag) return;
				const x = r.message;
				if (!x || x.abweichung === null || x.abweichung === undefined) return;
				const geld = (wert) => format_currency(wert);
				const satz = x.effektiver_satz !== null ? x.effektiver_satz : x.geplanter_satz;
				const art = x.effektiver_satz !== null ? __('effektiv') : __('geplant');
				const text = __('Pauschale {0}/Std. ({1}) gegen Sollsatz {2}/Std.: {3} %', [
					geld(satz),
					art,
					geld(x.sollsatz),
					format_number(x.abweichung, null, 1),
				]);
				const breite = Math.max(0, Math.min((satz / x.sollsatz) * 100, 100));
				if (frm.__zp_rent) frm.__zp_rent.remove();
				frm.__zp_rent = frm.dashboard.add_progress(
					__('Rentabilität'),
					[{ title: text, width: breite + '%', progress_class: FARBKLASSEN[x.farbe] }],
					text
				);
			});
	}

	function zeigen(frm) {
		entfernen(frm);
		const auftrag = frm.doctype === 'Sales Order' ? (frm.is_new() ? null : frm.doc.name) : frm.doc.sales_order;
		frm.__zp_budget_stand = auftrag;
		if (!auftrag) return;

		rentabilitaet_zeigen(frm, auftrag);
		frappe
			.call({ method: 'zeit_projekt.zeit_projekt.zeitbudget.get_zeitbudget', args: { sales_order: auftrag } })
			.then((r) => {
				// Auftrag inzwischen gewechselt? Dann gehört die Antwort nicht mehr hierher.
				if (frm.__zp_budget_stand !== auftrag) return;
				const b = r.message;
				if (frm.__zp_budget) {
					frm.__zp_budget.remove();
					frm.__zp_budget = null;
				}
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
