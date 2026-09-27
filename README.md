# Zeit & Projekt

Frappe-App für ERPNext v15/v16. Enthält drei zuvor getrennte Apps als
Module in **einer** App (siehe "Herkunft" unten):

1. **Zeiterfassung als Einzelpositionen** (Modul „Zeit Projekt") – Knopf in
   der Ausgangsrechnung, der abrechenbare Zeiten holt und pro Zeitbuchung
   eine eigene Rechnungsposition erzeugt (Artikel aus der Aktivitätsart,
   Preis aus dem Artikel, Beschreibung mit Datum/Uhrzeit, Liefertermin =
   Leistungstag).
2. **Projekt aus Auftrag** (Modul „Zeit Projekt") – Haken im Auftrag, der
   beim Bestätigen automatisch ein Projekt anlegt, verknüpft und direkt
   dorthin springt.
3. **Fahrtenbuch** (Modul „Fahrtenbuch") – Fahrten zum Kunden dokumentieren,
   Kilometerstand per Fotoerkennung erfassen und optional automatisch
   abrechnen.
4. **Site Visit** (Modul „Site Visit") – Kundeneinsätze vor Ort
   dokumentieren (Zeit, Fotos, Unterschrift, Zusatzartikel) und daraus
   automatisch ein abrechenbares Zeitblatt erzeugen.

Die vier Funktionen sind über gemeinsame Kern-Doctypes (Activity Type,
Project, Sales Order, Timesheet) locker verzahnt – siehe "Zusammenspiel der
Module" unten.

---

## Herkunft

Diese App ist aus drei ursprünglich unabhängigen, locker gekoppelten
Schwester-Apps zu **einer** App zusammengeführt:

- [`zeit_projekt`](https://github.com/nienhausdavid/zeit_projekt) (Basis
  dieser App, Modul „Zeit Projekt")
- [`fahrtenbuch`](https://github.com/nienhausdavid/fahrtenbuch) (Modul
  „Fahrtenbuch")
- [`site_visit`](https://github.com/nienhausdavid/site_visit) (Modul
  „Site Visit")

Die drei Repositories bleiben als eigenständige, installierbare Apps
bestehen; diese Zusammenführung ist eine bewusste Alternative dazu, alle
drei getrennt auf derselben Site zu installieren (dort funktioniert die
Kopplung ohne jede Code-Änderung, siehe die READMEs der Einzel-Apps). Wer
die drei Funktionsbereiche **unabhängig voneinander** installieren oder
deinstallieren will, ist mit den getrennten Apps besser bedient – in dieser
zusammengeführten App gehören alle drei zu ein und derselben Installation.

---

## Aufbau

```
zeit_projekt/
├── pyproject.toml
├── license.txt
├── README.md
└── zeit_projekt/
    ├── __init__.py            # Versionsnummer + pdf_on_submit-Chrome-Patch
    ├── hooks.py               # doctype_js + doc_events + Install-Hooks + Dashboards
    ├── install.py             # Custom Fields anlegen/entfernen, PDF-on-Submit-Kopplung
    ├── modules.txt            # "Zeit Projekt", "Fahrtenbuch", "Site Visit"
    ├── patches.txt
    ├── patches/
    │   └── set_project_trip_toggle_defaults.py
    ├── public/
    │   ├── js/
    │   │   ├── sales_invoice.js         # Import-Knopf und Positionslogik
    │   │   ├── sales_order.js           # Hinweise + Sprung zum Projekt nach dem Buchen
    │   │   ├── fahrtenbuch.js           # Fahrt-Formular: Defaults, Timer, OCR-Trigger
    │   │   ├── fahrtenbuch_einstellungen.js  # "Modelle abrufen"-Button
    │   │   ├── project.js               # "Fahrt mit Timer starten"-Button im Projekt
    │   │   └── site_visit.js            # Site-Visit-Formular: Defaults, Timer, Neuer-Auftrag-Dialog
    │   └── images/
    │       ├── fahrtenbuch-logo.svg
    │       └── site_visit-logo.svg
    ├── translations/
    │   ├── en.csv             # Englische Übersetzung (Quelle: Deutsch, aus Fahrtenbuch)
    │   └── de.csv             # Deutsche Übersetzung (Quelle: Englisch, aus Site Visit)
    ├── workspace_sidebar/
    │   └── site_visits.json   # Eigene Sidebar (nur Site Visit + Timesheet)
    ├── zeit_projekt/          # Modul "Zeit Projekt"
    │   ├── billing.py             # Positionen in Aufträge übernehmen/entfernen (Preis aus ERPNext)
    │   ├── technician.py          # eingeschränkte Link-Suchen für Techniker
    │   ├── sales_invoice.py       # Zeitimport nur für den Rechnungskunden
    │   ├── sales_order.py         # Projektanlage in before_submit
    │   ├── pdf.py                 # optional: Chrome als PDF-Generator erzwingen
    │   └── doctype/zeit_projekt_einstellungen/
    ├── fahrtenbuch/           # Modul "Fahrtenbuch"
    │   ├── fahrtenbuch.py         # before_submit/on_cancel (Abrechnung), get_odometer_reading, ...
    │   ├── ocr.py                 # Kilometerstand per OpenAI-kompatibler Vision-API
    │   ├── project_dashboard.py
    │   └── doctype/{fahrt,fahrtenbuch_einstellungen}/
    └── site_visit/            # Modul "Site Visit"
        ├── site_visit.py          # before_submit/on_cancel/create_sales_order
        ├── project_dashboard.py
        ├── doctype/{site_visit,site_visit_item,site_visit_photo}/
        ├── print_format/site_visit_report/
        └── workspace/site_visits/
```

Die Formular-Skripte sind **Dateien**, keine Client-Script-Datensätze. Sie
verschwinden restlos mit der App und unterliegen nicht dem
Client-Script-Cache im Browser.

---

## Zusammenspiel der Module

- **Fahrtenbuch → Site Visit:** Eine Fahrt lässt sich optional mit einem
  Site Visit verknüpfen (Feld `site_visit` auf „Fahrt") – Kunde, Projekt und
  Auftrag werden dann automatisch übernommen.
- **Site Visit → Zeit Projekt:** Das beim Buchen eines Site Visit
  automatisch erzeugte, gebuchte Timesheet (`is_billable=1`, mit Kunde und
  Projekt) taucht im „Zeiten aus Zeiterfassung importieren"-Dialog der
  Ausgangsrechnung dieses Kunden auf.
- **Fahrtenbuch/Site Visit → Projekt-Formular:** Beide ergänzen die
  „Verknüpfungen"-Liste im Projekt-Formular (Fahrten bzw. Site Visits) über
  `override_doctype_dashboards`; Frappe ruft beide Einträge nacheinander auf.
- **Fahrtenbuch/Site Visit → Auftrag:** Beide übernehmen Positionen in den
  verknüpften Auftrag über dieselbe Logik (`zeit_projekt/billing.py`), siehe
  „Abrechnung über den Auftrag" unten.

Die früheren Einzel-Apps `fahrtenbuch` und `site_visit` dürfen **nicht**
zusätzlich installiert sein: sie bringen dieselben Module und Doctypes mit,
die Hooks liefen doppelt. `before_install` bzw. `before_app_install` brechen
die Installation in diesem Fall ab.

---

## Vor der Installation anpassen

In `pyproject.toml` und `zeit_projekt/hooks.py` Name, E-Mail und
Beschreibung eintragen. Willst du die App anders nennen, muss der Name an
vier Stellen konsistent sein: Ordnername, Paketordner, `app_name` in
`hooks.py` und `name` in `pyproject.toml` – dazu alle dotted paths in
`hooks.py`/`install.py`/den `public/js/*.js`-Dateien, die mit `zeit_projekt.`
beginnen.

---

## Installation (eigener Bench)

```bash
cd ~/frappe-bench
bench get-app https://github.com/<dein-user>/zeit_projekt.git
bench --site <deine-site> install-app zeit_projekt
bench build --app zeit_projekt
bench --site <deine-site> clear-cache
```

Die App bringt `Pillow` als Python-Abhängigkeit mit (für die
Kilometerstand-Erkennung im Fahrtenbuch-Modul, siehe `fahrtenbuch/ocr.py`) –
wird von `bench get-app`/`install-app` automatisch installiert.

## Installation (Frappe Cloud)

Eigene Apps brauchen dort ein Git-Repository und eine eigene Bench-Gruppe
(auf den kleinen Shared-Plänen nicht möglich).

1. Repository auf GitHub anlegen und den Inhalt dieses Ordners hochladen
2. In Frappe Cloud: Bench-Gruppe → *Apps* → *Add App* → *From GitHub*
3. Deploy anstoßen, danach die App auf der Site installieren

---

## Deinstallation

```bash
bench --site <deine-site> uninstall-app zeit_projekt --dry-run   # nur anzeigen
bench --site <deine-site> uninstall-app zeit_projekt
```

**Was dabei entfernt wird:**

- die drei Custom Fields (`before_uninstall`)
- die Doctypes „Fahrt", „Fahrtenbuch Einstellungen", „Site Visit", „Site
  Visit Item", „Site Visit Photo"
- die Module „Zeit Projekt", „Fahrtenbuch", „Site Visit" und alles, was
  daran hängt (inkl. Print Format, Workspace)
- die Formular-Skripte, da sie reiner Code sind
- die Zeile „Site Visit" in `PDF on Submit Settings` (nur falls
  `pdf_on_submit` installiert ist)
- das Desktop-Symbol „Zeit & Projekt" samt untergeordneten Symbolen
  (Frappe selbst sucht es unter dem App-Namen und fände es nicht)

**Was bewusst bestehen bleibt:**

- alle angelegten Projekte
- alle geschriebenen Rechnungspositionen, auch in gebuchten Belegen
- die Verknüpfungen zwischen Auftrag und Projekt
- bereits gebuchte Fahrten und Site Visits (inkl. Fotos/Unterschrift als
  Daten, auch wenn die Doctype-Definition entfernt wird)
- bereits angelegte und gebuchte Timesheets, auch aus einem später
  stornierten Site Visit
- bereits in Aufträge übernommene Positionen (Fahrzeit, Kilometer,
  Zusatzartikel) – die Auftragspositionen selbst gehören nicht zu dieser App

**Achtung:** Beim Löschen eines Custom Fields wird die Spalte aus der
Tabelle entfernt. Die Zuordnungen *Aktivitätsart → Dienstleistungsartikel*
sind danach weg. Frappe legt vor dem Deinstallieren automatisch ein Backup
an (außer mit `--no-backup`).

---

## Einstellungen

### Zeit Projekt Einstellungen

Unter **Zeit Projekt Einstellungen** (Suchleiste oder
`/app/zeit-projekt-einstellungen`) lässt sich das Verhalten des Imports
umstellen:

**Erste Zeile der Positionsbeschreibung**

| Auswahl | Ergebnis in der Position |
|---|---|
| *Nur Datum und Uhrzeit* (Standard) | `05.05.2026 09:51-13:51 Uhr` – der Artikelname steht ohnehin schon in der Position |
| *Aktivitätsart voranstellen* | `Ausführung – 05.05.2026 09:51-13:51 Uhr` |
| *Bezeichnung für Rechnung, sonst Aktivitätsart* | nutzt das Feld `custom_rechnungstext` der Aktivitätsart, sonst deren Namen |

Die dritte Variante lohnt nur, wenn mehrere Aktivitätsarten auf denselben
Artikel zeigen – dann ist die Bezeichnung die einzige Unterscheidung auf der
Rechnung. In den ersten beiden Modi kann das Feld *Bezeichnung für
Rechnung* leer bleiben.

Der Freitext aus der Zeitbuchung steht in allen drei Varianten darunter.

**Liefertermin der Position:** Beginn (Standard) oder Ende der Zeitbuchung.
Relevant nur bei Buchungen über Mitternacht.

Der Import holt nur Zeiten des **Rechnungskunden**: Kunde des Projekts der
Zeitbuchung, sonst Kunde des Zeitblatts. Zeiten ohne Kunde und Projekt
werden ausgelassen und gemeldet. „Vorhandene Positionen ersetzen" ist
standardmäßig aus.

**PDFs immer mit Chrome erzeugen** (Standard: aus): nur für Server, auf
denen wkhtmltopdf grundsätzlich scheitert. Setzt für PDF-Download,
Druckansicht und die automatischen PDFs von `pdf_on_submit` den
Chrome-Generator – für **alle** Doctypes der Site. Chromium muss für Frappe
eingerichtet sein, sonst scheitern alle PDFs.

### Fahrtenbuch Einstellungen

Doctype **"Fahrtenbuch Einstellungen"** öffnen (Suche im Awesomebar):

- **API-URL**: Basis-URL einer OpenAI-kompatiblen API ohne
  `/chat/completions` am Ende, z. B. `http://<ip-des-servers>:11434/v1` für
  [Ollama](https://ollama.com/) oder `https://api.openai.com/v1`
- **Modell**: z. B. `qwen3.5:9b` – Button **"Verfügbare Modelle abrufen"**
  fragt die eingetragene API direkt nach den dort tatsächlich vorhandenen
  Modellen (`GET .../models`) und zeigt sie zur Auswahl an, testet dabei
  auch eine gerade eingetippte, noch nicht gespeicherte API-URL
- **API-Schlüssel**: nur nötig, falls die API einen verlangt (bei den
  meisten lokal/selbst gehosteten Servern leer lassen)
- **Artikel Fahrzeit**: Vorbelegung für das gleichnamige Pflichtfeld auf
  einer neuen Fahrt – bleibt dort weiterhin pro Fahrt änderbar
- **Timer automatisch starten** / **Kamera automatisch öffnen**: steuert das
  Verhalten beim Anlegen einer Fahrt über die "+"-Verknüpfung bzw. den
  Button im Projekt-Formular (Standard: beide an)

**Keine Standardwerte hinterlegt** – ohne Eintrag bleibt die automatische
Kilometerstand-Erkennung schlicht deaktiviert; die Fahrt lässt sich immer
ganz normal von Hand ausfüllen und buchen.

---

## Nach der Installation

Die App deaktiviert vorhandene Client Scripts mit den Namen „Zeiterfassung
als Einzelpositionen", „Auftrag: Projekt erstellen" und „Auftrag: Kommission
und Projekt", damit die Funktionen nicht doppelt laufen. Löschen musst du
sie selbst.

Dann noch einrichten:

1. Je Aktivitätsart einen **Dienstleistungsartikel** eintragen (Zeit
   Projekt) und einen sinnvollen **Stundensatz** hinterlegen (Site Visit)
2. Für jeden Dienstleistungsartikel einen **Verkaufspreis** in der
   Standard-Verkaufspreisliste hinterlegen
3. Prüfen, dass der Projekttyp **External** existiert
4. Für die Fahrtenbuch-Abrechnung einen Artikel für die **Fahrzeit**
   (Pflicht) und optional einen Artikel für **Kilometergeld** hinterlegen –
   beide mit Verkaufspreis. Gleiches gilt für alle Artikel, die als
   Zusatzartikel im Site Visit verwendet werden: ohne Preis lässt sich der
   Beleg nicht buchen.
5. Neue Auftragspositionen brauchen ein **Lager** (ERPNext-Vorgabe für
   Aufträge, auch bei Dienstleistungen): Standardlager am Artikel, am
   Auftrag („Set Source Warehouse") oder in den Lagereinstellungen setzen.
6. Optional: **Fahrtenbuch Einstellungen** ausfüllen für die
   Kilometerstand-Erkennung per Foto (siehe oben)
7. Optional: [`pdf_on_submit`](https://github.com/alyf-de/erpnext_pdf-on-submit)
   installieren, damit Site Visits beim Buchen automatisch ein PDF erhalten
   (siehe "Automatische PDF-Erzeugung" unten)

---

## Fahrtenbuch

Ein Techniker legt pro Fahrt eine **Fahrt** an: Zeitraum, Start/Ziel, Fotos
vom Tacho am Anfang und am Ende. Der Kilometerstand wird dabei per
KI-Bilderkennung automatisch vorgeschlagen, lässt sich aber jederzeit von
Hand eintragen oder korrigieren. Beim Buchen wird die Fahrzeit immer, die
gefahrene Strecke optional als Position in einen Auftrag übernommen.

Kein Finanzamt-taugliches Fahrtenbuch: keine Geschäftlich/Privat-Kennzeichnung,
keine lückenlose Erfassung. Ein praktisches Log für Kundenbesuche.

### Kilometerstand-Erkennung

Die App liest den Kilometerstand aus einem Tacho-Foto über eine beliebige
**OpenAI-kompatible API** aus (`fahrtenbuch/ocr.py`, Chat-Completions-Format
mit Bild) – funktioniert damit z. B. mit Ollama, LM Studio oder echtem
OpenAI. Ist die API nicht erreichbar/nicht konfiguriert oder erkennt nichts
Eindeutiges, bleibt das Kilometerstand-Feld einfach leer bzw. unverändert –
die Erkennung ist reine Komfortfunktion.

Echte Handy-Fotos werden vor dem Versand automatisch auf max. 1024px
Kantenlänge herunterskaliert (`MAX_IMAGE_DIMENSION` in `ocr.py`).

### Timer

"Timer starten"/"Timer stoppen" (im Formular und beim Anlegen aus dem
Projekt heraus) setzen nicht nur `start_time`/`end_time`, sondern
**speichern sofort** – genau wie ERPNexts eigener Timesheet-Timer. Ohne das
sofortige Speichern ginge ein laufender Timer bei einem Reload oder
Schließen der Seite verloren.

Damit ein Entwurf mit nur laufendem Timer überhaupt speicherbar ist, sind
Endzeit, beide Kilometerstände, Auftrag und Artikel Fahrzeit **nicht mehr
auf Feldebene Pflicht** – sie werden erst beim Buchen selbst geprüft
(`Fahrt.before_submit` in `fahrt.py`). Leere Kilometerstände speichert
Frappe als 0; die Prüfung behandelt 0 deshalb als „nicht eingetragen".

### Einrichtung

- Im Projekt-Formular gibt es unter "Verknüpfungen" eine Gruppe "Fahrten".
  Die "+"-Verknüpfung dort legt eine neue Fahrt an (über `frm.make_methods`).
  Zusätzlich ein eigenständig sichtbarer Button **"Fahrt mit Timer
  starten"** oben im Formular.
- Beide Wege legen die Fahrt standardmäßig mit bereits laufendem Timer an
  (Projekt/Kunde vorbelegt, Startzeit = jetzt, sofort gespeichert) **und**
  öffnen direkt danach die Kamera für das Start-Kilometerstand-Foto.

---

## Site Visit

Ein Techniker legt pro Einsatz einen **Site Visit** an: Zeitraum,
Aktivitätsart, Fotos, optional die Unterschrift des Kunden direkt auf dem
eigenen Gerät. Beim Buchen (Submit) wird automatisch ein **Timesheet**
angelegt, gebucht und verknüpft – bereit zur Abrechnung.

### Auftrag

`sales_order` ist Pflichtfeld – jeder Einsatz muss einem Auftrag zugeordnet
sein. Gibt es noch keinen, öffnet der Button **"New Sales Order"** im
Formular einen Dialog, in dem sich die **Kundenreferenz** eintragen lässt.
Der Site Visit wird vorher gespeichert; Kunde, Firma, Projekt und Artikel
liest der Server aus dem gespeicherten Beleg, die Preise aus ERPNext.
Der neue Auftrag entsteht als **Entwurf** (Liefertermin = Einsatzdatum,
frühestens heute) und übernimmt die Zusatzartikel als Startpositionen.

**Zusätzliche Artikel** (`extra_items`): vor Ort zusätzlich benötigtes
Material. Der Preis ist schreibgeschützt und wird beim Speichern aus der
Preisliste des Kunden bzw. des Auftrags ermittelt. Beim Buchen des Site
Visit werden neue (noch nicht übernommene) Zeilen in den verknüpften
Auftrag aufgenommen – siehe „Abrechnung über den Auftrag".

Das automatisch erzeugte Zeitblatt wird ohne Rollenprüfung angelegt und
gebucht (maßgeblich ist die Berechtigung auf den Site Visit): die Rolle
„Employee" darf Zeitblätter in ERPNext nicht buchen.

### Timer

Wie beim Fahrtenbuch: "Start Timer"/"Stop Timer" speichern sofort, Kunde/
Aktivitätsart/Auftrag/Endzeit sind deshalb erst beim Buchen
(`before_submit` in `site_visit.py`) Pflicht, nicht auf Feldebene.

### Automatische PDF-Erzeugung beim Buchen

Die App liefert ein eigenes Print Format **"Site Visit Report"** mit
(Kopfbereich, Kundendaten, Fotogalerie, Unterschriftsblock). Für die
**automatische** PDF-Anlage beim Buchen braucht es zusätzlich einen
PDF-Automatisierungsmechanismus wie
[`pdf_on_submit`](https://github.com/alyf-de/erpnext_pdf-on-submit) (bewusst
keine harte Abhängigkeit, funktioniert auch ohne). Ist `pdf_on_submit` zum
Zeitpunkt der Installation bereits vorhanden, trägt `install.py`
automatisch die Zeile „Site Visit" in dessen **PDF on Submit Settings**
ein.

Ist in „Zeit Projekt Einstellungen" **PDFs immer mit Chrome erzeugen**
aktiv, läuft auch die automatische PDF-Erzeugung von `pdf_on_submit` über
Chrome (`zeit_projekt/__init__.py` ersetzt dazu
`pdf_on_submit.attach_pdf.get_pdf_data()`); sonst bleibt `pdf_on_submit`
unverändert.

---

## Abrechnung über den Auftrag

Fahrt (Fahrzeit, optional Kilometer) und Site Visit (Zusatzartikel)
übernehmen beim Buchen Positionen in den verknüpften Auftrag – auch in einen
bereits gebuchten, über
`erpnext.controllers.accounts_controller.update_child_qty_rate` (dieselbe
Funktion wie der „Update Items"-Dialog). Gemeinsame Logik in
`zeit_projekt/zeit_projekt/billing.py`:

- **Preis** kommt aus ERPNext (Preisliste, Preisregeln, Währung des
  Auftrags). Ohne Preis bricht das Buchen mit einer klaren Meldung ab –
  sonst landete die Position mit 0 im Auftrag.
- **Beschreibung** ist je Beleg eindeutig (z. B. „Fahrzeit FB-2026-00001,
  27.09.2026, Werkstatt → Kunde"), damit mehrere Fahrten im selben Auftrag
  nicht an ERPNexts Duplikatsprüfung scheitern.
- Der **Auftrag muss offen sein und zum Kunden des Belegs gehören**.
- **Stornieren** entfernt genau die beim Buchen angelegten Positionen
  wieder (bereits gelieferte/fakturierte Positionen lehnt ERPNext ab – dann
  bleibt auch das Stornieren blockiert). Ein berichtigter Beleg übernimmt
  sie beim erneuten Buchen neu, ohne Dubletten.

---

## Sprache

Die App liefert zwei Übersetzungsdateien mit, je nach Herkunfts-Modul in
unterschiedlicher Richtung:

- `translations/en.csv`: Quelle Deutsch (Module „Zeit Projekt" und
  „Fahrtenbuch", auf Deutsch geschrieben), übersetzt für Nutzer mit Sprache
  "Englisch".
- `translations/de.csv`: Quelle Englisch (Modul „Site Visit", auf Englisch
  geschrieben), übersetzt für Nutzer mit Sprache "Deutsch".

Frappe wählt die passende Datei automatisch anhand der Nutzersprache.
Standardbegriffe, die bereits über Frappe/ERPNext selbst übersetzt sind
(z. B. "Customer", "Employee", "Sales Order", "Timesheet"), sind bewusst
**nicht** noch einmal in den CSV-Dateien enthalten.

App-Übersetzungen gelten in Frappe für die **ganze Site**. Damit Einträge
wie „Duration" → „Zeitraum" nicht überall in ERPNext greifen, trägt jede
Zeile in `de.csv` den DocType als dritte Spalte (Kontext). Frappe übersetzt
Feldbezeichnungen automatisch mit diesem Kontext; Meldungen im Code geben
ihn explizit mit (`_("…", context="Site Visit")`,
`__("…", null, "Site Visit")`). Nur die eindeutigen DocType-Namen stehen
ohne Kontext.

Nach Änderungen an Texten im Code: neue/geänderte Strings in der
passenden CSV ergänzen (bei `de.csv` mit Kontext), sonst bleiben sie in der
jeweiligen Zielsprache unübersetzt (Ausgangssprache als Fallback).

---

## Eigene App im Desk

Fahrtenbuch und Site Visit bringen je ein eigenes Logo mit
(`public/images/*-logo.svg`) und registrieren sich über
`add_to_apps_screen` in `hooks.py` als eigene Kacheln auf der
Apps-Übersicht (`/apps`): Fahrtenbuch mit direktem Sprung in die
Fahrt-Liste, Site Visit mit einer eigenen Workspace (Verknüpfungen zu
"Site Visit" und "Timesheet"). Das Modul „Zeit Projekt" selbst hat keine
eigene Kachel – es wirkt rein als Ergänzung auf Sales-Invoice-/
Sales-Order-Formularen.

Auf dem **Desk von v16** (App-Symbole) legt Frappe beim Installieren **ein**
Symbol je App an: „Zeit & Projekt", mit Logo und Ziel des **ersten**
`add_to_apps_screen`-Eintrags (Fahrtenbuch → Fahrt-Liste); „Site Visits"
erscheint als untergeordnetes Symbol. Diese Symbole entstehen nur bei
`install-app`, nicht bei `migrate`. Auf einer Site, auf der die App schon
vor dieser Version installiert war, einmalig nachholen:

```bash
bench --site <deine-site> execute frappe.utils.install.auto_generate_icons_and_sidebar
```

## Berechtigungen

**Fahrt / Site Visit**

| Rolle | Lesen | Schreiben | Anlegen | Buchen | Stornieren |
|---|---|---|---|---|---|
| System Manager | ✓ | ✓ | ✓ | ✓ | ✓ |
| Projects Manager | ✓ | ✓ | ✓ | ✓ | ✓ |
| Employee | eigene | eigene | ✓ | eigene | – |
| Projects User | ✓ | – | – | – | – |
| Accounts User | ✓ | – | – | – | – |

Ein gebuchter, unterschriebener Site Visit gilt als Bestätigung gegenüber
dem Kunden – nur Projects Manager/System Manager können ihn stornieren.

**Techniker mit nur der Rolle „Employee"** dürfen in ERPNext Kunde,
Auftrag, Artikel und Fahrzeug nicht lesen. Damit sie Fahrten und Site
Visits trotzdem ausfüllen können, nutzen die Formulare eigene Link-Suchen
und Detail-Abfragen (`zeit_projekt/zeit_projekt/technician.py`): nur Name
und Bezeichnung, nur offene Aufträge, nur verkaufsfähige Artikel – und nur
für Nutzer mit Anlege- oder Schreibrecht auf Fahrt bzw. Site Visit. Die
Übernahme in den Auftrag läuft serverseitig als Administrator; geprüft wird
dabei, dass der Auftrag offen ist und zum Kunden des Belegs gehört.

**Zeit Projekt Einstellungen / Fahrtenbuch Einstellungen**

Nur System Manager kann schreiben; Zeit Projekt Einstellungen ist zusätzlich
für Accounts User/Accounts Manager/Projects User lesbar. Fahrtenbuch
Einstellungen enthalten den API-Schlüssel und sind nur für System Manager
lesbar; das Fahrt-Formular holt die drei unkritischen Vorbelegungen über
`get_fahrt_defaults`. „Verfügbare Modelle abrufen" steht nur System
Managern zur Verfügung (der Server ruft dabei eine frei angegebene URL ab),
die Kilometerstand-Erkennung nur für Dateien, die der Nutzer selbst lesen
darf.

Es gibt bewusst keine eigene, engere Techniker-Rolle als Fixture (Rollen
sind nicht modulgebunden und würden beim Deinstallieren als Karteileiche
zurückbleiben); wer den Zugriff über die Standardrolle "Employee" hinaus
einschränken will, legt manuell eine eigene Rolle an.

---

## Erweiterungsideen

- **"Neuer Auftrag"-Dialog** direkt aus der Fahrt heraus (wie bei Site
  Visit), statt nur einen bestehenden Auftrag wählen zu können.
- **GPS/Adress-basierte automatische km-Berechnung** als Alternative/
  Ergänzung zum Kilometerstand-Foto.
- **Mehrere Fahrten/Einsätze pro Tag zusammenfassen** statt Einzelbuchung.
- **Externes USB/Bluetooth-Signaturpad** statt Finger/Stift auf dem
  Touch-Bildschirm für die Site-Visit-Unterschrift.
- Mehrere Zeitsegmente/Pausen pro Site Visit statt eines durchgehenden
  Blocks.
- GPS/Standort-Erfassung beim Anlegen von Fahrt/Site Visit.
- Direkte Rechnungs-/Angebotserstellung aus dem Site Visit heraus.
- Custom Fields, die du später über die Oberfläche anlegst, gehören nicht
  automatisch der App. Trage sie in `CUSTOM_FIELDS` in `install.py` nach,
  dann werden sie beim Deinstallieren mitentfernt. Für Property Setter gilt
  dasselbe (im `after_install` erzeugen oder als Fixture exportieren, Modul
  auf eines der drei Module setzen).
