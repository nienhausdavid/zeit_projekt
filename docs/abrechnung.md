# Abrechnung

Zeiten und Kilometer werden über den **Zeitimport der Ausgangsrechnung**
abgerechnet, Zusatzmaterial aus Kundeneinsätzen über den **Auftrag**.

## Zeitimport in der Ausgangsrechnung

In einer Ausgangsrechnung im Entwurf holt der Knopf **„Zeiten aus
Zeiterfassung importieren"** für einen wählbaren Zeitraum (optional ein
Projekt):

- **Zeitbuchungen**: gebuchte, abrechenbare, noch nicht abgerechnete
  Zeitblatt-Zeilen – aus Kundeneinsätzen, Fahrten oder von Hand erfasst. Pro
  Zeitbuchung entsteht eine eigene Rechnungsposition: Artikel =
  *Dienstleistungsartikel* der Aktivitätsart, Menge = abrechenbare Stunden,
  Preis = Verkaufspreis des Artikels (sonst Stundensatz der Aktivitätsart).
  Zusätzlich wird die Zeitblatt-Tabelle der Rechnung gefüllt – darüber
  markiert ERPNext die Zeiten beim Buchen als abgerechnet.
- **Kilometer**: gebuchte Fahrten mit „Kilometer abrechnen", deren
  Kilometer noch in keiner gebuchten Rechnung stehen. Artikel und Menge
  kommen aus der Fahrt, der Preis aus der Preisliste.

Es werden nur Zeiten und Fahrten des **Rechnungskunden** übernommen (Kunde
des Projekts der Zeitbuchung, sonst Kunde des Zeitblatts bzw. der Fahrt).
Zeiten ohne Kunde und Projekt werden ausgelassen und gemeldet. Bereits in
der Rechnung stehende Zeiten/Fahrten werden bei einem erneuten Import nicht
doppelt übernommen. „Vorhandene Positionen ersetzen" ist standardmäßig aus.

**Auftrag:** Kundeneinsatz und Fahrt tragen beim Buchen ihren Auftrag in die
Zeitbuchung ein (Feld *Auftrag*; bei manuell erfassten Zeiten von Hand
setzbar). Der optionale Filter **„Auftrag"** im Dialog holt nur Zeiten und
Fahrten dieses Auftrags. Jede importierte Zeitposition übernimmt den Auftrag
in ihr Feld *Auftrag* (`sales_order`) – aber nur bei gebuchtem Auftrag, dessen
Projekt leer ist oder dem der Rechnung entspricht: ERPNext vergleicht Kunde,
Firma, Projekt und Währung von Rechnung und Auftrag und lehnt die Rechnung
sonst ab.

**Kilometer genau einmal:** Jede Kilometer-Position verweist über das Feld
*Fahrt (Kilometer)* auf ihre Fahrt. Mit dem Buchen der Rechnung gilt die
Fahrt als abgerechnet; eine zweite Rechnung mit derselben Fahrt wird
abgelehnt, ebenso eine Fahrt eines anderen Kunden. Stornieren der Rechnung
hebt die Markierung wieder auf.

### Positionsbeschreibung (Zeit Projekt Einstellungen)

| Auswahl „Erste Zeile der Positionsbeschreibung" | Ergebnis |
|---|---|
| *Nur Datum und Uhrzeit* (Standard) | `05.05.2026 09:51-13:51 Uhr` – der Artikelname steht ohnehin in der Position |
| *Aktivitätsart voranstellen* | `Ausführung – 05.05.2026 09:51-13:51 Uhr` |
| *Bezeichnung für Rechnung, sonst Aktivitätsart* | Feld *Bezeichnung für Rechnung* der Aktivitätsart, sonst deren Name |

Die dritte Variante lohnt sich, wenn mehrere Aktivitätsarten auf denselben
Artikel zeigen. Der Freitext der Zeitbuchung steht in allen Varianten
darunter.

**Liefertermin der Position:** Beginn (Standard) oder Ende der Zeitbuchung
– wirkt nur, wenn die Rechnungsposition ein Feld `delivery_date` hat (siehe
[Technik – bekannte Grenzen](technik.md#bekannte-grenzen)).

## Zusatzartikel im Auftrag

Beim Buchen eines Kundeneinsatzes werden noch nicht übernommene
Zusatzartikel in den verknüpften Auftrag aufgenommen – in einen Entwurf
direkt, in einen bereits gebuchten über dieselbe ERPNext-Funktion wie der
Dialog „Update Items" (Steuern, Summen und Kreditlimit werden neu berechnet).

- **Preis** aus ERPNext (Preisliste, Preisregeln, Währung des Auftrags).
  Fehlt ein Preis, lässt sich der Einsatz nicht buchen – außer in *Zeit
  Projekt Einstellungen* ist **„Zusatzartikel ohne Verkaufspreis erlauben"**
  aktiv; dann kommt die Position mit 0 und einem Hinweis im Auftragsverlauf.
- **Herkunft**: Jede Position trägt im Feld *Kundeneinsatz* ihren
  Ursprung, die Beschreibung nennt Einsatz und Zeile. Ein Kommentar im
  Auftragsverlauf nennt den Nutzer, der gebucht hat (die Änderung selbst
  läuft technisch als Administrator, weil Techniker keine Auftragsrechte
  haben).
- Der Auftrag muss **offen** sein und **zum Kunden** des Einsatzes gehören.
- **Stornieren** des Einsatzes entfernt genau diese Positionen wieder
  (bereits gelieferte/berechnete Positionen lehnt ERPNext ab – dann bleibt
  auch das Stornieren blockiert). Ein berichtigter Einsatz übernimmt sie beim
  erneuten Buchen genau einmal.

## Abrechnungsstand des Auftrags

ERPNext berechnet „% berechnet" eines Auftrags nur aus dem Betrag seiner
Positionen. Die Einsatzzeit steht aber nicht als Betrag im Auftrag, sondern
in Zeitbuchungen mit dem Feld *Auftrag*. Ohne Korrektur hieße das: Ein über
„Neuer Auftrag" angelegter Auftrag (Summe 0) gilt nach der ersten Rechnung
als „Vollständig berechnet", auch wenn weitere Einsätze offen sind; ein
Auftrag mit Zusatzartikeln gilt als berechnet, sobald die Artikel berechnet
sind – egal ob die Zeit schon abgerechnet ist.

Die App zählt deshalb Positionen und Zeitbuchungen zusammen, gewichtet nach
Betrag: berechnete Positionen plus abgerechnete Zeitbuchungen
(Abrechnungsbetrag) im Verhältnis zur Summe aus beidem. Aktualisiert wird
beim Buchen und Stornieren von Rechnungen, Zeitblättern (auch aus
Kundeneinsatz und Fahrt) und beim Buchen des Auftrags – auch wenn der Auftrag
beim Abrechnen noch ein Entwurf war. Aufträge ohne Zeitbuchungen rechnet
weiter ERPNext allein.

Den Lieferstatus ändert das nicht: Ein Auftrag nur mit Dienstleistungen
bleibt in ERPNext „Zu liefern", solange nicht *Lieferschein überspringen*
gesetzt ist (in ERPNext nur bei Auftragsart *Maintenance* sichtbar).

## Projekt aus Auftrag

Custom Field *„Projekt für diesen Auftrag erstellen"* im Auftrag: Beim
Bestätigen (Buchen) legt ein serverseitiger `before_submit`-Hook ein Projekt
an (Typ *External*, Kunde, Auftrag, Zeitraum) und verknüpft es; danach
springt das Formular zum Projekt (Reiter *Verknüpfungen*). Name des Projekts:
Käuferreferenz (`buyer_reference`, nur mit der App eu_einvoice), sonst
Kundenname, plus Auftragsnummer.

Die Projektanlage läuft bewusst im selben Request wie das Buchen: eine
frühere Variante per JavaScript konnte bei doppeltem Klick einen „has been
modified after you have opened it"-Konflikt auslösen.

## PDF-Erzeugung

**PDFs immer mit Chrome erzeugen** (*Zeit Projekt Einstellungen*, Standard
aus): nur für Server, auf denen wkhtmltopdf grundsätzlich scheitert. Setzt
für PDF-Download, Druckansicht und die automatischen PDFs von `pdf_on_submit`
den Chrome-Generator – für **alle** Doctypes der Site. Chromium muss für
Frappe eingerichtet sein, sonst scheitern alle PDFs.
