# Projektkontext

App `zeit_projekt` für ERPNext v16, entwickelt auf einem Server mit Frappe Manager (fm).

Bench: `<BENCHNAME>` — Site: `<SITENAME>`
(beim ersten Start bitte ersetzen, z. B. `erpdev` / `erpdev.localhost`)

Vier Funktionen in drei Modulen (aus den ursprünglich getrennten Apps `zeit_projekt`, `fahrtenbuch` und `site_visit` zu einer App zusammengeführt, siehe README.md "Herkunft"):
1. (Modul „Zeit Projekt") Knopf in der Ausgangsrechnung, der Zeiterfassungen als einzelne Rechnungspositionen importiert (Artikel aus der Aktivitätsart, Preis aus dem Artikel, Beschreibung und Liefertermin konfigurierbar).
2. (Modul „Zeit Projekt") Haken im Auftrag, der beim Bestätigen automatisch ein Projekt anlegt und verknüpft.
3. (Modul „Fahrtenbuch") Fahrten dokumentieren, Kilometerstand per Fotoerkennung erfassen; beim Buchen entsteht ein Zeitblatt (Fahrzeit), Kilometer kommen über den Zeitimport der Ausgangsrechnung.
4. (Modul „Site Visit") Kundeneinsätze dokumentieren (Zeit, Fotos, Unterschrift), daraus automatisch ein abrechenbares Zeitblatt erzeugen.

Details zu Funktionsweise, Feldern und Einstellungen stehen in `README.md` und `docs/` — vor der ersten Änderung lesen.

## Umgebung

Dieses Verzeichnis ist gleichzeitig `/workspace/frappe-bench/apps/zeit_projekt` im Container. Dateien werden direkt hier bearbeitet. Alles, was bench oder Python im Frappe-Kontext braucht, läuft über:

- Shell-Befehl:  `fm shell <BENCHNAME> -c "<befehl>"`
- Python/Frappe: `fm shell <BENCHNAME> --bench-console -c "<python>"`

Frappe- und ERPNext-Quellcode zum Nachschlagen (nur lesen, nie ändern):
`../frappe/frappe/` und `../erpnext/erpnext/`

## Befehle

| Zweck | Befehl |
|---|---|
| Nach JS-Änderung | `fm shell <BENCHNAME> -c "bench build --app zeit_projekt"` |
| Nach hooks.py/Python-Änderung | `fm shell <BENCHNAME> -c "bench --site <SITENAME> clear-cache && bench restart"` |
| Nach DocType-Änderung | `fm shell <BENCHNAME> -c "bench --site <SITENAME> migrate"` |
| App installieren | `fm shell <BENCHNAME> -c "bench --site <SITENAME> install-app zeit_projekt"` |
| App entfernen | `fm shell <BENCHNAME> -c "bench --site <SITENAME> uninstall-app zeit_projekt --yes"` |
| Logs | `fm logs <BENCHNAME> --follow` |
| Tests | `fm shell <BENCHNAME> -c "bench --site <SITENAME> run-tests --app zeit_projekt"` (einmalig vorher `set-config allow_tests true`) |

## Regeln

- Niemals Dateien außerhalb dieses App-Verzeichnisses ändern. Standardcode von Frappe oder ERPNext wird nur gelesen, nie gepatcht.
- Keine Client Scripts, keine Custom Fields über die Oberfläche anlegen — alles gehört in die App (`install.py`, `public/js/`, DocType-JSON), damit `uninstall-app` sauber wieder alles entfernt.
- Vor jeder Behauptung über Frappe-/ERPNext-Verhalten: im Quellcode nachsehen, nicht raten.
- Änderungen an der Datenbank immer über bench/Frappe-API, nie mit direktem SQL.
- Nach jeder Änderung selbst verifizieren (siehe unten) und das Ergebnis zeigen, bevor der nächste Schritt beginnt.
- Deutsche Oberflächentexte; Code, Feld- und Methodennamen englisch bzw. wie in der App bereits vorgegeben (Präfix `custom_` für Custom Fields).
- Kleine, einzeln nachvollziehbare Änderungen statt großer Umbauten in einem Schritt. Nach jeder funktionierenden Änderung committen.

## Verifikation

```bash
# Sind die Felder da?
fm shell <BENCHNAME> --bench-console -c "print(frappe.get_all('Custom Field', filters={'module':'Zeit Projekt'}, pluck='name'))"

# Ist die App installiert?
fm shell <BENCHNAME> -c "bench --site <SITENAME> list-apps"

# Sind die Einstellungen erreichbar?
fm shell <BENCHNAME> --bench-console -c "print(frappe.get_doc('Zeit Projekt Einstellungen').as_dict())"
fm shell <BENCHNAME> --bench-console -c "print(frappe.get_doc('Fahrtenbuch Einstellungen').as_dict())"

# Sind alle drei Module registriert und die neuen Doctypes da?
fm shell <BENCHNAME> --bench-console -c "print(frappe.get_all('Module Def', filters={'app_name':'zeit_projekt'}, pluck='name'))"
fm shell <BENCHNAME> --bench-console -c "print(frappe.db.exists('DocType', 'Fahrt'), frappe.db.exists('DocType', 'Site Visit'))"
```

Browserseitiges Verhalten (Knopf, Dialog, Sprung auf den Reiter Verknüpfungen) lässt sich nicht automatisiert prüfen — dafür eine kurze Klickliste vorschlagen und das Ergebnis vom Nutzer zurückmelden lassen.
