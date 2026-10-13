import base64
import io
import re
import time
from collections import Counter

import frappe
import requests
from frappe import _
from PIL import Image

# Prompt-Vergleich (docs/fahrtenbuch.md): Der fruehere Prompt verlangte immer
# Ziffern - bei Fotos ohne Gesamtstand (nur Temperatur oder Tageszaehler) erfanden
# die Modelle eine Zahl. Diese Fassung beschreibt den Gesamtzaehler genauer,
# grenzt Tageszaehler (TRIP) und andere Werte ab und erlaubt "NONE". Gegenueber dem
# frueheren Prompt: ornith-1.5:9b 86 % statt 88 % (im Rauschen), qwen3.5:9b 80 %
# statt 73 %, qwen3.5:4b 78 % statt 53 %; das Temperatur-Foto erkennen alle.
# Ein Tageszaehler wird weiter als Gesamtstand gelesen.
PROMPT = (
	"This is a photo of a car instrument cluster. Find the TOTAL odometer: the long "
	"counter showing all kilometers (or miles) the car has driven. It is NOT the trip "
	"counter (labelled TRIP, A or B, usually with a decimal digit), NOT a temperature, "
	"clock, range or fuel value. Ignore any small decimal/tenths digit shown in a "
	"different color. If the total odometer is not clearly visible, respond with the "
	"single word NONE. Otherwise respond with only the digits, nothing else."
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


API_TYP_OLLAMA = "Ollama (nativ)"

# Die Antwort besteht nur aus wenigen Ziffern oder "NONE". Die Begrenzung kappt eine
# Denkschleife nach wenigen Sekunden, falls ein Modell das Denken trotz think=false
# nicht abschaltet (qwen3-vl:4b tat das im Test, 54-87 s je Anfrage): leere Antwort =
# "kein Wert" statt minutenlangem Warten.
NUM_PREDICT = 32


def _ollama_basis(api_url: str) -> str:
	"""Server-Adresse fuer Ollamas eigene Schnittstelle. Ein angehaengtes /v1
	(die Adresse der OpenAI-kompatiblen Schnittstelle) wird entfernt."""
	basis = api_url.rstrip("/")
	return basis[: -len("/v1")] if basis.endswith("/v1") else basis


def _zahl_aus(text: str) -> int | None:
	"""Kilometerstand aus der Modellantwort: nur Ziffern, NONE (kein Gesamtstand
	sichtbar) und Zahlensalat ergeben keinen Wert."""
	if text.strip().upper().startswith("NONE"):
		return None  # "NONE (Tageszaehler 185.5)": die Ziffern dahinter gehoeren nicht dazu
	digits = re.sub(r"\D", "", text)
	if not digits or len(digits) > MAX_STELLEN:
		return None
	return int(digits)


def _auth_headers(settings) -> dict:
	api_key = settings.get_password("api_key", raise_exception=False)
	return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def list_models(
	api_url: str | None = None, api_key: str | None = None, api_type: str | None = None
) -> list[str]:
	"""Fragt die API nach den dort tatsaechlich verfuegbaren Modellen: bei der
	OpenAI-kompatiblen Schnittstelle GET .../models, bei Ollama (nativ)
	GET /api/tags.

	api_url/api_key/api_type optional: fuer den "Modelle abrufen"-Button in
	Fahrtenbuch Einstellungen, damit ein gerade eingetipptes, noch nicht
	gespeichertes Feld direkt getestet werden kann. Ohne Angabe wird der
	bereits gespeicherte Stand aus den Einstellungen verwendet."""
	settings = frappe.get_cached_doc("Fahrtenbuch Einstellungen")
	api_url = api_url or settings.api_url
	if not api_url:
		frappe.throw(_("Bitte zuerst eine API-URL eintragen."))
	ollama = (api_type or settings.api_type) == API_TYP_OLLAMA

	headers = {}
	key = api_key or settings.get_password("api_key", raise_exception=False)
	if key:
		headers["Authorization"] = f"Bearer {key}"

	url = f"{_ollama_basis(api_url)}/api/tags" if ollama else f"{api_url.rstrip('/')}/models"
	try:
		response = requests.get(url, headers=headers, timeout=15)
		response.raise_for_status()
		data = response.json()
	except requests.RequestException:
		frappe.throw(_("Die API war nicht erreichbar."))

	if ollama:
		return sorted(m["name"] for m in data.get("models", []) if m.get("name"))
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
	if settings.api_type == API_TYP_OLLAMA:
		basis = _ollama_basis(settings.api_url)

		def frage():
			return _frage_ollama(
				basis, headers, settings.model, image_b64, settings.context_length, settings.keep_alive
			)

	else:
		api_url = settings.api_url.rstrip("/")

		def frage():
			return _frage_openai(api_url, headers, settings.model, image_b64)

	ende = time.monotonic() + GESAMT_ZEIT

	stimmen = []
	for _ in range(ANFRAGEN):
		try:
			stimmen.append(frage())
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


def _frage_openai(api_url: str, headers: dict, model: str, image_b64: str) -> int | None:
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

	return _zahl_aus(response.json()["choices"][0]["message"]["content"] or "")


def _frage_ollama(
	basis: str,
	headers: dict,
	model: str,
	image_b64: str,
	num_ctx: int | None = None,
	keep_alive: str | None = None,
) -> int | None:
	"""Eine Anfrage ueber Ollamas eigene Schnittstelle (/api/chat). Dort gehoeren
	Kontextfenster (options.num_ctx), Denken aus (think) und Verweildauer im
	Speicher (keep_alive) zur Schnittstelle. None, wenn die Antwort keine
	brauchbare Zahl enthaelt; Netzwerk- und Formatfehler werden gereicht."""
	optionen = {"num_predict": NUM_PREDICT}
	if num_ctx:
		optionen["num_ctx"] = int(num_ctx)
	body = {
		"model": model,
		"stream": False,
		"think": False,
		"options": optionen,
		# Text und Bild als zwei aufeinanderfolgende Nachrichten, in dieser Reihenfolge: So
		# macht es Ollamas OpenAI-kompatible Schicht aus "Text, dann Bild". Liegt das Bild
		# in derselben Nachricht, steht es vor dem Text, und das Modell haengt bei Zaehlern
		# mit Dezimalstelle die Zehntelziffer an (qwen3-vl:4b-instruct: 87846 -> 878469,
		# 173386 -> 1733862; mit zwei Nachrichten 88 % statt 83 % wie ueber die OpenAI-API).
		"messages": [
			{"role": "user", "content": PROMPT},
			{"role": "user", "content": "", "images": [image_b64]},
		],
	}
	if keep_alive:
		# "30m"/"1h" als Text, "-1" (dauerhaft) und "0" als Zahl, wie Ollama es erwartet
		body["keep_alive"] = int(keep_alive) if re.fullmatch(r"-?\d+", str(keep_alive).strip()) else keep_alive

	def senden(mit_think: bool):
		return requests.post(
			f"{basis}/api/chat",
			headers=headers,
			json=body if mit_think else {k: v for k, v in body.items() if k != "think"},
			timeout=45,
		)

	# Modelle ohne Denkfunktion koennen think ablehnen (HTTP 400): einmal ohne den
	# Parameter weiter und die Adresse fuer spaeter vormerken.
	response = senden(basis not in _OHNE_DENKEN_PARAMETER)
	if response.status_code == 400 and basis not in _OHNE_DENKEN_PARAMETER:
		_OHNE_DENKEN_PARAMETER.add(basis)
		response = senden(False)
	response.raise_for_status()

	return _zahl_aus((response.json().get("message") or {}).get("content") or "")
