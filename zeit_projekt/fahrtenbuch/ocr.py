import base64
import io
import re
import time
import uuid
from collections import Counter

import frappe
import requests
from frappe import _
from frappe.utils import cint
from PIL import Image, ImageOps

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
# Standardwert; in den Einstellungen (Bildgroesse) aenderbar. Bei zwei echten, dunklen
# Handyfotos las ornith-1.5:9b mit 1536 px besser als mit 1024 px, brauchte aber etwa
# doppelt so lange (docs/modellvergleich.md, Abschnitt 8).
MAX_IMAGE_DIMENSION = 1024
# Marker fuer "nicht verkleinern" (Einstellung "Originalauflösung verwenden")
ORIGINAL_GROESSE = -1

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
# Wartezeit je Anfrage (Standard; einstellbar: "Zeitlimit je Anfrage"). Ollama sendet im
# Nicht-Streaming-Betrieb erst nach der fertigen Antwort, das Limit gilt also faktisch fuer
# die ganze Anfrage. Gesamtzeit aller Anfragen und Limit des Hintergrund-Jobs (siehe
# fahrtenbuch.get_odometer_reading) richten sich danach: Standard 45 -> 100 s bzw. 120 s.
ANFRAGE_ZEIT = 45
ZUSCHLAG_GESAMT = 55
ZUSCHLAG_JOB = 20


def zeitlimit(settings=None) -> int:
	"""Wartezeit je Anfrage in Sekunden (Einstellung, sonst Standard)."""
	settings = settings or frappe.get_cached_doc("Zeit Projekt Einstellungen")
	return cint(settings.get("request_timeout")) or ANFRAGE_ZEIT


def gesamtzeit(settings=None) -> int:
	"""Obergrenze fuer alle Anfragen eines Fotos zusammen."""
	return zeitlimit(settings) + ZUSCHLAG_GESAMT


def job_timeout() -> int:
	"""Limit des Hintergrund-Jobs: etwas ueber der Gesamtzeit."""
	return gesamtzeit() + ZUSCHLAG_JOB

# API-URLs, die reasoning_effort ablehnen (z. B. aeltere OpenAI-Modelle): dort
# wird nicht jedes Mal erst die abgelehnte Anfrage geschickt.
_OHNE_DENKEN_PARAMETER = set()


def _downscale_to_jpeg(image_bytes: bytes, max_px: int | None = None) -> bytes:
	"""Skaliert bei Bedarf herunter und kodiert dabei immer als JPEG neu -
	nicht nur wenn tatsaechlich verkleinert wird, damit der MIME-Typ im
	data:-URL unten (immer "image/jpeg") garantiert zum Inhalt passt, egal
	welches Format das Original hatte."""
	image = Image.open(io.BytesIO(image_bytes))
	# Handyfotos im Hochformat sind oft Querformat-Pixel plus EXIF-Drehvermerk (Orientation).
	# Ohne Drehen bekaeme das Modell ein seitliches Bild.
	image = ImageOps.exif_transpose(image)
	max_px = max_px or MAX_IMAGE_DIMENSION
	if max_px != ORIGINAL_GROESSE and max(image.size) > max_px:
		image.thumbnail((max_px, max_px))

	buffer = io.BytesIO()
	image.convert("RGB").save(buffer, format="JPEG", quality=85)
	return buffer.getvalue()


API_TYP_OLLAMA = "Ollama (nativ)"
API_TYP_OPENCODE = "OpenCode"
ZUGANG_ZEN = "Zen (Pay per use)"
# OpenCode Go (Abo) liegt unter .../inference/go (der Zen-Zugang mit Guthaben unter .../inference).
# Chat: <Basis>/openai/v1/chat/completions, Modellliste: <Basis>/v1/models (NICHT neben dem Chat-Pfad).
OPENCODE_URL = "https://opencode.ai/inference/go"
# Zen: Pay per use mit Guthaben (die kostenlosen Zen-Modelle erlaubt der Anbieter nur innerhalb von OpenCode)
OPENCODE_ZEN_URL = "https://opencode.ai/inference"
# OpenCode lehnt Anfragen ohne x-opencode-session ab (HTTP 400 "cannot be routed efficiently") und
# erwartet bei Drittclients einen eigenen User-Agent.
OPENCODE_USER_AGENT = "zeit-projekt/0.1 (ERPNext Kilometerstand-Erkennung)"

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
	# Manche Modelle liefern ihr Nachdenken im Text (<think>...</think>): nur die Antwort danach zaehlt;
	# ist der Denkblock nicht abgeschlossen (Antwort abgeschnitten), gibt es keine Antwort.
	text = re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.I)
	if re.search(r"<think>", text, flags=re.I):
		return None
	if text.strip().upper().startswith("NONE"):
		return None  # "NONE (Tageszaehler 185.5)": die Ziffern dahinter gehoeren nicht dazu
	digits = re.sub(r"\D", "", text)
	if not digits or len(digits) > MAX_STELLEN:
		return None
	return int(digits)


def _opencode_basis(zugang: str | None = None) -> str:
	"""Basis-URL von OpenCode: Go (Abo) oder Zen (Pay per use). Ein im Feld "API-URL" noch stehender
	Wert (z. B. von einer frueheren Schnittstelle) bleibt unbeachtet: das Feld ist bei OpenCode
	ausgeblendet."""
	return (OPENCODE_ZEN_URL if zugang == ZUGANG_ZEN else OPENCODE_URL).rstrip("/")


# Eingabe-Modalitaeten der OpenCode-Modelle: die Modellliste der API nennt nur Namen. Das oeffentliche
# Verzeichnis models.dev (daraus bezieht auch OpenCode selbst seine Modelleigenschaften) kennt je
# Modell, ob Bilder moeglich sind. Textmodelle verwerfen ein Bild still und raten dann eine Zahl
# (im Test: 44591, 139872 ... statt 185460) - sie gehoeren nicht in die Auswahl.
MODELS_DEV_URL = "https://models.dev/api.json"
_BILD_CACHE = "zeit_projekt_opencode_bildfaehig"
_BILD_ANBIETER = {"Go (Abo)": "opencode-go", ZUGANG_ZEN: "opencode"}


def _bildfaehige_modelle(zugang: str | None) -> dict | None:
	"""{Modell-ID: Bild-Eingabe moeglich} laut models.dev fuer den Zugang; None, wenn das Verzeichnis
	nicht erreichbar ist (dann wird nichts gefiltert). Ergebnis 12 Stunden zwischengespeichert."""
	anbieter = _BILD_ANBIETER.get(zugang or "Go (Abo)", "opencode-go")
	if frappe.cache.get_value(f"{_BILD_CACHE}:{anbieter}"):
		return _mit_luecken_aus_dem_anderen_zugang(anbieter)
	try:
		daten = requests.get(MODELS_DEV_URL, timeout=20).json()
		for name in _BILD_ANBIETER.values():  # beide Zugaenge aus einem Abruf (5 MB) merken
			frappe.cache.set_value(
				f"{_BILD_CACHE}:{name}",
				{
					i: "image" in ((m.get("modalities") or {}).get("input") or [])
					for i, m in daten[name]["models"].items()
				},
				expires_in_sec=12 * 3600,
			)
	except (requests.RequestException, ValueError, KeyError, AttributeError):
		return None
	return _mit_luecken_aus_dem_anderen_zugang(anbieter)


def _mit_luecken_aus_dem_anderen_zugang(anbieter: str) -> dict:
	"""Dasselbe Modell kann Bilder bei Go wie bei Zen gleich (oder gleich nicht): was das Verzeichnis
	fuer den einen Zugang nicht kennt, kommt aus dem anderen (z. B. glm-5.1 steht nur bei Zen)."""
	eigene = frappe.cache.get_value(f"{_BILD_CACHE}:{anbieter}") or {}
	andere = frappe.cache.get_value(f"{_BILD_CACHE}:{'opencode' if anbieter == 'opencode-go' else 'opencode-go'}") or {}
	return {**andere, **eigene}


def _opencode_headers(sitzung: str | None = None) -> dict:
	"""Pflicht-Header von OpenCode; die Sitzung gilt je Foto (alle Anfragen dazu gehoeren zusammen)."""
	return {"x-opencode-session": sitzung or str(uuid.uuid4()), "User-Agent": OPENCODE_USER_AGENT}


def _auth_headers(settings) -> dict:
	api_key = settings.get_password("api_key", raise_exception=False)
	return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def list_models(
	api_url: str | None = None,
	api_key: str | None = None,
	api_type: str | None = None,
	opencode_zugang: str | None = None,
) -> list[str]:
	"""Fragt die API nach den dort tatsaechlich verfuegbaren Modellen: bei der
	OpenAI-kompatiblen Schnittstelle GET .../models, bei Ollama (nativ)
	GET /api/tags.

	api_url/api_key/api_type optional: fuer den "Modelle abrufen"-Button in
	Zeit Projekt Einstellungen, damit ein gerade eingetipptes, noch nicht
	gespeichertes Feld direkt getestet werden kann. Ohne Angabe wird der
	bereits gespeicherte Stand aus den Einstellungen verwendet."""
	settings = frappe.get_cached_doc("Zeit Projekt Einstellungen")
	api_url = api_url or settings.api_url
	if not api_url and (api_type or settings.api_type) != API_TYP_OPENCODE:
		frappe.throw(_("Bitte zuerst eine API-URL eintragen."))
	typ = api_type or settings.api_type
	ollama = typ == API_TYP_OLLAMA
	opencode = typ == API_TYP_OPENCODE

	headers = _opencode_headers() if opencode else {}
	if api_key and set(api_key) == {"*"}:
		api_key = None  # so zeigt Frappe einen gespeicherten Schluessel an: den echten nehmen
	key = api_key or settings.get_password("api_key", raise_exception=False)
	if key:
		headers["Authorization"] = f"Bearer {key}"

	if ollama:
		urls = [f"{_ollama_basis(api_url)}/api/tags"]
	elif opencode:
		urls = [f"{_opencode_basis(opencode_zugang or settings.get('opencode_zugang'))}/v1/models"]
	else:
		urls = [f"{api_url.rstrip('/')}/models"]
		# Manche Anbieter (z. B. OpenCode Go) legen die Modellliste NICHT neben den Chat-Pfad:
		# Chat unter .../go/openai/v1, Liste unter .../go/v1/models. Bei 404 deshalb auch ohne
		# das Protokoll-Segment versuchen.
		if "/openai/v1" in api_url:
			urls.append(f"{api_url.rstrip('/').replace('/openai/v1', '/v1')}/models")

	letzter_fehler = None
	data = None
	for url in urls:
		try:
			response = requests.get(url, headers=headers, timeout=15)
			response.raise_for_status()
			data = response.json()
			break
		except requests.HTTPError as e:
			letzter_fehler = e
			if e.response is not None and e.response.status_code == 404:
				continue  # naechsten Pfad versuchen
			break
		except requests.RequestException as e:
			letzter_fehler = e
			break
		except ValueError as e:  # keine JSON-Antwort
			letzter_fehler = e
			break

	if data is None:
		_melde_modellfehler(letzter_fehler, urls[0])

	if ollama:
		return sorted(m["name"] for m in data.get("models", []) if m.get("name"))
	ids = [m["id"] for m in data.get("data", []) if m.get("id")]
	if opencode:
		# "Contributor"-Modelle trainieren mit den gesendeten Daten (und brauchen eine Freigabe in der
		# OpenCode Console): Fotos sollen dort nicht versehentlich landen.
		zen = (opencode_zugang or settings.get("opencode_zugang")) == ZUGANG_ZEN
		# Die kostenlosen Zen-Modelle ("-free") darf der Anbieter nur innerhalb von OpenCode nutzen (HTTP 403
		# FreeTierError); die im Go-Abo enthaltenen Free-Modelle laufen dagegen ueber den Go-Zugang.
		ids = [i for i in ids if "contributor" not in i and not (zen and i.endswith("-free"))]
		# Modelle ohne Bild-Eingabe ausblenden; unbekannte (nicht im Verzeichnis) bleiben sichtbar
		bildfaehig = _bildfaehige_modelle(opencode_zugang or settings.get("opencode_zugang"))
		if bildfaehig:
			ids = [i for i in ids if bildfaehig.get(i, True)]
	return sorted(ids)


def _melde_modellfehler(fehler, url):
	"""Sagt, woran der Abruf der Modellliste gescheitert ist (statt immer "nicht erreichbar")."""
	if isinstance(fehler, requests.HTTPError) and fehler.response is not None:
		status = fehler.response.status_code
		if status in (401, 403):
			frappe.throw(
				_("Die API hat den Zugang abgelehnt (HTTP {0}). Bitte API-Schlüssel und Abo prüfen.").format(status)
			)
		if status == 404:
			frappe.throw(
				_("Der Pfad {0} wurde nicht gefunden (HTTP 404). Bitte die API-URL prüfen.").format(url)
			)
		frappe.throw(_("Die API meldet einen Fehler (HTTP {0}).").format(status))
	if isinstance(fehler, requests.Timeout):
		frappe.throw(_("Zeitüberschreitung: Die API hat nicht innerhalb von 15 Sekunden geantwortet."))
	if isinstance(fehler, ValueError):
		frappe.throw(_("Die Antwort der API war keine Modellliste. Bitte die API-URL prüfen."))
	frappe.throw(_("Die API war nicht erreichbar."))


def is_configured() -> bool:
	settings = frappe.get_cached_doc("Zeit Projekt Einstellungen")
	if settings.api_type == API_TYP_OPENCODE:
		return bool(settings.model)  # die URL ist optional (Standard: Go)
	return bool(settings.api_url and settings.model)


def read_odometer(file_doc) -> int | None:
	"""Nur der erkannte Wert (siehe read_odometer_mit_vertrauen)."""
	return read_odometer_mit_vertrauen(file_doc)[0]


def _fehlerursache(e) -> str:
	"""Ordnet einen Fehler der Anfrage einer Ursache zu (siehe read_odometer_detail)."""
	if isinstance(e, requests.Timeout):
		return "timeout"
	if isinstance(e, requests.HTTPError) and e.response is not None:
		status, text = e.response.status_code, (e.response.text or "").lower()
		if status == 403 and "free tier" in text:
			return "free_nur_in_opencode"
		if status in (401, 403):
			return "zugang_abgelehnt"
		if status in (402, 429):  # Guthaben/Nutzungslimit erschoepft
			return "limit_erreicht"
		if status == 400 and "trains" in text:
			return "modell_freigabe_noetig"  # Contributor-Modell: trainiert mit den Daten, braucht Freigabe
		if status == 400 and "image" in text and "support" in text:
			return "modell_ohne_bild"
		if status == 400 and "protocol" in text:
			return "modell_nicht_unterstuetzt"
		return "nicht_erreichbar"
	if isinstance(e, requests.RequestException):
		return "nicht_erreichbar"
	return "antwort_unlesbar"


def _ergebnis(wert=None, sicher=False, fehler=None) -> dict:
	return {"wert": wert, "sicher": sicher, "fehler": fehler}


def read_odometer_mit_vertrauen(file_doc) -> tuple[int | None, bool]:
	"""(Wert, sicher) - siehe read_odometer_detail."""
	ergebnis = read_odometer_detail(file_doc)
	return ergebnis["wert"], ergebnis["sicher"]


def read_odometer_detail(file_doc) -> dict:
	"""Liest den Kilometerstand ueber eine OpenAI-kompatible Chat-Completions-
	API (Ollama, LM Studio, echtes OpenAI, ...) - konfiguriert in
	"Zeit Projekt Einstellungen", keine Standard-URL/kein Standard-Modell
	hinterlegt.

	None, wenn nichts konfiguriert ist, die API nicht erreichbar ist oder
	nichts Eindeutiges erkannt wurde - der Techniker traegt dann manuell ein,
	das Feld bleibt dafuer immer normal editierbar. Bewusst in einem eigenen
	Modul: die einzige Stelle, die sich aendern muesste, falls das
	API-Format spaeter wechseln sollte.

	Rueckgabe: {"wert", "sicher", "fehler"}. "fehler" ist None oder der Grund, warum gar keine
	Antwort kam ("timeout", "nicht_erreichbar", "antwort_unlesbar", "bild_unlesbar") - nicht zu
	verwechseln mit "nichts erkannt" (fehler None, wert None). "Sicher" heisst: schon die ersten beiden
	Antworten stimmen ueberein. Brauchte es die dritte Anfrage, gab es eine
	abweichende Antwort - der Wert ist dann nur die Mehrheit und der Techniker
	soll ihn gegen das Foto pruefen."""
	settings = frappe.get_cached_doc("Zeit Projekt Einstellungen")
	if not is_configured():
		return _ergebnis()

	with open(file_doc.get_full_path(), "rb") as f:
		image_bytes = f.read()
	try:
		image_b64 = base64.b64encode(_downscale_to_jpeg(
				image_bytes, ORIGINAL_GROESSE if settings.get("image_original") else settings.max_image_px
			)).decode()
	except (OSError, Image.DecompressionBombError):
		return _ergebnis(fehler="bild_unlesbar")

	headers = {"Content-Type": "application/json", **_auth_headers(settings)}
	zeit = zeitlimit(settings)
	if settings.api_type == API_TYP_OLLAMA:
		basis = _ollama_basis(settings.api_url)

		def frage():
			return _frage_ollama(
				basis, headers, settings.model, image_b64, settings.context_length, settings.keep_alive, zeit
			)

	elif settings.api_type == API_TYP_OPENCODE:
		# Pflicht-Header von OpenCode; das Protokoll (Chat, Anthropic, Responses, Gemini) waehlt
		# _frage_opencode je Modell selbst.
		basis = _opencode_basis(settings.get("opencode_zugang"))
		headers = {**headers, **_opencode_headers()}

		def frage():
			return _frage_opencode(basis, headers, settings.model, image_b64, zeit)

	else:
		api_url = settings.api_url.rstrip("/")

		def frage():
			return _frage_openai(api_url, headers, settings.model, image_b64, zeit)

	ende = time.monotonic() + gesamtzeit(settings)

	stimmen = []
	for _ in range(ANFRAGEN):
		try:
			stimmen.append(frage())
		except (requests.RequestException, KeyError, IndexError, ValueError) as e:
			# API nicht erreichbar, zu langsam oder Antwort nicht lesbar: weitere Anfragen
			# wuerden nur dieselbe Wartezeit kosten.
			frappe.logger("fahrtenbuch").error("Kilometerstand-Erkennung fehlgeschlagen", exc_info=True)
			return _ergebnis(fehler=_fehlerursache(e))

		haeufigste = Counter(s for s in stimmen if s is not None).most_common(1)
		if haeufigste and haeufigste[0][1] >= 2:
			# zwei gleiche Antworten genuegen, die dritte spart man sich
			return _ergebnis(haeufigste[0][0], len(stimmen) == 2)
		if time.monotonic() > ende:
			break

	# Keine zwei gleichen Antworten: lieber kein Wert, als einen unsicheren
	# einzutragen - der Techniker tippt ihn dann selbst ein.
	return _ergebnis()


# --- OpenCode Go: je nach Modell ein anderes Protokoll ------------------------------------
# Chat Completions (offene Modelle), Anthropic Messages (Claude, Qwen, MiniMax), OpenAI Responses
# (GPT, Grok) und Gemini. Welches ein Modell spricht, steht nur in der Dokumentation und aendert
# sich mit dem Katalog; die App probiert deshalb der Reihe nach und merkt sich das Protokoll je
# Modell. Ein Modell, das ein Protokoll nicht kann, antwortet sofort mit HTTP 400 "Model does not
# support this protocol".
OPENCODE_PROTOKOLLE = ("chat", "anthropic", "responses", "google")
_PROTOKOLL_CACHE = "zeit_projekt_opencode_protokoll"
# Antwort-Token fuer die Protokolle ausser Chat: grosszuegig, damit Modelle mit Denkphase noch
# eine Antwort schaffen (die Antwort ist nur eine Zahl)
MAX_TOKEN_OPENCODE = 256


def _frage_opencode(basis: str, headers: dict, model: str, image_b64: str, timeout: int) -> int | None:
	"""Eine Anfrage an OpenCode: bekanntes Protokoll des Modells zuerst, sonst der Reihe nach."""
	bekannt = frappe.cache.hget(_PROTOKOLL_CACHE, model)
	bekannt = bekannt.decode() if isinstance(bekannt, bytes) else bekannt
	reihenfolge = ([bekannt] if bekannt in OPENCODE_PROTOKOLLE else []) + [
		p for p in OPENCODE_PROTOKOLLE if p != bekannt
	]
	letzter_fehler = None
	for protokoll in reihenfolge:
		try:
			wert = _OPENCODE_ANFRAGEN[protokoll](basis, headers, model, image_b64, timeout)
		except requests.HTTPError as e:
			text = (e.response.text if e.response is not None else "").lower()
			if e.response is not None and e.response.status_code == 400 and "protocol" in text:
				letzter_fehler = e
				continue  # dieses Modell spricht ein anderes Protokoll
			raise
		frappe.cache.hset(_PROTOKOLL_CACHE, model, protokoll)
		return wert
	raise letzter_fehler


def _opencode_post(url, headers, body, timeout):
	response = requests.post(url, headers=headers, json=body, timeout=timeout)
	response.raise_for_status()
	return response.json()


def _opencode_chat(basis, headers, model, image_b64, timeout):
	return _frage_openai(f"{basis}/openai/v1", headers, model, image_b64, timeout)


def _opencode_responses(basis, headers, model, image_b64, timeout):
	antwort = _opencode_post(
		f"{basis}/openai/v1/responses",
		headers,
		{
			"model": model,
			"max_output_tokens": MAX_TOKEN_OPENCODE,
			"input": [
				{
					"role": "user",
					"content": [
						{"type": "input_text", "text": PROMPT},
						{"type": "input_image", "image_url": f"data:image/jpeg;base64,{image_b64}"},
					],
				}
			],
		},
		timeout,
	)
	text = antwort.get("output_text") or "".join(
		teil.get("text", "")
		for eintrag in antwort["output"]
		if eintrag.get("type") == "message"
		for teil in eintrag.get("content", [])
		if teil.get("type") == "output_text"
	)
	return _zahl_aus(text)


def _opencode_anthropic(basis, headers, model, image_b64, timeout):
	antwort = _opencode_post(
		f"{basis}/anthropic/v1/messages",
		{**headers, "anthropic-version": "2023-06-01"},
		{
			"model": model,
			"max_tokens": MAX_TOKEN_OPENCODE,
			"messages": [
				{
					"role": "user",
					"content": [
						{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
						{"type": "text", "text": PROMPT},
					],
				}
			],
		},
		timeout,
	)
	return _zahl_aus("".join(t.get("text", "") for t in antwort["content"] if t.get("type") == "text"))


def _opencode_google(basis, headers, model, image_b64, timeout):
	antwort = _opencode_post(
		f"{basis}/google/v1beta/models/{model}:generateContent",
		headers,
		{
			"contents": [
				{
					"role": "user",
					"parts": [{"text": PROMPT}, {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}}],
				}
			],
			"generationConfig": {"maxOutputTokens": MAX_TOKEN_OPENCODE},
		},
		timeout,
	)
	return _zahl_aus("".join(t.get("text", "") for t in antwort["candidates"][0]["content"]["parts"]))


_OPENCODE_ANFRAGEN = {
	"chat": _opencode_chat,
	"anthropic": _opencode_anthropic,
	"responses": _opencode_responses,
	"google": _opencode_google,
}


def _frage_openai(
	api_url: str, headers: dict, model: str, image_b64: str, timeout: int = ANFRAGE_ZEIT
) -> int | None:
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
			timeout=timeout,
		)

	# Ohne Denken, siehe oben. Lehnt die API den Parameter ab (HTTP 400), geht es
	# einmal ohne ihn weiter und die URL wird fuer spaeter vorgemerkt.
	response = senden(api_url not in _OHNE_DENKEN_PARAMETER)
	if response.status_code == 400 and api_url not in _OHNE_DENKEN_PARAMETER:
		# Nur bei einer Parameter-Ablehnung wiederholen und die URL vormerken: leere Antwort oder ein
		# Hinweis auf den Parameter. Nicht, wenn das Modell Bilder, das Protokoll oder eine Freigabe
		# nicht hat (sonst gaelte die Vormerkung fuer ein spaeter gewaehltes, funktionierendes Modell mit).
		text = (response.text or "").lower()
		if not text.strip() or any(w in text for w in ("reasoning", "parameter", "unknown", "unrecognized")):
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
	timeout: int = ANFRAGE_ZEIT,
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
			timeout=timeout,
		)

	# Modelle ohne Denkfunktion koennen think ablehnen (HTTP 400): einmal ohne den
	# Parameter weiter und die Adresse fuer spaeter vormerken.
	response = senden(basis not in _OHNE_DENKEN_PARAMETER)
	if response.status_code == 400 and basis not in _OHNE_DENKEN_PARAMETER:
		_OHNE_DENKEN_PARAMETER.add(basis)
		response = senden(False)
	response.raise_for_status()

	return _zahl_aus((response.json().get("message") or {}).get("content") or "")
