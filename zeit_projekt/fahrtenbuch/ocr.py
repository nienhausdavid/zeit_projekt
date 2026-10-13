import base64
import io
import re
import time
from collections import Counter

import frappe
import requests
from frappe import _
from PIL import Image

PROMPT = (
	"This is a photo of a car odometer (mileage display). What is the total "
	"number of kilometers shown? Ignore any small decimal/tenths digit shown "
	"in a different color. Respond with only the digits, nothing else."
)

# Handy-Kamerafotos kommen leicht mit 4000+ px Kantenlaenge und mehreren MB
# daher - im Test hat das die API einmal mit einer leeren Nullwert-Antwort
# (content: "") und einmal mit komplettem Totalausfall (Timeout) quittiert.
# Erst nach Verkleinerung auf ~1024px kam eine korrekte Antwort. Deshalb hier
# vorsorglich fuer jedes Foto, nicht erst als Reaktion auf einen Fehlschlag.
MAX_IMAGE_DIMENSION = 1024

# Modellvergleich vom 09./10.10.2026 (27 Tacho-Fotos, je 3 Anfragen, Details in
# docs/fahrtenbuch.md): Mit dem Standard-Denken der Modelle kam bei schwierigen
# Fotos oft gar keine Antwort (Denkschleife bis ins Zeitlimit, bei qwen3.5:9b
# einmal nach 15 Minuten noch nicht). Ohne Denken antwortet das Modell in rund
# einer Sekunde. Einzelne Antworten sind dann gelegentlich falsch (angehaengte
# Ziffer, Tageszaehler statt Gesamtstand) - deshalb mehrere Anfragen und nur ein
# Wert, den mindestens zwei Antworten nennen (ornith-1.5:9b: 88 % je Anfrage,
# 93 % der Fotos mit Mehrheitsentscheid).
ANFRAGEN = 3
# Laenger ist kein Kilometerstand, sondern Zahlensalat (im Test kam einmal eine
# 25-stellige Antwort).
MAX_STELLEN = 7
# Der Hintergrund-Job laeuft mit timeout=120 (fahrtenbuch.get_odometer_reading).
GESAMT_ZEIT = 100

# API-URLs, die reasoning_effort ablehnen (z. B. aeltere OpenAI-Modelle): dort
# wird nicht jedes Mal erst die abgelehnte Anfrage geschickt.
_OHNE_DENKEN_PARAMETER = set()


def _downscale_to_jpeg(image_bytes: bytes) -> bytes:
	"""Skaliert bei Bedarf herunter und kodiert dabei immer als JPEG neu -
	nicht nur wenn tatsaechlich verkleinert wird, damit der MIME-Typ im
	data:-URL unten (immer "image/jpeg") garantiert zum Inhalt passt, egal
	welches Format das Original hatte."""
	image = Image.open(io.BytesIO(image_bytes))
	if max(image.size) > MAX_IMAGE_DIMENSION:
		image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION))

	buffer = io.BytesIO()
	image.convert("RGB").save(buffer, format="JPEG", quality=85)
	return buffer.getvalue()


def _auth_headers(settings) -> dict:
	api_key = settings.get_password("api_key", raise_exception=False)
	return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def list_models(api_url: str | None = None, api_key: str | None = None) -> list[str]:
	"""Fragt eine OpenAI-kompatible API nach den dort tatsaechlich
	verfuegbaren Modellen (GET .../models - Teil des OpenAI-Standards, den
	auch Ollama & Co. darueber mit anbieten).

	api_url/api_key optional: fuer den "Modelle abrufen"-Button in
	Fahrtenbuch Einstellungen, damit ein gerade eingetipptes, noch nicht
	gespeichertes Feld direkt getestet werden kann. Ohne Angabe wird der
	bereits gespeicherte Stand aus den Einstellungen verwendet."""
	settings = frappe.get_cached_doc("Fahrtenbuch Einstellungen")
	api_url = api_url or settings.api_url
	if not api_url:
		frappe.throw(_("Bitte zuerst eine API-URL eintragen."))

	headers = {}
	key = api_key or settings.get_password("api_key", raise_exception=False)
	if key:
		headers["Authorization"] = f"Bearer {key}"

	try:
		response = requests.get(f"{api_url.rstrip('/')}/models", headers=headers, timeout=15)
		response.raise_for_status()
		data = response.json()
	except requests.RequestException:
		frappe.throw(_("Die API war nicht erreichbar."))

	return sorted(m["id"] for m in data.get("data", []) if m.get("id"))


def is_configured() -> bool:
	settings = frappe.get_cached_doc("Fahrtenbuch Einstellungen")
	return bool(settings.api_url and settings.model)


def read_odometer(file_doc) -> int | None:
	"""Nur der erkannte Wert (siehe read_odometer_mit_vertrauen)."""
	return read_odometer_mit_vertrauen(file_doc)[0]


def read_odometer_mit_vertrauen(file_doc) -> tuple[int | None, bool]:
	"""Liest den Kilometerstand ueber eine OpenAI-kompatible Chat-Completions-
	API (Ollama, LM Studio, echtes OpenAI, ...) - konfiguriert in
	"Fahrtenbuch Einstellungen", keine Standard-URL/kein Standard-Modell
	hinterlegt.

	None, wenn nichts konfiguriert ist, die API nicht erreichbar ist oder
	nichts Eindeutiges erkannt wurde - der Techniker traegt dann manuell ein,
	das Feld bleibt dafuer immer normal editierbar. Bewusst in einem eigenen
	Modul: die einzige Stelle, die sich aendern muesste, falls das
	API-Format spaeter wechseln sollte.

	Rueckgabe: (Wert, sicher). "Sicher" heisst: schon die ersten beiden
	Antworten stimmen ueberein. Brauchte es die dritte Anfrage, gab es eine
	abweichende Antwort - der Wert ist dann nur die Mehrheit und der Techniker
	soll ihn gegen das Foto pruefen."""
	settings = frappe.get_cached_doc("Fahrtenbuch Einstellungen")
	if not settings.api_url or not settings.model:
		return None, False

	with open(file_doc.get_full_path(), "rb") as f:
		image_bytes = f.read()
	try:
		image_b64 = base64.b64encode(_downscale_to_jpeg(image_bytes)).decode()
	except (OSError, Image.DecompressionBombError):
		# Kein (lesbares) Bild - wie "nichts erkannt" behandeln
		return None, False

	headers = {"Content-Type": "application/json", **_auth_headers(settings)}
	api_url = settings.api_url.rstrip("/")
	ende = time.monotonic() + GESAMT_ZEIT

	stimmen = []
	for _ in range(ANFRAGEN):
		try:
			stimmen.append(_frage(api_url, headers, settings.model, image_b64))
		except (requests.RequestException, KeyError, IndexError, ValueError):
			# API nicht erreichbar oder Antwort nicht lesbar: weitere Anfragen
			# wuerden nur dieselbe Wartezeit kosten.
			frappe.logger("fahrtenbuch").error("Kilometerstand-Erkennung fehlgeschlagen", exc_info=True)
			return None, False

		haeufigste = Counter(s for s in stimmen if s is not None).most_common(1)
		if haeufigste and haeufigste[0][1] >= 2:
			# zwei gleiche Antworten genuegen, die dritte spart man sich
			return haeufigste[0][0], len(stimmen) == 2
		if time.monotonic() > ende:
			break

	# Keine zwei gleichen Antworten: lieber kein Wert, als einen unsicheren
	# einzutragen - der Techniker tippt ihn dann selbst ein.
	return None, False


def _frage(api_url: str, headers: dict, model: str, image_b64: str) -> int | None:
	"""Eine Anfrage an die Vision-API. None, wenn die Antwort keine brauchbare
	Zahl enthaelt; Netzwerk- und Formatfehler werden an den Aufrufer gereicht."""
	body = {
		"model": model,
		"messages": [
			{
				"role": "user",
				"content": [
					{"type": "text", "text": PROMPT},
					{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
				],
			}
		],
		"stream": False,
	}

	def senden(mit_denken_aus: bool):
		return requests.post(
			f"{api_url}/chat/completions",
			headers=headers,
			json={**body, "reasoning_effort": "none"} if mit_denken_aus else body,
			# Grosszuegig: ein kaltes, noch nicht geladenes Modell brauchte im
			# Test 10-15s zusaetzlich zur eigentlichen Anfrage, ein echtes
			# (statt synthetisches) Testfoto weitere ca. 20s statt <2s.
			timeout=45,
		)

	# Ohne Denken, siehe oben. Lehnt die API den Parameter ab (HTTP 400), geht es
	# einmal ohne ihn weiter und die URL wird fuer spaeter vorgemerkt.
	response = senden(api_url not in _OHNE_DENKEN_PARAMETER)
	if response.status_code == 400 and api_url not in _OHNE_DENKEN_PARAMETER:
		_OHNE_DENKEN_PARAMETER.add(api_url)
		response = senden(False)
	response.raise_for_status()

	text = response.json()["choices"][0]["message"]["content"] or ""
	digits = re.sub(r"\D", "", text)
	if not digits or len(digits) > MAX_STELLEN:
		return None
	return int(digits)
