# Zeit & Projekt

Frappe-App für **ERPNext v16**: Arbeits- und Fahrzeiten vor Ort erfassen und
sauber abrechnen.

| Bereich | Was es tut |
|---|---|
| **Kundeneinsatz** (Site Visit) | Einsatz vor Ort mit Timer, Fotos, Kundenunterschrift und Zusatzmaterial dokumentieren; beim Buchen entsteht automatisch ein Zeitblatt. |
| **Fahrtenbuch** | Fahrten mit Timer und Kilometerstand (optional per Fotoerkennung) erfassen; beim Buchen entsteht ein Zeitblatt für die Fahrzeit. |
| **Zeitimport in der Ausgangsrechnung** | Holt offene Zeiten und Fahrt-Kilometer des Rechnungskunden als Einzelpositionen in die Rechnung. |
| **Projekt aus Auftrag** | Haken im Auftrag legt beim Bestätigen automatisch ein Projekt an und verknüpft es. |

## Abrechnung auf einen Blick

```
Kundeneinsatz ──► Zeitblatt (Aktivitätsart des Einsatzes) ─┐
Fahrt ─────────► Zeitblatt (Aktivitätsart „Fahrzeit") ─────┼──► Ausgangsrechnung
Fahrt ─────────► Kilometer ────────────────────────────────┘    (Zeitimport)
Kundeneinsatz ──► Zusatzartikel (Material) ──► Auftrag ──► Lieferung/Rechnung wie gewohnt
```

Zeiten und Kilometer laufen über **einen** Weg – den Zeitimport der
Ausgangsrechnung. Material aus dem Einsatz landet im Auftrag, weil es dort
wie jede andere Auftragsposition geliefert und berechnet wird.

## Installation

```bash
cd ~/frappe-bench
bench get-app https://github.com/<dein-user>/zeit_projekt.git
bench --site <deine-site> install-app zeit_projekt
bench build --app zeit_projekt
bench --site <deine-site> clear-cache
```

Frappe Cloud: Repository in der Bench-Gruppe unter *Apps → Add App → From
GitHub* hinzufügen, deployen, dann auf der Site installieren.

Die früheren Einzel-Apps [`fahrtenbuch`](https://github.com/nienhausdavid/fahrtenbuch)
und [`site_visit`](https://github.com/nienhausdavid/site_visit) sind in dieser
App enthalten und dürfen **nicht** zusätzlich installiert sein – die
Installation bricht sonst ab.

## Einrichtung nach der Installation

1. **Aktivitätsarten**: je Aktivitätsart einen *Dienstleistungsartikel*
   eintragen (daraus wird die Rechnungsposition) und einen Stundensatz
   hinterlegen. Eine Aktivitätsart für die **Fahrzeit** anlegen.
2. **Preise**: Verkaufspreise in der Standard-Verkaufspreisliste für die
   Dienstleistungsartikel, den Kilometer-Artikel und alle Artikel, die als
   Zusatzmaterial im Einsatz verwendet werden.
3. **Lager**: Neue Auftragspositionen brauchen ein Lager (ERPNext-Vorgabe,
   auch für Dienstleistungen) – Standardlager am Artikel, am Auftrag oder in
   den Lagereinstellungen setzen.
4. **Fahrtenbuch Einstellungen**: Aktivitätsart Fahrzeit und
   Kilometer-Artikel als Vorbelegung, optional Taktung der Fahrzeit und die
   API für die Kilometerstand-Erkennung.
5. **Zeit Projekt Einstellungen**: Aufbau der Positionsbeschreibung im
   Zeitimport, Umgang mit Zusatzartikeln ohne Preis, ggf. „PDFs immer mit
   Chrome erzeugen".
6. Projekttyp **External** muss existieren (für „Projekt aus Auftrag").
7. Optional: [`pdf_on_submit`](https://github.com/alyf-de/erpnext_pdf-on-submit)
   installieren, damit Kundeneinsätze beim Buchen automatisch ein PDF
   erhalten.

Auf dem Desk erscheint ein App-Symbol **„Zeit & Projekt"** mit den
Bereichen *Fahrtenbuch* und *Site Visits*.

## Deinstallation

```bash
bench --site <deine-site> uninstall-app zeit_projekt --dry-run   # nur anzeigen
bench --site <deine-site> uninstall-app zeit_projekt
```

Entfernt werden die Doctypes der App (Fahrt, Site Visit, Einstellungen …)
**samt ihrer Tabellen**, die Custom Fields, Desk-Symbole und Seitenleisten.
Zeitblätter, Rechnungen, Aufträge und Projekte bleiben bestehen. Frappe legt
vorher automatisch ein Backup an (außer mit `--no-backup`).

## Dokumentation

- [Abrechnung](docs/abrechnung.md) – Zeitimport, Kilometer, Zusatzartikel, Projekt aus Auftrag, Einstellungen
- [Fahrtenbuch](docs/fahrtenbuch.md) – Fahrt, Timer, Taktung, Kilometerstand-Erkennung
- [Kundeneinsatz](docs/site_visit.md) – Site Visit, Neuer Auftrag, Stornieren, PDF
- [Technik](docs/technik.md) – Aufbau, Rechte, Desk, Sprache, Tests, bekannte Grenzen

## Entwicklung und Tests

```bash
bench --site <test-site> set-config allow_tests true
bench --site <test-site> execute zeit_projekt.zeit_projekt.tests.setup_ci.complete_setup   # nur auf frischer Site
bench --site <test-site> run-tests --app zeit_projekt
```

Die Integrationstests liegen in `zeit_projekt/zeit_projekt/tests/` und laufen
in GitHub Actions (`.github/workflows/ci.yml`) gegen Frappe/ERPNext
`version-16`.

## Herkunft

Zusammengeführt aus drei ursprünglich getrennten Apps:
[`zeit_projekt`](https://github.com/nienhausdavid/zeit_projekt) (Basis),
[`fahrtenbuch`](https://github.com/nienhausdavid/fahrtenbuch) und
[`site_visit`](https://github.com/nienhausdavid/site_visit).
