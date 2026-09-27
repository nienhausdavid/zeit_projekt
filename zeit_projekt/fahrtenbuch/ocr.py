import base64
import io
import re

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


def read_odometer(file_url: str) -> int | None:
	"""Liest den Kilometerstand ueber eine OpenAI-kompatible Chat-Completions-
	API (Ollama, LM Studio, echtes OpenAI, ...) - konfiguriert in
	"Fahrtenbuch Einstellungen", keine Standard-URL/kein Standard-Modell
	hinterlegt.

	None, wenn nichts konfiguriert ist, die API nicht erreichbar ist oder
	nichts Eindeutiges erkannt wurde - der Techniker traegt dann manuell ein,
	das Feld bleibt dafuer immer normal editierbar. Bewusst in einem eigenen
	Modul: die einzige Stelle, die sich aendern muesste, falls das
	API-Format spaeter wechseln sollte."""
	settings = frappe.get_cached_doc("Fahrtenbuch Einstellungen")
	if not settings.api_url or not settings.model:
		return None

	file_doc = frappe.get_doc("File", {"file_url": file_url})
	with open(file_doc.get_full_path(), "rb") as f:
		image_bytes = f.read()
	image_b64 = base64.b64encode(_downscale_to_jpeg(image_bytes)).decode()

	headers = {"Content-Type": "application/json", **_auth_headers(settings)}

	try:
		response = requests.post(
			f"{settings.api_url.rstrip('/')}/chat/completions",
			headers=headers,
			json={
				"model": settings.model,
				"messages": [
					{
						"role": "user",
						"content": [
							{"type": "text", "text": PROMPT},
							{
								"type": "image_url",
								"image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
							},
						],
					}
				],
				"stream": False,
			},
			# Grosszuegig: ein kaltes, noch nicht geladenes Modell brauchte im
			# Test 10-15s zusaetzlich zur eigentlichen Anfrage, ein echtes
			# (statt synthetisches) Testfoto weitere ca. 20s statt <2s.
			timeout=45,
		)
		response.raise_for_status()
		text = response.json()["choices"][0]["message"]["content"]
	except (requests.RequestException, KeyError, IndexError):
		frappe.logger("fahrtenbuch").error("Kilometerstand-Erkennung fehlgeschlagen", exc_info=True)
		return None

	digits = re.sub(r"\D", "", text)
	return int(digits) if digits else None
