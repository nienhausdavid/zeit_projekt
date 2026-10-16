// Formular "Zeit Projekt Einstellungen".
//
// Modell: eine echte Auswahlliste (Autocomplete). Sie fuellt sich von selbst mit den Modellen, die
// die eingestellte API tatsaechlich anbietet - beim Oeffnen und sobald Schnittstelle, URL oder
// Schluessel geaendert werden - statt ueber einen Knopf in der Kopfzeile. Ein anderer Name laesst
// sich weiterhin eintippen. Das Laden darf nur der System Manager (Abschnitt hat permlevel 1).
frappe.ui.form.on('Zeit Projekt Einstellungen', {
	refresh(frm) {
		lade_modelle(frm);
	},

	api_type(frm) {
		lade_modelle(frm);
	},
	opencode_zugang(frm) {
		lade_modelle(frm);
	},
	api_url(frm) {
		lade_modelle(frm);
	},
	api_key(frm) {
		lade_modelle(frm);
	},

	setup(frm) {
		// Auswahl in der Tabelle "Aktivitaetsarten" auf aktive Verkaufsartikel beschraenken.
		frm.set_query('dienstleistungsartikel', 'aktivitaetsarten', () => ({
			filters: { disabled: 0, is_sales_item: 1, has_variants: 0 },
		}));
		frm.set_query('activity_type', 'aktivitaetsarten', () => ({ filters: { disabled: 0 } }));
	},
});

const MODELL_BESCHREIBUNG = __(
	'Vision-Modell, das den Kilometerstand liest, z. B. minicpm-v4.5 (Ollama) oder kimi-k3 (OpenCode). Die Auswahl lädt die bei der API tatsächlich verfügbaren Modelle von selbst; ein anderer Name lässt sich auch eintippen. Das Modell muss Bilder lesen können.'
);

// Laedt die Modelle der API und fuellt die Auswahl. Mehrere Aenderungen kurz hintereinander
// (Tippen in der URL) ergeben nur einen Abruf; ein veraltetes Ergebnis wird verworfen.
function lade_modelle(frm) {
	const feld = frm.fields_dict.model;
	if (!feld || feld.disp_status !== 'Write') return; // Abschnitt nur fuer den System Manager
	clearTimeout(frm.__modelle_timer);
	frm.__modelle_timer = setTimeout(() => {
		const typ = frm.doc.api_type;
		if (!frm.doc.api_url && typ !== 'OpenCode') {
			setze_modelle(frm, [], __('Bitte zuerst die API-URL eintragen, dann erscheint hier die Auswahl.'));
			return;
		}
		const anfrage = (frm.__modelle_anfrage = (frm.__modelle_anfrage || 0) + 1);
		// Den Schluessel nur senden, wenn er gerade eingetippt wurde: ein gespeicherter erscheint
		// als Sternchen, dann nimmt der Server den gespeicherten.
		const schluessel = frm.doc.api_key && !/^\*+$/.test(frm.doc.api_key) ? frm.doc.api_key : null;
		frappe.call({
			method: 'zeit_projekt.fahrtenbuch.fahrtenbuch.get_available_models',
			args: { api_url: frm.doc.api_url, api_key: schluessel, api_type: typ, opencode_zugang: frm.doc.opencode_zugang },
			silent: true, // den Grund zeigen wir selbst unter dem Feld, kein Fehler-Dialog beim Oeffnen
			callback(r) {
				if (anfrage !== frm.__modelle_anfrage) return;
				const modelle = r.message || [];
				setze_modelle(frm, modelle, modelle.length ? null : __('Die API nennt keine Modelle.'));
			},
			error(xhr) {
				if (anfrage !== frm.__modelle_anfrage) return;
				setze_modelle(frm, [], grund_aus(xhr) || __('Die Modellliste konnte nicht geladen werden.'));
			},
		});
	}, 600);
}

function setze_modelle(frm, modelle, hinweis) {
	const feld = frm.fields_dict.model;
	feld.df.options = modelle;
	if (feld.set_data) feld.set_data(modelle);
	frm.set_df_property(
		'model',
		'description',
		hinweis ? `${MODELL_BESCHREIBUNG}<br><span class="text-danger">${frappe.utils.escape_html(hinweis)}</span>` : MODELL_BESCHREIBUNG
	);
}

// Die Meldung des Servers (frappe.throw) aus der Fehlerantwort holen
function grund_aus(xhr) {
	try {
		const nachrichten = JSON.parse(xhr.responseJSON._server_messages);
		return JSON.parse(nachrichten[0]).message;
	} catch (e) {
		return null;
	}
}
