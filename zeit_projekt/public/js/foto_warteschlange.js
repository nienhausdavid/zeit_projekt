// Offline-Warteschlange fuer Kilometerstand-Fotos.
//
// Schlaegt der Foto-Upload am Handy wegen fehlender Verbindung fehl (Funkloch, Tiefgarage),
// geht das Foto nicht verloren: es wird im Browser (IndexedDB) abgelegt und automatisch
// gesendet, sobald wieder Netz da ist (Ereignis "online", sonst alle 30 s, ausserdem beim
// Oeffnen einer Fahrt). Wohin das Foto gehoert, entscheidet fahrtenbuch.js (zuordnen).
// Die Warteschlange bleibt nach einem Neuladen oder Schliessen der Seite erhalten.
window.zeit_projekt = window.zeit_projekt || {};

(function () {
	const DB_NAME = 'zeit_projekt_fotos';
	const STORE = 'fotos';
	const TAKT_MS = 30000;
	let laeuft = false;
	let takt = null;
	let letzte_zuordnung = null;

	function oeffne() {
		return new Promise((resolve, reject) => {
			if (!window.indexedDB) return reject(new Error('IndexedDB nicht verfügbar'));
			const anfrage = indexedDB.open(DB_NAME, 1);
			anfrage.onupgradeneeded = () => anfrage.result.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true });
			anfrage.onsuccess = () => resolve(anfrage.result);
			anfrage.onerror = () => reject(anfrage.error);
		});
	}

	function transaktion(modus, aktion) {
		return oeffne().then(
			(db) =>
				new Promise((resolve, reject) => {
					const t = db.transaction(STORE, modus);
					const anfrage = aktion(t.objectStore(STORE));
					t.oncomplete = () => {
						db.close();
						resolve(anfrage.result);
					};
					t.onerror = () => reject(t.error);
					t.onabort = () => reject(t.error);
				})
		);
	}

	const ablegen = (eintrag) => transaktion('readwrite', (s) => s.add(eintrag));
	const alle = () => transaktion('readonly', (s) => s.getAll());
	const entfernen = (id) => transaktion('readwrite', (s) => s.delete(id));
	const anzahl = () => alle().then((liste) => liste.length).catch(() => 0);

	function hochladen(eintrag) {
		const form = new FormData();
		form.append('file', eintrag.blob, eintrag.filename);
		form.append('is_private', 1);
		form.append('folder', 'Home');
		form.append('doctype', eintrag.doctype);
		if (eintrag.docname) form.append('docname', eintrag.docname);
		form.append('fieldname', eintrag.fieldname);
		return fetch('/api/method/upload_file', {
			method: 'POST',
			headers: { 'X-Frappe-CSRF-Token': frappe.csrf_token },
			body: form,
		}).then((antwort) => {
			if (!antwort.ok) throw Object.assign(new Error(`HTTP ${antwort.status}`), { http: antwort.status });
			return antwort.json();
		}).then((json) => json.message.file_url);
	}

	// Sendet alle wartenden Fotos nacheinander. zuordnen(eintrag, file_url) -> Promise haengt das
	// hochgeladene Foto an die Fahrt (fahrtenbuch.js). Bei einem Fehler bleibt der Rest liegen.
	function senden(zuordnen) {
		if (zuordnen) letzte_zuordnung = zuordnen;
		if (laeuft || !navigator.onLine || !letzte_zuordnung) return Promise.resolve();
		laeuft = true;
		return alle()
			.then((liste) =>
				liste.reduce(
					(kette, eintrag) =>
						kette.then(() =>
							hochladen(eintrag)
								.then((url) => letzte_zuordnung(eintrag, url))
								.then(() => entfernen(eintrag.id))
						),
					Promise.resolve()
				)
			)
			.catch(() => {
				// Noch kein Netz oder Sitzung abgelaufen: liegen lassen, der naechste Takt versucht es erneut
			})
			.finally(() => {
				laeuft = false;
				return anzahl().then((n) => (n ? starte_takt() : stoppe_takt()));
			});
	}

	function starte_takt() {
		if (takt) return;
		takt = setInterval(() => senden(), TAKT_MS);
	}

	function stoppe_takt() {
		if (!takt) return;
		clearInterval(takt);
		takt = null;
	}

	window.addEventListener('online', () => senden());

	window.zeit_projekt.foto_warteschlange = { ablegen, anzahl, senden, starte_takt };
})();
