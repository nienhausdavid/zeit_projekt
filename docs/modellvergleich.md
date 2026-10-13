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
Bild (Ollama behält das verarbeitete Bild im Zwischenspeicher: erste Anfrage etwa
14 s, weitere etwa 0,8 s). `gemma4:e4b` und `gemma4:e2b` wurden nur mit dem früheren
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

## Grenzen

- 27 Fotos mit je 3 Anfragen: Unterschiede von wenigen Punkten sind nicht gesichert.
- Sollwerte vom Bild abgelesen, Lesefehler möglich.
- Überwiegend US-Tachos mit englischer Beschriftung, kein SLK R170, keine echten
  Handyfotos aus dem Außendienst. Dort kann es anders aussehen.
- Alles auf einem Steam Deck gemessen; Dauern lassen sich nicht auf andere Hardware
  übertragen.
- Rohdaten, Skripte und Fotos liegen im Bench unter `modell-vergleich/`
  (`ergebnis_*.json`, `vergleich.py`, `zuschnitt.py`), nicht im Repo.
