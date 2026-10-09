# Kundeneinsatz (Site Visit)

Ein Techniker legt pro Einsatz einen **Kundeneinsatz** an: Zeitraum,
Aktivitätsart, Tätigkeit, Fotos, optional die Unterschrift des Kunden
direkt auf dem eigenen Gerät und zusätzlich benötigtes Material.

## Auftrag

Jeder Einsatz gehört zu einem **Auftrag** – Pflicht schon beim Speichern.
Kunde und (falls leer) Projekt kommen aus dem Auftrag; ein Auftrag eines
anderen Kunden oder ein abgeschlossener/stornierter wird abgelehnt.

- **Projekt gewählt:** Gibt es genau einen offenen Auftrag dazu, wird er
  übernommen; bei mehreren erscheint ein Auswahldialog (Auftrag,
  Kommissionsnummer, Datum).
- **Noch kein Auftrag:** Knopf **„Neuer Auftrag"** – auch im noch nicht
  gespeicherten Einsatz. Im Dialog Kunde, **Kommissionsnummer** und
  Aktivitätsart. Die Kommissionsnummer steht im Auftragsfeld `po_no` (je nach
  Site z. B. „Customer Reference"; ist es dort Pflicht, ist es auch im Dialog
  Pflicht). Der Auftrag entsteht als **Entwurf** – Buchen bleibt Sache des
  Vertriebs – mit einer Position: dem Dienstleistungsartikel der
  Aktivitätsart, Menge 1, **Preis 0**. ERPNext verlangt mindestens eine
  Position; die Zeit selbst wird über das Zeitblatt abgerechnet, so wird
  nichts doppelt berechnet.

## Buchen

Vor dem Buchen geprüft: Aktivitätsart und Endzeit gesetzt, alle Pausen
beendet, der Auftrag ist offen und gehört zum Kunden.

Beim Buchen entsteht automatisch ein **Zeitblatt** (Aktivitätsart des
Einsatzes, Kunde, Projekt, Auftrag, Stundensatz der Aktivitätsart), gebucht
und verknüpft – mit **einer Zeile je Arbeitsabschnitt** zwischen den Pausen. Abgerechnet wird es über den
[Zeitimport der Ausgangsrechnung](abrechnung.md). Das Zeitblatt wird ohne
Rollenprüfung angelegt und gebucht – maßgeblich ist die Berechtigung auf den
Einsatz, denn die Rolle „Employee" darf in ERPNext keine Zeitblätter buchen.

Überschneidet sich der Zeitraum mit einer anderen Zeitbuchung desselben
Mitarbeiters, bricht das Buchen mit einer klaren Meldung ab.

## Zusatzartikel und Auftrag

**Zusätzliche Artikel** sind vor Ort benötigtes Material (Adapter, Kabel …).
Der Preis ist schreibgeschützt und wird beim Speichern aus der Preisliste
des Kunden bzw. des Auftrags ermittelt. Beim Buchen kommen die Artikel in
den verknüpften Auftrag (auch in einen Entwurf) – Details unter
[Abrechnung – Zusatzartikel im Auftrag](abrechnung.md#zusatzartikel-im-auftrag).

In *Zeit Projekt Einstellungen → Ausgeschlossene Artikelgruppen* lassen sich
Gruppen (inkl. Untergruppen, meist die Dienstleistungen) als Zusatzartikel
sperren: Die Artikelsuche zeigt sie nicht, und Speichern lehnt sie ab.

## Stornieren und Berichtigen

Stornieren (Projects Manager/System Manager) storniert das Zeitblatt und
entfernt die beim Buchen übernommenen Zusatzartikel wieder aus dem Auftrag.
Nicht möglich, wenn das Zeitblatt schon abgerechnet ist. Ein berichtigter
Einsatz übernimmt die Artikel beim erneuten Buchen genau einmal.

## Timer und Pausen

„Timer starten"/„Timer stoppen" speichern sofort (wie im Fahrtenbuch);
Aktivitätsart und Endzeit werden deshalb erst beim Buchen geprüft. Starten
geht erst mit Auftrag, sonst ließe sich der Einsatz nicht speichern.

**„Timer pausieren"** fragt einen Grund ab (*Pause*, *Notfall bei anderem
Kunden*, *Sonstiges*) und eine optionale Notiz und legt eine Zeile unter
*Pausen* an; **„Timer fortsetzen"** beendet sie. Die Anzeige zeigt die
Netto-Arbeitszeit, in einer Pause „Pausiert seit …". „Timer stoppen" in
einer Pause beendet sie mit dem Einsatz. Pausen lassen sich auch von Hand
eintragen; sie müssen im Einsatzzeitraum liegen und dürfen sich nicht
überschneiden.

*Arbeitszeit (Std.)* zeigt die Dauer ohne Pausen – so viel kommt ins
Zeitblatt. Weil das Zeitblatt nur die Arbeitsabschnitte enthält, kollidiert
ein Notfall-Einsatz beim anderen Kunden während der Pause nicht mit diesem
Einsatz.

## Einsatzbericht (PDF)

Das Druckformat **„Site Visit Report"** (Einsatzbericht) zeigt Kopfdaten,
Arbeitszeit und Pausen, Tätigkeit, Fotogalerie und Unterschriftsblock. Für ein **automatisches** PDF
beim Buchen: [`pdf_on_submit`](https://github.com/alyf-de/erpnext_pdf-on-submit)
installieren. Ist die App bei der Installation von Zeit & Projekt schon
vorhanden, trägt `install.py` den Kundeneinsatz automatisch in deren
Einstellungen ein; sonst dort von Hand ergänzen (Doctype *Site Visit*,
Druckformat *Site Visit Report*).
