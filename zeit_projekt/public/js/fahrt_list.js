// Fahrten-Liste: zweiter Knopf neben "Neu" - legt eine neue Fahrt an, startet gleich den
// Timer (Startzeit jetzt, sofort gespeichert) und oeffnet die Kamera fuer das Start-Foto.
// Das normale "Neu" bleibt unveraendert. Das Fahrt-Formular (fahrtenbuch.js) fuehrt es
// aus, sobald es geladen ist; der Merker verfaellt nach 15 s.
frappe.listview_settings['Fahrt'] = {
	onload(listview) {
		if (!frappe.model.can_create('Fahrt')) return;
		listview.page.add_button(__('Neu mit Timer und Kamera'), () => {
			window.zeit_projekt = window.zeit_projekt || {};
			window.zeit_projekt.neu_mit_timer_kamera = Date.now();
			frappe.new_doc('Fahrt');
		});
	},
};
