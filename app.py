import os
import base64
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Config por variables de entorno (las pondremos en Render)
META_TOKEN = os.getenv("META_TOKEN")           # Token de WhatsApp Business
META_VERSION = os.getenv("META_VERSION", "v21.0")
ODOO_URL = os.getenv("ODOO_URL")               # e.g. https://tuodoo.com/jsonrpc
ODOO_DB = os.getenv("ODOO_DB")                 # nombre base de datos
ODOO_UID = int(os.getenv("ODOO_UID", "1"))     # normalmente 1 para admin
ODOO_KEY = os.getenv("ODOO_KEY")               # api key o contraseña
ODOO_MODEL = os.getenv("ODOO_MODEL", "mail.message")
ODOO_RES_ID = int(os.getenv("ODOO_RES_ID", "1")) # ID de registro al que adjuntas (ajústalo)

@app.route("/", methods=["GET"])
def health():
    return "OK"

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    # Verificación de suscripción (Meta usa GET con hub.challenge)
    if request.method == "GET":
        hub_challenge = request.args.get("hub.challenge")
        hub_verify_token = request.args.get("hub.verify_token")
        # Usa un token de verificación que tú definas en Meta y aquí
        VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "mi_token_verificacion")
        if hub_verify_token == VERIFY_TOKEN:
            return hub_challenge, 200
        return "Error de verificación", 403

    # Evento entrante (POST)
    data = request.json
    try:
        entry = data["entry"][0]
        changes = entry["changes"][0]["value"]
        messages = changes.get("messages", [])

        if not messages:
            return jsonify({"status": "no message"}), 200

        msg = messages[0]
        # Soportamos imagen
        if "image" in msg:
            media_id = msg["image"]["id"]
            filename = msg["image"].get("filename", "foto_whatsapp.jpg")

            # Paso 1: obtener URL temporal del media
            meta_media_url = f"https://graph.facebook.com/{META_VERSION}/{media_id}"
            headers = {"Authorization": f"Bearer {META_TOKEN}"}
            meta_resp = requests.get(meta_media_url, headers=headers)
            meta_resp.raise_for_status()
            image_url = meta_resp.json()["url"]

            # Paso 2: descargar binario con token
            img_resp = requests.get(image_url, headers=headers)
            img_resp.raise_for_status()
            img_bytes = img_resp.content

            # Paso 3: codificar en base64 para Odoo (string)
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")

            # Paso 4: crear attachment en Odoo
            payload = {
                "jsonrpc": "2.0",
                "method": "call",
                "params": {
                    "service": "object",
                    "method": "execute_kw",
                    "args": [
                        ODOO_DB,
                        ODOO_UID,
                        ODOO_KEY,
                        "ir.attachment",
                        "create",
                        [{
                            "name": filename,
                            "datas": img_b64,
                            "res_model": ODOO_MODEL,
                            "res_id": ODOO_RES_ID,
                            "mimetype": "image/jpeg"
                        }]
                    ]
                }
            }
            odoo_resp = requests.post(ODOO_URL, json=payload, timeout=30)
            odoo_resp.raise_for_status()

            return jsonify({"status": "attached"}), 200

        return jsonify({"status": "no image"}), 200

    except Exception as e:
        return jsonify({"error": str(e), "data": data}), 500

if __name__ == "__main__":
    # Para local, Render usará gunicorn con Procfile
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
