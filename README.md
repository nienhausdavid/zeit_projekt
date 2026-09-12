# Zeit & Projekt

Frappe-App für ERPNext v15/v16 mit zwei Funktionen:

1. **Zeiterfassung als Einzelpositionen** – Knopf in der Ausgangsrechnung, der abrechenbare Zeiten holt und pro Zeitbuchung eine eigene Rechnungsposition erzeugt (Artikel aus der Aktivitätsart, Preis aus dem Artikel, Beschreibung mit Datum/Uhrzeit, Liefertermin = Leistungstag).
2. **Projekt aus Auftrag** – Haken im Auftrag, der beim Bestätigen automatisch ein Projekt anlegt, verknüpft und direkt dorthin springt.

---

## Aufbau

```
zeit_projekt/
├── pyproject.toml
├── license.txt
├── README.md
└── zeit_projekt/
    ├── __init__.py           # Versionsnummer
    ├── hooks.py              # doctype_js + doc_events + Install-Hooks
    ├── install.py            # Custom Fields anlegen / entfernen
    ├── sales_order.py        # Projektanlage in before_submit (serverseitig)
    ├── modules.txt           # Modulname "Zeit Projekt"
    ├── patches.txt
    ├── public/js/
    │   ├── sales_invoice.js  # Import-Knopf und Positionslogik
    │   └── sales_order.js    # Hinweise + Sprung zum Projekt nach dem Buchen
    └── zeit_projekt/         # Modulordner (für DocTypes)
        └── __init__.py
```

Die Formular-Skripte sind **Dateien**, keine Client-Script-Datensätze. Sie verschwinden restlos mit der App und unterliegen nicht dem Client-Script-Cache im Browser.

---

## Vor der Installation anpassen

In `pyproject.toml` und `zeit_projekt/hooks.py` Name, E-Mail und Beschreibung eintragen. Willst du die App anders nennen, muss der Name an vier Stellen konsistent sein: Ordnername, Paketordner, `app_name` in `hooks.py` und `name` in `pyproject.toml` – dazu die Pfade in `after_install` / `before_uninstall`.

---

## Installation (eigener Bench)

```bash
cd ~/frappe-bench
bench get-app https://github.com/<dein-user>/zeit_projekt.git
bench --site <deine-site> install-app zeit_projekt
bench build --app zeit_projekt
bench --site <deine-site> clear-cache
```

## Installation (Frappe Cloud)

Eigene Apps brauchen dort ein Git-Repository und eine eigene Bench-Gruppe (auf den kleinen Shared-Plänen nicht möglich).

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
- das Modul „Zeit Projekt" und alles, was daran hängt
- die Formular-Skripte, da sie reiner Code sind

**Was bewusst bestehen bleibt:**

- alle angelegten Projekte
- alle geschriebenen Rechnungspositionen, auch in gebuchten Belegen
- die Verknüpfungen zwischen Auftrag und Projekt

**Achtung:** Beim Löschen eines Custom Fields wird die Spalte aus der Tabelle entfernt. Die Zuordnungen *Aktivitätsart → Dienstleistungsartikel* sind danach weg. Frappe legt vor dem Deinstallieren automatisch ein Backup an (außer mit `--no-backup`).

---

## Einstellungen

Unter **Zeit Projekt Einstellungen** (Suchleiste oder `/app/zeit-projekt-einstellungen`) lässt sich das Verhalten des Imports umstellen:

**Erste Zeile der Positionsbeschreibung**

| Auswahl | Ergebnis in der Position |
|---|---|
| *Nur Datum und Uhrzeit* (Standard) | `05.05.2026 09:51-13:51 Uhr` – der Artikelname steht ohnehin schon in der Position |
| *Aktivitätsart voranstellen* | `Ausführung – 05.05.2026 09:51-13:51 Uhr` |
| *Bezeichnung für Rechnung, sonst Aktivitätsart* | nutzt das Feld `custom_rechnungstext` der Aktivitätsart, sonst deren Namen |

Die dritte Variante lohnt nur, wenn mehrere Aktivitätsarten auf denselben Artikel zeigen – dann ist die Bezeichnung die einzige Unterscheidung auf der Rechnung. In den ersten beiden Modi kann das Feld *Bezeichnung für Rechnung* leer bleiben.

Der Freitext aus der Zeitbuchung steht in allen drei Varianten darunter.

**Liefertermin der Position:** Beginn (Standard) oder Ende der Zeitbuchung. Relevant nur bei Buchungen über Mitternacht.

## Nach der Installation

Die App deaktiviert vorhandene Client Scripts mit den Namen „Zeiterfassung als Einzelpositionen", „Auftrag: Projekt erstellen" und „Auftrag: Kommission und Projekt", damit die Funktionen nicht doppelt laufen. Löschen musst du sie selbst.

Dann noch einrichten:

1. Je Aktivitätsart einen **Dienstleistungsartikel** eintragen
2. Für jeden dieser Artikel einen **Verkaufspreis** in der Standard-Verkaufspreisliste hinterlegen
3. Prüfen, dass der Projekttyp **External** existiert

---

## Erweiterungsideen

- Custom Fields, die du später über die Oberfläche anlegst, gehören nicht automatisch der App. Trage sie in `CUSTOM_FIELDS` in `install.py` nach, dann werden sie beim Deinstallieren mitentfernt.
- Für Property Setter (geänderte Feldeigenschaften am Standard) gilt dasselbe: entweder im `after_install` erzeugen oder als Fixture exportieren und dabei das Modul auf „Zeit Projekt" setzen.
- ~~Serverseitige Logik (etwa die Projektanlage) ließe sich später von JavaScript nach `doc_events` verschieben.~~ Erledigt: Die Projektanlage läuft in `sales_order.py` als `before_submit`-Hook, im selben Request wie das Buchen. Grund: Die alte JS-Variante rief `frappe.client.insert` in einem eigenen Request auf, *bevor* der eigentliche Buchen-Request lief - bei einem doppelten Klick auf Buchen (z. B. auf dem Handy) konnte der zweite Request dann mit einem veralteten Zeitstempel auf "has been modified after you have opened it" laufen, obwohl das Projekt schon korrekt angelegt war. Serverseitig in `before_submit` gibt es diesen zweiten Request nicht mehr, dadurch entfällt das Zeitfenster für den Konflikt vollständig - und es greift jetzt auch bei API-Zugriffen und Massenbuchungen.
