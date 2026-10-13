# Modellvergleich Kilometerstand-Erkennung

Alle Messungen vom 09. bis 13.10.2026 mit **Ollama auf einem Steam Deck**
(Handheld mit integrierter Grafik, kein Server mit dedizierter GPU), über die
OpenAI-kompatible Chat-API wie in `fahrtenbuch/ocr.py`. Die Dauern gelten nur für
dieses Gerät. Zusammenfassung und Empfehlung stehen in `docs/fahrtenbuch.md`.

## Testaufbau

- **Fotos:** 30 Tacho-Fotos von Wikimedia Commons (Lizenzen in
  `modell-vergleich/LIZENZEN.md`, nicht im Repo): **27 Hauptfotos**, 2 Negativfälle
  (zeigen keinen Gesamtstand: Tageszähler „TRIP" bzw. Temperatur) und 1 Foto mit
  unsicherem Sollwert (unscharfer Mercedes W124, wird nicht mitgezählt).
  Überwiegend US-Tachos, kein SLK R170.
- **Sollwerte** hat Claude selbst vom Bild abgelesen (nur wenige stehen in der
  Bildbeschreibung). Lesefehler sind möglich. Bei zwei Zählern mitten im Umlauf
  (89999/90000 und 99999/100000) gelten beide Werte.
- **Je Foto 3 Anfragen.** Ein Foto zählt als „3/3 richtig", wenn alle drei
  Antworten stimmen. „Mehrheit" heißt: Ein Wert, den mindestens zwei Antworten
  nennen, ist richtig (so arbeitet die App). Das sind effektiv nur 27 Datenpunkte,
  Unterschiede von wenigen Punkten sind Rauschen.
- **Standard:** Denken aus (`reasoning_effort: none`), Bildkante 1024 px, Limit 120 s.
  Auswertung wie in der App: alle Ziffern der Antwort, `NONE` oder keine Ziffer
  zählt als „kein Wert".
- **Prompts:** *früher* = „Wie viele Kilometer zeigt der Zähler? Nur Ziffern."
  *NONE 1* = früher plus „antworte NONE, wenn kein Gesamtstand zu sehen ist".
  *NONE 2* (jetzt in der App) = Gesamtzähler genau beschrieben, Tageszähler,
  Temperatur, Uhr, Reichweite ausgeschlossen, `NONE` erlaubt.

## 1. Modelle und Prompts (Denken aus, 1024 px)

| Modell | Prompt | Treffer je Anfrage | Mehrheit richtig | Foto 3/3 richtig | Negativfälle ohne Zahl | Dauer je Foto |
|---|---|---|---|---|---|---|
| `ornith-1.5:9b` | früher | 87,7 % | 25 / 27 | 20 / 27 | 0 / 6 | 15 s |
|  | NONE 1 | 80,2 % | 22 / 27 | 20 / 27 | 3 / 6 | 15 s |
|  | NONE 2 | 86,4 % | 23 / 27 | 21 / 27 | 3 / 6 | 15 s |
| `gemma4:12b` | früher | 79,0 % | 21 / 27 | 21 / 27 | 1 / 6 | 8 s |
|  | NONE 1 | 75,3 % | 20 / 27 | 20 / 27 | 3 / 6 | 8 s |
|  | NONE 2 | 76,5 % | 21 / 27 | 20 / 27 | 3 / 6 | 9 s |
| `qwen3.5:9b` | früher | 72,8 % | 21 / 27 | 16 / 27 | 0 / 6 | 2 s (2) |
|  | NONE 1 | 70,4 % | 19 / 27 | 15 / 27 | 3 / 6 | 15 s |
|  | NONE 2 | 80,2 % | 23 / 27 | 17 / 27 | 3 / 6 | 15 s |
| `qwen3.5:4b` | früher | 53,1 % | 14 / 27 | 9 / 27 | 0 / 6 | 10 s |
|  | NONE 1 | 65,4 % | 17 / 27 | 13 / 27 | 3 / 6 | 11 s |
|  | NONE 2 | 77,8 % | 22 / 27 | 17 / 27 | 3 / 6 | 11 s |
| `gemma4:e4b` | früher | 58,0 % | 16 / 27 | 11 / 27 | 0 / 6 | 5 s |
| `gemma4:e2b` | früher | 43,2 % | 11 / 27 | 11 / 27 | 0 / 6 | 3 s |
| `glm-ocr:bf16` | früher | 0,0 % | 0 / 27 | 0 / 27 | 6 / 6 | Limit (3) |


(2) Im allerersten Lauf waren bei `qwen3.5:9b` viele erste Anfragen sofort fertig (Median 1,2 s statt
14 s). Vermutlich lag das an Ollamas Zwischenspeicher oder an der Auslastung des Geräts; in allen
späteren Läufen (NONE 1/2, 640/448 px) lag dasselbe Modell wieder bei etwa 15 s. Der Wert ist nicht
mit den anderen vergleichbar. (3) Jede Anfrage lief ins Limit von 120 s.

*Negativfälle ohne Zahl:* 6 Anfragen (2 Fotos × 3), richtig ist „kein Wert". Das
Temperatur-Foto liefert mit NONE 1/2 bei allen vier Hauptmodellen in allen 3
Anfragen „kein Wert", das Tageszähler-Foto bei keinem (sie lesen den Tageszähler
als Gesamtstand). *Dauer je Foto:* erste Anfrage plus eine weitere mit demselben
Bild (erste Anfrage etwa 14 s, weitere etwa 0,8 s; vermutlich hält Ollama das
verarbeitete Bild im Zwischenspeicher - nicht geprüft). `gemma4:e4b` und `gemma4:e2b` wurden nur mit dem früheren
Prompt gemessen. `glm-ocr` liest die ganze Anzeige als Text, antwortet auf die Frage
nicht gezielt und läuft meist ins Limit - unbrauchbar für diese Aufgabe.

## 2. Denken an oder aus

`ornith-1.5:9b`, die 13 schwierigsten Hauptfotos (die, bei denen `ornith-1.5:9b` oder `qwen3.5:9b` ohne Denken nicht 3/3 richtig lagen), früherer Prompt:

| Einstellung | Anfragen | Treffer | davon unter 45 s | Median je Anfrage | längste Anfrage |
|---|---|---|---|---|---|
| Denken aus (3 Anfragen je Foto) | 39 | 29 (74 %) | 29 | 0,8 s | 14 s |
| Denken an (2 Anfragen je Foto, Limit 300 s) | 26 | 21 (81 %) | 18 (69 %) | 27,5 s | 300 s |


Mit Denken liest das Modell genau die Fälle richtig, bei denen es sonst den
Tageszähler oder eine angehängte Ziffer liefert (z. B. 100000, 333333, 46000).
Es braucht aber im Median etwa 28 s je Anfrage, gelegentlich liefert es
Zahlensalat, und rund ein Drittel der Antworten käme nach dem 45-s-Limit der App.
Mit dem App-Limit schneidet Denken an deshalb schlechter ab als Denken aus.

**`qwen3.5:9b` mit Denken an** (erster Lauf, Standard der API, Limit 45 s, früher Prompt,
nur die ersten 9 Fotos, dann abgebrochen): 9 von 27 Anfragen richtig,
18 ohne Antwort, 0 mit falscher Zahl. Wenn das Modell antwortete, stimmte es also;
es antwortete aber nur bei etwa einem Drittel der Anfragen. Auf dem Foto mit 100000 kam
auch nach **15 Minuten ohne Limit keine Antwort** (endlose Denkschleife); mit
`max_tokens: 200` war die Antwort leer (`finish_reason: length`, das Denken verbrauchte
alle Token); mit `reasoning_effort: none` kam die Antwort nach 1 s.

## 3. Bildgröße (längste Kante, früherer Prompt, Denken aus)

| Modell | 1024 px (App) | 640 px | 448 px |
|---|---|---|---|
| `ornith-1.5:9b` | 87,7 % | 66,7 % | 56,8 % |
| `qwen3.5:9b` | 72,8 % | 63,0 % | 64,2 % |


Kleinere Bilder verschlechtern die Erkennung deutlich, die Antwortzeit ändert sich bei Denken aus kaum.

## 4. Automatischer Zuschnitt auf den Zählerstand (früherer Prompt, Denken aus)

Zweistufig: Das Modell liefert den Rahmen des Gesamtzählers, der Ausschnitt (mit Rand) wird gelesen.

| Modell | ganzes Foto | Zuschnitt, Rand 15 % | Zuschnitt, Rand 35 % | ohne brauchbaren Rahmen (15 % / 35 %) |
|---|---|---|---|---|
| `ornith-1.5:9b` | 87,7 % | 81,5 % | 79,0 % | 3 / 5 |
| `qwen3.5:9b` | 72,8 % | 74,1 % | 72,8 % | 2 / 0 |


Der Zuschnitt behebt einige Verwechslungen mit dem Tageszähler, schneidet aber an anderer Stelle Ziffern ab oder liefert Unsinn. Unterm Strich kein Gewinn, dazu kommt eine zusätzliche Anfrage.

## 5. Ergebnis je Foto (aktueller Prompt NONE 2, Denken aus, 1024 px)

Richtige Antworten von 3, schwierigste Fotos zuerst.

| Foto | Soll | `ornith-1.5:9b` | `gemma4:12b` | `qwen3.5:9b` | `qwen3.5:4b` |
|---|---|---|---|---|---|
| `100000_k04.jpg` | 100000 | 1/3 | 3/3 | 0/3 | 0/3 |
| `499_k31.jpg` | 499 | 3/3 | 0/3 | 2/3 | 0/3 |
| `87846_k10.jpg` | 87846 | 1/3 | 0/3 | 2/3 | 2/3 |
| `k25_extra.jpg` | 99999 oder 100000 | 1/3 | 3/3 | 1/3 | 0/3 |
| `46000_k05.jpg` | 46000 | 0/3 | 3/3 | 0/3 | 3/3 |
| `k09_extra.jpg` | 87846 | 2/3 | 0/3 | 1/3 | 3/3 |
| `659446_k30.jpg` | 659446 | 3/3 | 0/3 | 3/3 | 1/3 |
| `333333_k11.jpg` | 333333 | 3/3 | 3/3 | 2/3 | 1/3 |
| `91308_k14.jpg` | 91308 | 3/3 | 0/3 | 3/3 | 3/3 |
| `k19_extra.jpg` | 89999 oder 90000 | 3/3 | 0/3 | 3/3 | 3/3 |
| `99173_k21.jpg` | 99173 | 3/3 | 3/3 | 2/3 | 2/3 |
| `105616_k26.jpg` | 105616 | 3/3 | 3/3 | 3/3 | 2/3 |
| `11000_k28.jpg` | 11000 | 3/3 | 3/3 | 2/3 | 3/3 |
| `150000_k24.jpg` | 150000 | 2/3 | 3/3 | 3/3 | 3/3 |
| `32534_k17.jpg` | 32534 | 3/3 | 3/3 | 3/3 | 2/3 |
| `500000_k12.jpg` | 500000 | 3/3 | 3/3 | 2/3 | 3/3 |
| `55055_k01.jpg` | 55055 | 3/3 | 2/3 | 3/3 | 3/3 |
| `k08_extra.jpg` | 173386 | 3/3 | 3/3 | 3/3 | 2/3 |
| `10000_k15.jpg` | 10000 | 3/3 | 3/3 | 3/3 | 3/3 |
| `103543_k20.jpg` | 103543 | 3/3 | 3/3 | 3/3 | 3/3 |
| `181033_k32.jpg` | 181033 | 3/3 | 3/3 | 3/3 | 3/3 |
| `222222_k07.jpg` | 222222 | 3/3 | 3/3 | 3/3 | 3/3 |
| `31412_k16.jpg` | 31412 | 3/3 | 3/3 | 3/3 | 3/3 |
| `31412_k18.jpg` | 31412 | 3/3 | 3/3 | 3/3 | 3/3 |
| `34763_k06.jpg` | 34763 | 3/3 | 3/3 | 3/3 | 3/3 |
| `92929_k29.jpg` | 92929 | 3/3 | 3/3 | 3/3 | 3/3 |
| `9840_k02.jpg` | 9840 | 3/3 | 3/3 | 3/3 | 3/3 |


Typische Fehler: eine angehängte Ziffer (3333333 statt 333333, 1733862 statt 173386),
der Tageszähler statt des Gesamtstands (2082 statt 100000), abgeschnittene oder
vertauschte Ziffern bei Spiegelung, Unschärfe und mechanischen Zählwerken.


## 6. `glm-ocr` (zweiter Versuch)

Der erste Lauf (Tabelle 1) war unfair: `glm-ocr` ist ein reines Texterkennungs-Modell. Es ignoriert die Frage,
schreibt den ganzen Text des Bildes ab und hört nicht von selbst auf (`finish_reason: length`, es wiederholt sich). Daher lief fast
jede Anfrage ins Limit. Zweiter Versuch: Prompt `Text Recognition:`, Ausgabe auf 40 Token begrenzt, ausgewertet wird die **erste Zeile**
(Tausenderpunkte und Leerzeichen entfernt), 27 Hauptfotos × 3 Anfragen, Limit 90 s:

| Auswertung | Treffer | ohne Wert | Negativfälle ohne Zahl | Dauer je Foto |
|---|---|---|---|---|
| erste Zeile der Texterkennung | 19,8 % (16 / 81) | 37 | 2 / 6 | etwa 11 s |

Die Ausgabe ist von Anfrage zu Anfrage unterschiedlich. In einer zusätzlichen Stichprobe (27 Hauptfotos × 2 Anfragen,
60 Token, ohne Auswertung nach Zeile) stand der richtige Wert in **38 von 54 Ausgaben irgendwo im Text**, aber nur in
**2 von 54 als erste Zeile**. Das Modell findet die Zahlen, weiß aber nicht, welche der Gesamtkilometerstand ist (es nennt auch
Tacho-Skalen, Tageszähler, Reichweite). Ohne zusätzliche Auswahlstufe (Heuristik oder ein zweites Modell) taugt es für diese
Aufgabe nicht; als eigenständiges Modell nicht empfohlen.


## 7. Schnittstelle und Kontextfenster (`qwen3-vl:4b-instruct`, aktueller Prompt, Denken aus)

Ollama lädt das Modell standardmäßig mit 128k Kontext (131 072 Token) und belegt dafür 14,5 GB, obwohl die Datei nur
3,3 GB groß ist. Ein Foto braucht nur etwa 1.000 bis 1.500 Token. Über Ollamas eigene Schnittstelle (`/api/chat`) lässt sich
das Kontextfenster setzen:

| Schnittstelle | Kontextfenster | Speicher im Server | Dauer je Foto | Treffer (27 Fotos × 3) | Negativfälle ohne Zahl |
|---|---|---|---|---|---|
| OpenAI-kompatibel | Server-Standard (128k) | 14,5 GB | 34 s | 88,9 % (72 / 81) | 0 / 6 |
| nativ, Bild in einer Nachricht | 8 192 | 3,7 GB | 14 s | 82,7 % (67 / 81) | 3 / 6 |
| nativ, Bild in einer Nachricht | 4 096 | 3,3 GB | 14 s | 81,5 % (66 / 81) | 3 / 6 |
| **nativ, Text und Bild als zwei Nachrichten (so in der App)** | **8 192** | **3,7 GB** | **14 s** | **87,7 % (71 / 81)** | 1 / 6 |

**Ursache des Unterschieds zwischen nativ und OpenAI:** Die Reihenfolge von Text und Bild. Die nativen Aufrufe mit dem Bild in
derselben Nachricht stellen das Bild vor den Text; die OpenAI-Schicht macht aus „Text, dann Bild" zwei aufeinanderfolgende
Nachrichten (so die Vermutung, am Verhalten, nicht im Ollama-Code geprüft). Bei Zählern mit Dezimalstelle hängt das Modell dann die
Zehntelziffer an (87846 → 878469, 173386 → 1733862). Belege: (1) Die OpenAI-Schnittstelle mit dem Bild **vor** dem Text liefert
dieselben Fehler wie nativ; (2) `temperature: 0` ändert nichts (nur dass die Fehler bei jeder Wiederholung gleich sind); (3) der
Server-Standard-Kontext (128k) nativ liefert dieselben Fehler wie 8 192, das Kontextfenster ist also nicht die Ursache; (4) nativ mit
zwei Nachrichten (erst der Text, dann das Bild) kommt auf das OpenAI-Ergebnis zurück. Gegenprobe (4) wurde auf allen Fotos gemessen,
(1) bis (3) auf den fünf Fotos mit Abweichung.

**Normales `qwen3-vl:4b` (ohne `-instruct`):** `think: false` wirkt auch über die native Schnittstelle nicht. Das Modell schreibt
trotzdem einen Denktext (1060 Zeichen, 329 Token, 33 s inklusive Laden); mit `num_predict: 32` bleibt die Antwort leer. `qwen3-vl:4b-instruct`
antwortet dagegen ohne Denktext (6 Token, 0,4 s). Für die App kommt nur `-instruct` in Frage.

## 8. Echte Handyfotos (2 Fotos) und Bildgröße

Zwei eigene Handyfotos des Betreibers (VW-Tacho bei Nacht, Gesamtstand **163244 km**, daneben Tageszähler 95,6 und Uhr 22:18; Sollwert vom Bild
gelesen). Foto 1 ist scharf, Foto 2 unscharf und schräg. Je Foto 3 Anfragen, Denken aus, aktueller Prompt. Die Ziffern sind klein; auf
die längste Kante von 1024 px verkleinert (so arbeitet die App heute) sind sie nur noch wenige Pixel hoch.

| Bildkante | Modell / Schnittstelle | Foto 1 (scharf) | Foto 2 (unscharf) | Dauer je Foto |
|---|---|---|---|---|
| 1024 px | `ornith-1.5:9b`, OpenAI | 163244 ×3 ✓ | 16324, 163214, 163214 ✗ | 16 s |
| 1024 px | `qwen3.5:9b`, OpenAI | 1632441632444, 163244, 163244 (✓ per Mehrheit) | 16324, 163294, 165324 ✗ | 16 s |
| 1024 px | `qwen3-vl:4b-instruct`, OpenAI | 16324 ×3 ✗ | 0, 15321, 63214 ✗ | 34 s |
| 1024 px | `qwen3-vl:4b-instruct`, nativ 2 Nachrichten, 8 192 | 16324 ×3 ✗ | 95641, 153214, 0 ✗ | 14 s |
| 1536 px | `ornith-1.5:9b`, OpenAI | 163244 ×3 ✓ | 163241, 163244, 163244 (✓ per Mehrheit) | 35 s |
| 1536 px | `qwen3-vl:4b-instruct`, nativ, 16 384 | 16324 ×3 ✗ | 16321 ×3 ✗ | 23 s |
| 2048 px | `ornith-1.5:9b`, OpenAI | 1632444, 163244, 163244 (✓ per Mehrheit) | 163214, 163214, 163244 ✗ | 90 s |
| 2048 px | `qwen3-vl:4b-instruct`, nativ, 16 384 | 163244 ×3 ✓ | 16321, 16324, 16321 ✗ | 51 s |

Zwei Fotos sind keine Statistik. Es zeigt aber, wo die Probleme liegen: Bei echten, dunklen Handyfotos sind die Ziffern klein, und
die Verkleinerung auf 1024 px kostet Genauigkeit. `qwen3-vl:4b-instruct` lässt bei 1024 und 1536 px die letzte Ziffer weg
(16324), bei 2048 px liest es das scharfe Foto richtig. `ornith-1.5:9b` liest das scharfe Foto immer richtig und das unscharfe
bei 1536 px per Mehrheit. 2048 px kostet bei `ornith-1.5:9b` 90 s je Foto, 1536 px etwa 35 s.

## Grenzen

- 27 Fotos mit je 3 Anfragen: Unterschiede von wenigen Punkten sind nicht gesichert.
- Sollwerte vom Bild abgelesen, Lesefehler möglich.
- Überwiegend US-Tachos mit englischer Beschriftung, kein SLK R170. Echte Handyfotos wurden nur
  an zwei Fotos geprüft (Abschnitt 8); dort schnitten die Modelle schlechter ab als auf den Commons-Fotos.
- Alles auf einem Steam Deck gemessen; Dauern lassen sich nicht auf andere Hardware
  übertragen.
- Rohdaten, Skripte und Fotos liegen im Bench unter `modell-vergleich/`
  (`ergebnis_*.json`, `vergleich.py`, `zuschnitt.py`), nicht im Repo.
