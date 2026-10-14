# Fahrtenbuch

Ein Techniker legt pro Fahrt eine **Fahrt** an: Zeitraum, Start/Ziel,
Fotos vom Tacho am Anfang und am Ende. Der Kilometerstand wird optional per
Bilderkennung vorgeschlagen und lässt sich jederzeit von Hand eintragen oder
korrigieren.

Kein Finanzamt-taugliches Fahrtenbuch (keine Geschäftlich/Privat-Trennung,
keine lückenlose Erfassung) – ein praktisches Log für Kundenbesuche.

## Mitarbeiter (freiwillig)

Der **Mitarbeiter** ist bei Fahrt und Kundeneinsatz **kein Pflichtfeld**. Das Formular trägt
automatisch den aktiven Mitarbeiter ein, dessen *Benutzer-ID* der angemeldete Benutzer ist,
falls es einen gibt; sonst bleibt das Feld leer und man kann trotzdem speichern und buchen.
Ohne Mitarbeiter entsteht das Zeitblatt ohne Mitarbeiter, die Firma kommt aus der
Standardfirma, und die Überschneidungsprüfung je Mitarbeiter entfällt.

Wer den Mitarbeiter erzwingen will, schaltet in *Zeit Projekt Einstellungen → Mitarbeiter*
**„Mitarbeiter ist Pflicht"** ein (Standard: aus). Dann lehnt das Speichern von Fahrt und
Kundeneinsatz ohne Mitarbeiter ab.

## Buchen und Abrechnung

Beim Buchen entsteht automatisch ein **Zeitblatt** mit der *Aktivitätsart
Fahrzeit* (Kunde und Projekt aus der Fahrt). Abgerechnet wird es – wie die
Einsatzzeiten – über den [Zeitimport der Ausgangsrechnung](abrechnung.md).
Mit „Kilometer abrechnen" holt derselbe Import zusätzlich die Strecke als
eigene Position (Artikel Kilometer, Menge = km).

Vor dem Buchen geprüft:

- Endzeit gesetzt, Fahrzeit größer 0
- beide Kilometerstände eingetragen, Ende nicht kleiner als Anfang (leere
  Kilometerstände speichert Frappe als 0 – die Prüfung behandelt 0 als „nicht
  eingetragen")
- Kunde gesetzt – sonst aus Projekt, Auftrag oder Kundeneinsatz übernommen
- Aktivitätsart Fahrzeit gesetzt; bei Kilometerabrechnung Artikel und
  Strecke größer 0

Der Auftrag an der Fahrt ist optional und füllt nur Kunde/Projekt vor.

**Stornieren** storniert das Zeitblatt mit – nicht, wenn Fahrzeit oder
Kilometer bereits in einer gebuchten Rechnung stehen.

## Taktung

*Zeit Projekt Einstellungen → „Fahrzeit abrechnen in Schritten von
(Minuten)"*: z. B. 15 rundet die abrechenbaren Stunden auf volle
Viertelstunden auf (50 Minuten → 1,0 Std.). Die tatsächliche Dauer bleibt im
Zeitblatt erhalten; ERPNext zeigt dann den Hinweis, dass die abrechenbaren
Stunden über den tatsächlichen liegen. 0 = minutengenau.

## Timer, Pausen und Fotos

Oben im Fahrt-Formular stehen **große Knöpfe** für den Timer (am Handy bildschirmbreit):

- **Timer starten / Timer stoppen** setzen Beginn bzw. Ende und **speichern sofort** – wie
  ERPNexts eigener Zeitblatt-Timer. Sonst ginge ein laufender Timer bei einem Neuladen
  verloren. Deshalb sind Endzeit, Kilometerstände und Aktivitätsart nicht auf Feldebene
  Pflicht, sondern werden erst beim Buchen geprüft.
- **Timer pausieren / Timer fortsetzen:** fragt einen Grund ab (*Pause*, *Notfall bei
  anderem Kunden*, *Sonstiges*) mit optionaler Notiz und legt eine Zeile unter *Pausen* an.
  Die Anzeige zeigt die Netto-Fahrzeit, in einer Pause „Pausiert seit …". „Timer stoppen" in
  einer Pause beendet sie mit der Fahrt. Pausen lassen sich auch von Hand eintragen; sie
  müssen im Zeitraum der Fahrt liegen und dürfen sich nicht überschneiden.
- **Foto Kilometerstand Start / Ende:** große Knöpfe im Abschnitt *Kilometerstand* (unten
  im Formular), jeder direkt über seinem Foto-Feld. Sie öffnen die Kamera (am Handy der Tipp
  auf den Knopf ist zugleich die Erlaubnis des Browsers dafür). Der Knopf verschwindet, sobald
  das Foto vorhanden ist; „Ende" erscheint ab dem Start des Timers.

*Fahrzeit (Std.)* ist die Zeit **ohne Pausen**. Beim Buchen entsteht ein **Zeitblatt mit einer
Zeile je Arbeitsabschnitt** zwischen den Pausen, wie beim Kundeneinsatz: eine Fahrt mit einer
Pause ergibt zwei Zeilen. So werden Pausen weder abgerechnet, noch kollidieren sie mit einer
Zeitbuchung, die währenddessen erfasst wird. Die *Taktung* gilt nur für Fahrten ohne Pausen
(die Stunden einer Zeile kommen dann direkt aus ihren Zeiten).

Im Projekt-Formular legt der Knopf **„Fahrt mit Timer starten"** (und das „+" bei
*Fahrten* unter *Verknüpfungen*) eine Fahrt mit Projekt/Kunde an, startet den Timer und
öffnet die Kamera für das Start-Foto. Beides einzeln abschaltbar in
*Zeit Projekt Einstellungen* (Standard: an). Manche mobile Browser blockieren das
automatische Öffnen der Kamera, wenn es nicht direkt auf einen Fingertipp folgt; dann den
Foto-Knopf im Formular benutzen. Eine mit „Neu" angelegte Fahrt startet nichts von selbst.

## Kilometerstand-Erkennung

Liest den Kilometerstand aus dem Tacho-Foto über eine beliebige
**OpenAI-kompatible API** (Chat-Completions mit Bild) – z. B.
[Ollama](https://ollama.com/), LM Studio oder OpenAI selbst.

Einrichtung in *Zeit Projekt Einstellungen*:

- **Schnittstelle**: `OpenAI-kompatibel` (Standard; geht mit Ollama, LM Studio,
  OpenAI u. a.) oder `Ollama (nativ)` (Ollamas eigene Schnittstelle `/api/chat`,
  nur für Ollama; erlaubt Kontextfenster und Verweildauer)
- **API-URL**: bei *OpenAI-kompatibel* die Basis-URL ohne `/chat/completions`, z. B.
  `http://<ip-des-servers>:11434/v1` oder `https://api.openai.com/v1`; bei
  *Ollama (nativ)* die Server-Adresse, z. B. `http://<ip-des-servers>:11434` (ein
  angehängtes `/v1` wird ignoriert)
- **Modell**: empfohlen `minicpm-v4.5` (schnell, auch mit großen Bildern; ca. 5,6 GB bei Kontext 8192) oder
  `qwen3-vl:8b-instruct` (gleich genau, aber langsamer); `ornith-1.5:9b` liest dunkle Fotos teils besser
  (siehe *Genauigkeit* unten und `docs/modellvergleich.md`, Abschnitt 10) – der Knopf
  **„Verfügbare Modelle abrufen"** fragt die API nach ihren Modellen (nur
  System Manager)
- **API-Schlüssel**: nur falls die API einen verlangt
- **Bildgröße (längste Kante, Pixel)**: Standard 1024. Größer macht kleine Ziffern
  besser lesbar, ist aber langsamer und braucht mehr Kontext. Bei zwei echten, dunklen
  Handyfotos las `ornith-1.5:9b` mit 1536 px besser als mit 1024 px, brauchte aber
  etwa doppelt so lange (35 statt 16 s je Foto; `docs/modellvergleich.md`,
  Abschnitt 8). Bei *Ollama (nativ)* das Kontextfenster mindestens auf 8192 lassen,
  ab 2048 px eher 16384. Messung mit weiteren Modellen bis Originalgröße:
  `docs/modellvergleich.md`, Abschnitt 9. Das Kontextfenster 8192, 16384 oder 32768 änderte die
  Genauigkeit nicht (Abschnitt 10), nur den Speicher: 8192 reicht bei 1024 px.
- **Originalauflösung verwenden**: schickt das Foto unverkleinert (Handyfotos haben oft
  12 MP und mehr); die Bildgröße ist dann ohne Wirkung. Nicht jedes Modell verkraftet das:
  auf dem Steam Deck lieferten `qwen3-vl:8b-instruct` ab etwa 4,9 MP und `qwen2.5vl:7b`
  ab etwa 3,2 MP leere Antworten, nur `minicpm-v4.5` verarbeitete das Original. Bei
  *Ollama (nativ)* dann das Kontextfenster auf 16384 oder mehr stellen.
- **Kontextfenster (Token)** (nur *Ollama (nativ)*): leer = Standard des Servers.
  Erlaubt sind 2048 bis 262144. Ein Foto braucht nur etwa 1.000 bis 1.500 Token;
  ein sehr großes Fenster belegt viel Speicher (bei `qwen3-vl:4b-instruct` lud der
  Server im Test 14,5 GB für ein 3,3-GB-Modell). Nach einer Änderung lädt Ollama
  das Modell einmal neu.
- **Modell im Speicher halten** (nur *Ollama (nativ)*): wie lange das Modell nach
  der letzten Anfrage geladen bleibt, z. B. `30m`, `2h`, `-1` (dauerhaft) oder `0`
  (sofort entladen). Leer = Standard des Servers. Ein dauerhaft geladenes Modell
  vermeidet das Neuladen beim ersten Foto nach einer Pause.

Ohne Eintrag bleibt die Erkennung aus. Die Erkennung läuft als
**Hintergrund-Job** (Queue `short`, bis zu 45 s je Anfrage, höchstens 100 s
insgesamt) – das Formular
bleibt bedienbar, das Ergebnis erscheint per Realtime-Meldung. Es wird nur
übernommen, wenn noch dasselbe Foto im Formular steht und der Wert nicht
schon von Hand eingetragen ist. Dafür muss ein Worker für die Queue `short`
laufen (bei Frappe Manager und Frappe Cloud Standard).

Fotos werden vor dem Versand auf die eingestellte **Bildgröße** verkleinert (längste
Kante, Standard 1024 px, zulässig 256 bis 4096; mit *Originalauflösung verwenden* gar nicht); verarbeitet werden nur Dateien, die
der Nutzer selbst lesen darf.

### Ablauf je Foto

1. Das Modell wird **ohne Denken** gefragt (`reasoning_effort: none`, bei *Ollama
   (nativ)* `think: false`; dort ist die Antwort zusätzlich auf 32 Token begrenzt,
   damit ein Modell, das das Denken ignoriert, nach Sekunden statt Minuten ohne Wert
   endet). Mit dem
   Standard-Denken blieben viele Anfragen leer: bei schwierigen Fotos lief das
   Modell in eine Denkschleife (bei `qwen3.5:9b` kam nach 15 Minuten keine
   Antwort). Lehnt eine API den Parameter ab (HTTP 400), geht es ohne ihn
   weiter.
2. Bis zu **drei Anfragen**; übernommen wird der Wert, den mindestens zwei
   Antworten nennen (nach zwei gleichen Antworten ist Schluss). Gibt es keine
   Mehrheit, bleibt das Feld leer, und der Techniker trägt von Hand ein.
3. Antworten mit mehr als 7 Ziffern gelten als Zahlensalat und werden verworfen.
   Der Prompt beschreibt den Gesamtzähler genauer (nicht Tageszähler/TRIP, nicht
   Temperatur, Uhr, Reichweite) und erlaubt die Antwort `NONE`, wenn er nicht
   klar zu sehen ist; `NONE` zählt als „kein Wert".
4. Im Formular wird ein erkannter **Endstand unter dem Startstand** nicht
   eingetragen, sondern nur gemeldet.
5. **Unsichere Treffer** werden markiert: Stimmten schon die ersten beiden
   Antworten überein, gilt der Wert als sicher (grüner Hinweis). Brauchte es die
   dritte Anfrage, gab es eine abweichende Antwort - der Wert wird eingetragen,
   aber orange gemeldet, und am Feld steht „nicht sicher, bitte mit dem Foto
   vergleichen", bis der Techniker den Wert ändert.

**Fotohilfe:** An den beiden Foto-Feldern und im Kamera-Dialog (Desktop) steht,
was aufs Bild gehört: der Gesamt-Kilometerzähler (ODO), nicht Tageszähler (TRIP)
oder Temperatur, formatfüllend und ohne Spiegelung.

Grenzen: Zeigt das Foto statt des Gesamtstands nur eine Temperatur oder andere
Werte, antworten die Modelle jetzt mit `NONE` (im Test bei allen getesteten
Modellen). Ein reiner **Tageszähler** wird aber weiter als Gesamtstand gelesen
(im Test bei allen Modellen). Der Techniker sieht den eingetragenen
Wert und kann ihn ändern; eine Prüfung gegen den letzten Stand des
Fahrzeugs gibt es noch nicht.

### Genauigkeit (Modellvergleich 09./10.10.2026)

**Alle Ergebnisse als Tabellen** (Modelle, Prompts, Denken an/aus, Bildgröße, Zuschnitt,
Ergebnis je Foto): [modellvergleich.md](modellvergleich.md). Hier die Kurzfassung.

27 Tacho-Fotos von Wikimedia Commons (überwiegend US-Tachos, kein SLK R170;
Sollwerte vom Bild abgelesen, Lesefehler möglich), je 3 Anfragen, Denken aus,
Bildkante 1024 px. Der Test lief mit **Ollama auf einem Steam Deck** (Handheld
mit integrierter Grafik, kein Server mit dedizierter GPU):

Treffer je Anfrage, mit dem früheren Prompt (nur „Ziffern") und mit dem
aktuellen Prompt (Gesamtzähler genau beschrieben, `NONE` erlaubt); Fotos per
Mehrheit richtig (von 27); Dauer je Foto auf dem Steam Deck:

| Modell | früherer Prompt | aktueller Prompt | Mehrheit richtig (früher → jetzt) | Dauer je Foto |
|---|---|---|---|---|
| `ornith-1.5:9b` | 88 % | 86 % | 25 → 23 | 15 s |
| `gemma4:12b` | 79 % | 77 % | 21 → 21 | 9 s |
| `qwen3.5:9b` | 73 % | 80 % | 21 → 23 | 15 s |
| `qwen3.5:4b` | 53 % | 78 % | 14 → 22 | 11 s |
| `gemma4:e4b` / `gemma4:e2b` (nur früherer Prompt) | 58 % / 43 % | – | 16 / 11 | – |

Die Unterschiede von ein bis drei Punkten bei `ornith-1.5:9b` und `gemma4:12b`
liegen im Rauschen (27 Fotos, je 3 Anfragen). Der aktuelle Prompt hebt die
kleineren Modelle deutlich an, und das Temperatur-Foto (kein Gesamtstand) wird
von allen vier Modellen als „kein Wert" erkannt, mit dem früheren Prompt von
keinem. Das Tageszähler-Foto bleibt ein Fehler bei allen.

**Weitere Modelle** (Abschnitt 10 im Modellvergleich, Treffer je Anfrage auf denselben 27 Fotos bei 8192 / 16384 / 32768 Token):
`qwen3-vl:8b-instruct` 90 / 89 / 91 % (19 s je Foto), `minicpm-v4.5` 85 / 90 / 89 % (11 s), `qwen3-vl:4b-instruct` 86 / 84 / 85 % (12,5 s),
`qwen2.5vl:7b` 82 % (15 s). Das Kontextfenster macht keinen erkennbaren Unterschied, `granite3.2-vision` und `gemma4:e2b` sind nicht brauchbar.
`minicpm-v4.5` und `qwen3-vl:8b-instruct` sind praktisch gleich genau; `minicpm-v4.5` ist fast doppelt so schnell und das einzige getestete
Modell, das auf dem Steam Deck auch das unverkleinerte Handyfoto verarbeitet. Das unscharfe Handyfoto las keines der neuen Modelle.

**Dauer je Foto** (ebenfalls auf dem Steam Deck, `ornith-1.5:9b`): Die erste
Anfrage braucht etwa 14 s, weil das Bild erst verarbeitet wird; jede weitere
Anfrage mit demselben Bild etwa 0,8 s (vermutlich Zwischenspeicher von Ollama). Der
Mehrheitsentscheid kostet daher kaum Zeit, ein Foto dauert insgesamt etwa 15 s
(höchstens gut 18 s). Dazu kommt das Laden des Modells, wenn Ollama es nach einer
Pause neu in den Speicher holen muss (im Test insgesamt 26 s für das erste Foto).
Auf stärkerer Hardware sind kürzere Zeiten zu erwarten, die Genauigkeit sollte
sich nicht ändern; die Werte hier gelten nur für das Steam Deck.

`glm-ocr` liest die ganze Anzeige als Text und passt nicht zur Aufgabe. Kleinere
Bilder (640 px: 67 %, 448 px: 57 % bei `ornith-1.5:9b`) und ein automatischer
Zuschnitt auf den Zähler (79–82 %) waren schlechter als das ganze Foto mit
1024 px. Mit Denken an stieg die Quote bei schwierigen Fotos, die Antworten
dauerten aber im Median 28 s und liefen teils ins Limit. Echte Handyfotos
können anders abschneiden - die Werte sind ein Anhaltspunkt, kein Versprechen.

## Standort bei Beginn und Ende (optional)

Mit der Einstellung **„Standort bei Beginn und Ende erfassen"** (Fahrtenbuch
Einstellungen, **standardmäßig aus**) speichert die Fahrt die Position des Geräts
beim Beginn und beim Ende der Fahrt und zeigt beide Punkte auf einer Karte
(Abschnitt *Karte*, Feld *Standorte*). Es gibt **keine laufende Aufzeichnung** und
keine Strecke, nur diese zwei Zeitpunkte, jeweils mit Zeit und Genauigkeit in Metern.

- Erfasst wird im Browser, wenn Beginn bzw. Ende gerade gesetzt wurden (höchstens 5
  Minuten her): beim Timer im Formular, beim Knopf im Projekt und beim Eintragen von
  Hand. Nachträglich geänderte alte Zeiten bekommen keinen Standort.
- Der Browser fragt beim ersten Mal um Erlaubnis. Ohne HTTPS, ohne Erlaubnis oder ohne
  Empfang bleibt die Karte leer und es erscheint ein Hinweis; die Fahrt lässt sich
  trotzdem normal speichern und buchen.
- Die Karte erscheint nur, wenn Standorte vorliegen. Das Feld ist schreibgeschützt.
- Standortdaten von Beschäftigten sind personenbezogen: Vor dem Einschalten
  Rechtsgrundlage, Information der Beschäftigten und ggf. Beteiligung des Betriebsrats
  klären.

## Einstellungen im Überblick

Alle Einstellungen der App (Fahrtenbuch, Kundeneinsatz, Abrechnung, PDF) liegen an einem
Ort: **Zeit Projekt Einstellungen**. Sie sind aus den Seitenleisten von Fahrtenbuch und
Kundeneinsätzen über den Eintrag *Einstellungen* erreichbar. Die frühere Seite
„Fahrtenbuch Einstellungen" gibt es nicht mehr; ein Patch hat ihre Werte übernommen.

| Feld | Zweck |
|---|---|
| Aktivitätsart Fahrzeit | Vorbelegung für neue Fahrten; die Aktivitätsart braucht einen Dienstleistungsartikel |
| Artikel Kilometer | Vorbelegung für neue Fahrten |
| Fahrzeit abrechnen in Schritten von (Minuten) | Taktung, 0 = minutengenau |
| Schnittstelle, API-URL, Modell, API-Schlüssel, Bildgröße, Originalauflösung, Kontextfenster, Modell im Speicher halten | Kilometerstand-Erkennung |
| Mitarbeiter ist Pflicht | Fahrt und Kundeneinsatz nur mit Mitarbeiter speichern (Standard: aus) |
| Timer automatisch starten / Kamera automatisch öffnen | Verhalten beim Anlegen aus dem Projekt |
| Standort bei Beginn und Ende erfassen | Position bei Beginn und Ende der Fahrt auf einer Karte (Standard: aus) |

Der Abschnitt *Kilometerstand-Erkennung* (mit dem API-Schlüssel) ist nur für den
System Manager sichtbar; der Rest ist für die Rollen sichtbar, die „Zeit Projekt
Einstellungen" lesen dürfen (Buchhaltung, Projekte). Techniker erhalten die
Vorbelegungen über eine eigene, eingeschränkte Server-Methode.
