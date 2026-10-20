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
    ├── workspace_sidebar/         # Seitenleisten im alten Format (Frappe < 16.51)
    ├── translations/
    │   ├── en.csv                 # Englisch (Quelle der App ist Deutsch)
    │   └── de.csv                 # nur die englischen Doctype-Namen von Site Visit
    ├── public/
    │   ├── images/zeit_projekt-logo.svg
    │   ├── icons/desktop_icons/       # solid/ + subtle/: je ein SVG für Fahrtenbuch und Site Visits
    │   └── js/
    │       ├── sales_invoice.js         # Zeitimport-Dialog
    │       ├── sales_order.js           # Hinweise + Sprung zum Projekt nach dem Buchen
    │       ├── fahrtenbuch.js           # Fahrt: Vorbelegung, Timer, Kilometerstand-Erkennung, Standort
    │       ├── project.js               # "Fahrt mit Timer starten"
    │       └── site_visit.js            # Kundeneinsatz: Timer/Pausen, Link-Suchen, "Neuer Auftrag"
    ├── zeit_projekt/              # Modul "Zeit Projekt"
    │   ├── billing.py                 # Zeitblatt anlegen/stornieren, Positionen im Auftrag
    │   ├── billing_status.py          # "% berechnet" des Auftrags inkl. Zeitbuchungen
    │   ├── report/abrechnungsansicht/         # Skriptbericht: offene Zeiten/Kilometer je Kunde, Auftrag, Projekt
    │   ├── report/auftrags__und_projektansicht/  # Skriptbericht: Projekte mit Aufträgen als Baum
    │   ├── sales_invoice.py           # Zeitimport, Kilometer, Prüfung custom_fahrt
    │   ├── sales_order.py             # Projektanlage in before_submit
    │   ├── technician.py              # eingeschränkte Link-Suchen für Techniker
    │   ├── desk.py                    # Sichtbarkeit des App-Symbols
    │   ├── pdf.py                     # optional: Chrome als PDF-Generator erzwingen
    │   ├── doctype/{zeit_projekt_einstellungen,zeit_projekt_artikelgruppe,zeit_projekt_aktivitaetsart}/
    │   └── tests/                     # Integrationstests + setup_ci.py
    ├── fahrtenbuch/               # Modul "Fahrtenbuch"
    │   ├── fahrtenbuch.py             # before_submit/on_cancel, Vorbelegung, OCR-Job
    │   ├── ocr.py                     # OpenAI-kompatible Vision-API
    │   ├── project_dashboard.py
    │   └── doctype/fahrt/
    └── site_visit/                # Modul "Site Visit"
        ├── site_visit.py              # before_submit/on_cancel, create_sales_order
        ├── project_dashboard.py
        ├── doctype/{site_visit,site_visit_item,site_visit_photo,site_visit_break}/
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
| Timesheet Detail | `custom_sales_order` | Auftrag der Zeitbuchung (Filter im Zeitimport) |
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
*Fahrtenbuch*, *Site Visits* und *Einstellungen*, die je eine eigene Seitenleiste öffnen
(*Zeit & Projekt Einstellungen*, Modul „Zeit Projekt": Einstellungen, Aktivitätsarten, Mitarbeiter;
Frappe benennt eine Seitenleiste nach ihrem Titel, Name und Titel müssen gleich sein). Die
Symbole liegen als JSON in `desktop_icon/`, die Seitenleisten als `Sidebar`
je Modul unter `fahrtenbuch/sidebar/fahrtenbuch/` und
`site_visit/sidebar/site_visits/` und `zeit_projekt/sidebar/zeit_&_projekt_einstellungen/`; Frappe gleicht sie bei jedem `migrate` ab.
Der Dateiname muss `frappe.scrub(<Bezeichnung>)` entsprechen, sonst löscht
`migrate` das Symbol als verwaist.

**Bilder der Unter-Symbole:** Der Desk sucht pro Unter-Symbol `public/icons/desktop_icons/
{solid,subtle}/<frappe.scrub(Bezeichnung)>.svg` der App (hier `fahrtenbuch.svg`,
`site_visits.svg`; Rahmen im Stil von ERPNext, Glyphen aus Lucide, ISC-Lizenz). Fehlen sie,
zeigt er nur den Anfangsbuchstaben (F, S). Das App-Symbol selbst nutzt `logo_url`. Die
Liste kommt beim Seitenaufruf aus `frappe.boot.desktop_icon_urls`; nach dem Anlegen den
Desk neu laden. Ein Test prüft, dass zu jedem Unter-Symbol beide Dateien existieren.

**Frappe ab 16.51:** Der Desk liest nur noch den Doctype `Sidebar`; `Workspace
Sidebar` ist wirkungslos, und `workspace_sidebar/` wird nicht mehr importiert
(`frappe/model/sync.py`). Ein Symbol zeigt über das Modul auf die Seitenleiste
(`frappe.boot.module_sidebars`), deshalb tragen die beiden Dateien
`"module": "Fahrtenbuch"` bzw. `"module": "Site Visit"`. Ohne sie hätten
beide Symbole kein Ziel. `workspace_sidebar/` bleibt für ältere Frappe-Stände
im Repo.

Frappe überspringt dabei Datensätze, die jünger als die Datei sind – etwa
die Symbole, die eine frühere Version der App automatisch erzeugen ließ.
`after_install`/`after_migrate` laden deshalb jeden Eintrag neu aus der
Datei, dessen Zeitstempel nicht mit ihr übereinstimmt. Nach einer Änderung an
einer dieser Dateien also immer `modified` hochsetzen.

Sichtbar ist das App-Symbol für System Manager, Projects Manager, Projects
User, Accounts User und Employee (`desk.check_app_permission`); die einzelnen
Einträge der Seitenleisten blendet Frappe nach Leserecht aus.
`before_uninstall` entfernt Symbole und Seitenleisten selbst: Frappe sucht
die Symbole unter dem App-Namen und fände „Zeit & Projekt" nicht, und das
Löschen der Seitenleisten schreibt Frappe nur bei `--dry-run` fest. Gelöscht
wird ohne `on_trash`, das im `developer_mode` sonst auch die JSON-Dateien in
der App entfernen würde.

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

**Einstellungen:** Alle Einstellungen der App liegen in *Zeit Projekt Einstellungen* (eine
Single). Schreiben darf nur der System Manager; Accounts User/Manager und Projects User
dürfen lesen. Der Abschnitt *Kilometerstand-Erkennung* (mit dem API-Schlüssel) hat
`permlevel` 1 und ist nur für den System Manager sichtbar. Techniker bekommen die
Vorbelegungen über `get_fahrt_defaults` (läuft serverseitig und gibt nur unkritische Werte
zurück). Das Laden der Modellliste (Auswahlfeld „Modell") ist System Managern vorbehalten (der Server ruft
dabei eine frei angegebene URL ab). Die frühere Single „Fahrtenbuch Einstellungen" wurde
zusammengeführt (Patch `zeit_projekt.patches.einstellungen_zusammenfuehren`: Werte
übernehmen, API-Schlüssel aus `__Auth` mitnehmen, Doctype löschen).

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
Kundeneinsatz samt Zeitblatt, Taktung, Überschneidung, Pausen, Zusatzartikel im
Auftrag (Preis, fremder Kunde, „Neuer Auftrag“, Entwurf, Berichtigung,
ausgeschlossene Artikelgruppen), Zeitimport mit Auftragsfilter und
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
- Standort bei Beginn und Ende gibt es für die Fahrt (optional, siehe `fahrtenbuch.md`); offen: dasselbe für den Kundeneinsatz und eine laufende Aufzeichnung (im Browser nur im Vordergrund zuverlässig, sonst eine Tracker-App).
- Externes Signaturpad statt Finger/Stift.
- Custom Fields oder Property Setter, die später über die Oberfläche
  entstehen, gehören nicht automatisch zur App – in `install.py`
  nachtragen, dann entfernt die Deinstallation sie mit.
