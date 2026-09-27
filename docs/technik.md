# Technik

## Aufbau

```
zeit_projekt/
├── pyproject.toml
├── README.md, docs/
├── .github/workflows/ci.yml       # Tests gegen Frappe/ERPNext version-16
└── zeit_projekt/
    ├── __init__.py                # Versionsnummer + pdf_on_submit-Chrome-Patch
    ├── hooks.py                   # doctype_js, doc_events, Install-Hooks, Dashboards, Desk
    ├── install.py                 # Custom Fields, Konflikt-Prüfung, pdf_on_submit-Kopplung
    ├── modules.txt                # "Zeit Projekt", "Fahrtenbuch", "Site Visit"
    ├── patches.txt                # derzeit leer
    ├── desktop_icon/              # App-Symbol "Zeit & Projekt" + zwei Unter-Symbole
    ├── workspace_sidebar/         # Seitenleisten "Fahrtenbuch" und "Site Visits"
    ├── translations/
    │   ├── en.csv                 # Englisch (Quelle der App ist Deutsch)
    │   └── de.csv                 # nur die englischen Doctype-Namen von Site Visit
    ├── public/
    │   ├── images/zeit_projekt-logo.svg
    │   └── js/
    │       ├── sales_invoice.js         # Zeitimport-Dialog
    │       ├── sales_order.js           # Hinweise + Sprung zum Projekt nach dem Buchen
    │       ├── fahrtenbuch.js           # Fahrt: Vorbelegung, Timer, Kilometerstand-Erkennung
    │       ├── fahrtenbuch_einstellungen.js  # "Verfügbare Modelle abrufen"
    │       ├── project.js               # "Fahrt mit Timer starten"
    │       └── site_visit.js            # Kundeneinsatz: Timer, Link-Suchen, "Neuer Auftrag"
    ├── zeit_projekt/              # Modul "Zeit Projekt"
    │   ├── billing.py                 # Zeitblatt anlegen/stornieren, Positionen im Auftrag
    │   ├── sales_invoice.py           # Zeitimport, Kilometer, Prüfung custom_fahrt
    │   ├── sales_order.py             # Projektanlage in before_submit
    │   ├── technician.py              # eingeschränkte Link-Suchen für Techniker
    │   ├── desk.py                    # Sichtbarkeit des App-Symbols
    │   ├── pdf.py                     # optional: Chrome als PDF-Generator erzwingen
    │   ├── doctype/zeit_projekt_einstellungen/
    │   └── tests/                     # Integrationstests + setup_ci.py
    ├── fahrtenbuch/               # Modul "Fahrtenbuch"
    │   ├── fahrtenbuch.py             # before_submit/on_cancel, Vorbelegung, OCR-Job
    │   ├── ocr.py                     # OpenAI-kompatible Vision-API
    │   ├── project_dashboard.py
    │   └── doctype/{fahrt,fahrtenbuch_einstellungen}/
    └── site_visit/                # Modul "Site Visit"
        ├── site_visit.py              # before_submit/on_cancel, create_sales_order
        ├── project_dashboard.py
        ├── doctype/{site_visit,site_visit_item,site_visit_photo}/
        └── print_format/site_visit_report/
```

Formular-Skripte sind **Dateien** (`doctype_js`), keine Client-Script-Datensätze,
und alle Custom Fields stehen in `install.py` – beides verschwindet restlos mit
der App.

### Custom Fields

| Doctype | Feld | Zweck |
|---|---|---|
| Activity Type | `custom_dienstleistungsartikel` | Artikel der Rechnungsposition |
| Activity Type | `custom_rechnungstext` | optionale Bezeichnung auf der Rechnung |
| Sales Order | `custom_projekt_erstellen` | Projekt beim Buchen anlegen |
| Sales Order Item | `custom_site_visit` | Herkunft einer Zusatzartikel-Position |
| Sales Invoice Item | `custom_fahrt` | Fahrt einer Kilometer-Position |

`after_migrate` legt sie erneut an bzw. aktualisiert sie – neue Felder kommen
so auch auf bestehenden Sites an.

### Zusammenspiel

- Eine **Fahrt** kann auf einen Kundeneinsatz verweisen; Kunde, Projekt und
  Auftrag werden dann übernommen.
- Beide Belege erzeugen beim Buchen über `billing.create_timesheet` ein
  gebuchtes, abrechenbares Zeitblatt mit Kunde und Projekt; der Zeitimport der
  Ausgangsrechnung findet es dadurch.
- Beide ergänzen die *Verknüpfungen* im Projekt über
  `override_doctype_dashboards` (Frappe ruft beide Funktionen nacheinander
  auf).
- Die früheren Einzel-Apps `fahrtenbuch` und `site_visit` bringen dieselben
  Module und Doctypes mit; `before_install` bzw. `before_app_install` brechen
  die Installation ab, wenn eine davon vorhanden ist.

## Desk

`add_to_apps_screen` registriert **ein** App-Symbol „Zeit & Projekt" (Logo,
Ziel `/desk/fahrt?sidebar=Fahrtenbuch`). Darunter liegen die Symbole
*Fahrtenbuch* und *Site Visits*, die je eine eigene Seitenleiste öffnen. Die
Symbole und Seitenleisten liegen als JSON in `desktop_icon/` und
`workspace_sidebar/`; Frappe gleicht sie bei jedem `migrate` ab. Der
Dateiname muss `frappe.scrub(<Bezeichnung>)` entsprechen, sonst löscht
`migrate` das Symbol als verwaist.

Sichtbar ist das App-Symbol für System Manager, Projects Manager, Projects
User, Accounts User und Employee (`desk.check_app_permission`); die einzelnen
Einträge der Seitenleisten blendet Frappe nach Leserecht aus.
`before_uninstall` entfernt die Symbole, weil Frappe sie unter dem App-Namen
sucht und „Zeit & Projekt" nicht fände.

## Berechtigungen

**Fahrt / Site Visit**

| Rolle | Lesen | Schreiben | Anlegen | Buchen | Stornieren |
|---|---|---|---|---|---|
| System Manager | ✓ | ✓ | ✓ | ✓ | ✓ |
| Projects Manager | ✓ | ✓ | ✓ | ✓ | ✓ |
| Employee | eigene | eigene | ✓ | eigene | – |
| Projects User | ✓ | – | – | – | – |
| Accounts User | ✓ | – | – | – | – |

Ein gebuchter, unterschriebener Kundeneinsatz gilt als Bestätigung gegenüber
dem Kunden – stornieren können nur Projects Manager/System Manager.

**Techniker mit nur der Rolle „Employee"** dürfen in ERPNext Kunde, Auftrag,
Artikel und Fahrzeug nicht lesen und keine Zeitblätter buchen. Deshalb:

- Die Formulare nutzen eigene Link-Suchen und Detail-Abfragen
  (`technician.py`): nur Name und Bezeichnung, nur offene Aufträge, nur
  verkaufsfähige Artikel – und nur für Nutzer mit Anlege- oder Schreibrecht
  auf Fahrt bzw. Site Visit. Frappe prüft bei eigenen Link-Suchen keine
  Rechte, daher prüft `_check_access` selbst.
- Zeitblatt und Auftragsänderung laufen serverseitig ohne Rollenprüfung bzw.
  als Administrator; vorher wird geprüft, dass der Auftrag offen ist und zum
  Kunden gehört. Wer gebucht hat, steht im Zeitblatt-Vermerk und als
  Kommentar im Auftrag.

**Einstellungen:** Schreiben darf nur der System Manager. *Zeit Projekt
Einstellungen* sind zusätzlich für Accounts User/Manager und Projects User
lesbar. *Fahrtenbuch Einstellungen* enthalten den API-Schlüssel und sind nur
für System Manager lesbar; Techniker bekommen die Vorbelegungen über
`get_fahrt_defaults`. „Verfügbare Modelle abrufen" ist System Managern
vorbehalten (der Server ruft dabei eine frei angegebene URL ab).

Eine eigene Techniker-Rolle liefert die App bewusst nicht mit: Rollen sind
nicht modulgebunden und blieben beim Deinstallieren zurück.

## Sprache

Quellsprache der App ist **Deutsch**. `translations/en.csv` übersetzt
Oberflächentexte und Meldungen für Nutzer mit Sprache Englisch;
`translations/de.csv` enthält nur die englischen Doctype-Namen des Moduls
Site Visit („Site Visit" → „Kundeneinsatz" …). Begriffe, die Frappe/ERPNext
schon übersetzen („Customer", „Timesheet" …), stehen nicht noch einmal
darin.

App-Übersetzungen gelten in Frappe für die **ganze Site**. Mehrdeutige
Begriffe bekommen deshalb einen Kontext (dritte Spalte), z. B. den Doctype.

Neue Texte im Code: Python `_("…")`, JavaScript `__("…")`, deutsch mit
Umlauten, und die englische Übersetzung in `en.csv` ergänzen.

## Tests

```bash
bench --site <test-site> set-config allow_tests true
bench --site <test-site> execute zeit_projekt.zeit_projekt.tests.setup_ci.complete_setup   # nur auf frischer Site
bench --site <test-site> run-tests --app zeit_projekt
```

`tests/utils.py` legt die Testdaten selbst an (Kunden, Artikel,
Aktivitätsarten, zwei Nutzer: Techniker nur mit „Employee", Buchhaltung mit
„Accounts User"). Abgedeckt sind u. a.: Buchen und Stornieren von Fahrt und
Kundeneinsatz samt Zeitblatt, Taktung, Überschneidung, Zusatzartikel im
Auftrag (Preis, fremder Kunde, „Neuer Auftrag“, Berichtigung), Zeitimport und
Kilometer genau einmal, Rechte der Link-Suchen, Desk-Sichtbarkeit und die
Kilometerstand-Erkennung gegen einen lokalen Fake-Server.

Die GitHub-Action `.github/workflows/ci.yml` baut eine frische Bench mit
Frappe/ERPNext `version-16`, installiert die App und führt die Tests aus.

## Bekannte Grenzen

- **Liefertermin der Rechnungsposition:** Sales Invoice Item hat in ERPNext
  v16 kein Feld `delivery_date`. Die Einstellung „Liefertermin der Position"
  wirkt daher nur, wenn eine andere App dieses Feld ergänzt.
- **Kilometerstand-Erkennung** braucht einen laufenden Worker für die Queue
  `short`; ohne Worker bleibt das Feld leer (manuelle Eingabe geht immer).
- **Taktung:** Liegen die abrechenbaren Stunden über den tatsächlichen,
  zeigt ERPNext im Zeitblatt einen Hinweis – gewollt, kein Fehler.
- **Nur v16:** Desk-Symbole, Seitenleisten und `/desk/…`-Routen gibt es erst
  ab Frappe v16.
- **Deinstallation** löscht die Tabellen von Fahrt und Site Visit samt Fotos
  und Unterschriften (Frappe-Standard) – vorher sichern, falls sie noch
  gebraucht werden.

## Erweiterungsideen

- „Neuer Auftrag" direkt aus der Fahrt (wie beim Kundeneinsatz).
- Kilometer per Route/Adresse berechnen statt über das Tacho-Foto.
- Mehrere Zeitsegmente/Pausen pro Kundeneinsatz.
- GPS-Standort beim Anlegen von Fahrt und Kundeneinsatz.
- Externes Signaturpad statt Finger/Stift.
- Custom Fields oder Property Setter, die später über die Oberfläche
  entstehen, gehören nicht automatisch zur App – in `install.py`
  nachtragen, dann entfernt die Deinstallation sie mit.
