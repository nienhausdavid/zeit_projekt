frappe.ui.form.on('Fahrtenbuch Einstellungen', {
	refresh(frm) {
		frm.add_custom_button(__('Verfügbare Modelle abrufen'), () => fetch_models(frm));
	},
});

function fetch_models(frm) {
	if (!frm.doc.api_url) {
		frappe.msgprint(__('Bitte zuerst eine API-URL eintragen und speichern.'));
		return;
	}
	frappe.call({
		method: 'zeit_projekt.fahrtenbuch.fahrtenbuch.get_available_models',
		// Testet direkt, was gerade im Formular steht (auch ungespeichert) -
		// server faellt auf den gespeicherten Stand zurueck, wenn leer.
		args: { api_url: frm.doc.api_url, api_key: frm.doc.api_key },
		freeze: true,
		freeze_message: __('Modelle werden abgerufen...'),
		callback(r) {
			const models = r.message || [];
			if (!models.length) {
				frappe.msgprint(__('Keine Modelle gefunden.'));
				return;
			}
			const dialog = new frappe.ui.Dialog({
				title: __('Modell wählen'),
				fields: [
					{
						fieldname: 'model',
						fieldtype: 'Select',
						label: __('Modell'),
						options: models.join('\n'),
						default: models.includes(frm.doc.model) ? frm.doc.model : models[0],
					},
				],
				primary_action_label: __('Übernehmen'),
				primary_action(values) {
					frm.set_value('model', values.model);
					dialog.hide();
				},
			});
			dialog.show();
		},
	});
}
