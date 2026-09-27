# Kundeneinsatz (Site Visit)

Ein Techniker legt pro Einsatz einen **Kundeneinsatz** an: Zeitraum,
Aktivitätsart, Tätigkeit, Fotos, optional die Unterschrift des Kunden
direkt auf dem eigenen Gerät und zusätzlich benötigtes Material.

## Buchen

Vor dem Buchen geprüft: Kunde, Aktivitätsart, Auftrag und Endzeit gesetzt;
der Auftrag ist offen und gehört zum Kunden.

Beim Buchen entsteht automatisch ein **Zeitblatt** (Aktivitätsart des
Einsatzes, Kunde, Projekt, Stundensatz der Aktivitätsart), gebucht und
verknüpft. Abgerechnet wird es über den
[Zeitimport der Ausgangsrechnung](abrechnung.md). Das Zeitblatt wird ohne
Rollenprüfung angelegt und gebucht – maßgeblich ist die Berechtigung auf den
Einsatz, denn die Rolle „Employee" darf in ERPNext keine Zeitblätter buchen.

Überschneidet sich der Zeitraum mit einer anderen Zeitbuchung desselben
Mitarbeiters, bricht das Buchen mit einer klaren Meldung ab.

## Zusatzartikel und Auftrag

**Zusätzliche Artikel** sind vor Ort benötigtes Material (Adapter, Kabel …).
Der Preis ist schreibgeschützt und wird beim Speichern aus der Preisliste
des Kunden bzw. des Auftrags ermittelt. Beim Buchen kommen die Artikel in
den verknüpften Auftrag – Details unter
[Abrechnung – Zusatzartikel im Auftrag](abrechnung.md#zusatzartikel-im-auftrag).

Gibt es noch keinen Auftrag, legt der Knopf **„Neuer Auftrag"** einen an:
Der Einsatz wird vorher gespeichert; Kunde, Firma, Projekt und Artikel liest
der Server aus dem gespeicherten Einsatz, die Preise aus ERPNext, dazu die
im Dialog eingegebene Kundenreferenz. Der Auftrag entsteht als **Entwurf**
(Liefertermin = Einsatzdatum, frühestens heute) – Buchen bleibt Sache des
Vertriebs.

## Stornieren und Berichtigen

Stornieren (Projects Manager/System Manager) storniert das Zeitblatt und
entfernt die beim Buchen übernommenen Zusatzartikel wieder aus dem Auftrag.
Nicht möglich, wenn das Zeitblatt schon abgerechnet ist. Ein berichtigter
Einsatz übernimmt die Artikel beim erneuten Buchen genau einmal; Artikel,
die über „Neuer Auftrag" schon im Auftrag standen, bleiben unberührt.

## Timer

„Timer starten"/„Timer stoppen" speichern sofort (wie im Fahrtenbuch);
Kunde, Aktivitätsart, Auftrag und Endzeit werden deshalb erst beim Buchen
geprüft.

## Einsatzbericht (PDF)

Das Druckformat **„Site Visit Report"** (Einsatzbericht) zeigt Kopfdaten,
Tätigkeit, Fotogalerie und Unterschriftsblock. Für ein **automatisches** PDF
beim Buchen: [`pdf_on_submit`](https://github.com/alyf-de/erpnext_pdf-on-submit)
installieren. Ist die App bei der Installation von Zeit & Projekt schon
vorhanden, trägt `install.py` den Kundeneinsatz automatisch in deren
Einstellungen ein; sonst dort von Hand ergänzen (Doctype *Site Visit*,
Druckformat *Site Visit Report*).
