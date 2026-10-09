# Fahrtenbuch

Ein Techniker legt pro Fahrt eine **Fahrt** an: Zeitraum, Start/Ziel,
Fotos vom Tacho am Anfang und am Ende. Der Kilometerstand wird optional per
Bilderkennung vorgeschlagen und lässt sich jederzeit von Hand eintragen oder
korrigieren.

Kein Finanzamt-taugliches Fahrtenbuch (keine Geschäftlich/Privat-Trennung,
keine lückenlose Erfassung) – ein praktisches Log für Kundenbesuche.

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

*Fahrtenbuch Einstellungen → „Fahrzeit abrechnen in Schritten von
(Minuten)"*: z. B. 15 rundet die abrechenbaren Stunden auf volle
Viertelstunden auf (50 Minuten → 1,0 Std.). Die tatsächliche Dauer bleibt im
Zeitblatt erhalten; ERPNext zeigt dann den Hinweis, dass die abrechenbaren
Stunden über den tatsächlichen liegen. 0 = minutengenau.

## Timer

„Timer starten"/„Timer stoppen" setzen Beginn bzw. Ende und **speichern
sofort** – wie ERPNexts eigener Zeitblatt-Timer. Sonst ginge ein laufender
Timer bei einem Neuladen verloren. Deshalb sind Endzeit, Kilometerstände und
Aktivitätsart nicht auf Feldebene Pflicht, sondern werden erst beim Buchen
geprüft.

Im Projekt-Formular legt der Knopf **„Fahrt mit Timer starten"** (und das
„+" bei *Fahrten* unter *Verknüpfungen*) eine Fahrt mit Projekt/Kunde an,
startet den Timer und öffnet die Kamera für das Start-Foto. Beides einzeln
abschaltbar in *Fahrtenbuch Einstellungen* (Standard: an).

## Kilometerstand-Erkennung

Liest den Kilometerstand aus dem Tacho-Foto über eine beliebige
**OpenAI-kompatible API** (Chat-Completions mit Bild) – z. B.
[Ollama](https://ollama.com/), LM Studio oder OpenAI selbst.

Einrichtung in *Fahrtenbuch Einstellungen*:

- **API-URL**: Basis-URL ohne `/chat/completions`, z. B.
  `http://<ip-des-servers>:11434/v1` oder `https://api.openai.com/v1`
- **Modell**: z. B. `qwen3.5:9b` – der Knopf **„Verfügbare Modelle
  abrufen"** fragt die API nach ihren Modellen (nur System Manager)
- **API-Schlüssel**: nur falls die API einen verlangt

Ohne Eintrag bleibt die Erkennung aus. Die Erkennung läuft als
**Hintergrund-Job** (Queue `short`, bis zu 45 s pro Foto) – das Formular
bleibt bedienbar, das Ergebnis erscheint per Realtime-Meldung. Es wird nur
übernommen, wenn noch dasselbe Foto im Formular steht und der Wert nicht
schon von Hand eingetragen ist. Dafür muss ein Worker für die Queue `short`
laufen (bei Frappe Manager und Frappe Cloud Standard).

Fotos werden vor dem Versand auf max. 1024 px verkleinert; verarbeitet
werden nur Dateien, die der Nutzer selbst lesen darf.

## Einstellungen im Überblick

| Feld | Zweck |
|---|---|
| Aktivitätsart Fahrzeit | Vorbelegung für neue Fahrten; die Aktivitätsart braucht einen Dienstleistungsartikel |
| Artikel Kilometer | Vorbelegung für neue Fahrten |
| Fahrzeit abrechnen in Schritten von (Minuten) | Taktung, 0 = minutengenau |
| API-URL, Modell, API-Schlüssel | Kilometerstand-Erkennung |
| Timer automatisch starten / Kamera automatisch öffnen | Verhalten beim Anlegen aus dem Projekt |

Die Einstellungen darf nur der System Manager lesen (API-Schlüssel);
Techniker erhalten die Vorbelegungen über eine eigene, eingeschränkte
Server-Methode.
