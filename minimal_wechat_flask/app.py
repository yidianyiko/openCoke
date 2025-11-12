from flask import Flask, request, jsonify
import os
import logging
from xml.etree import ElementTree as ET

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

SUPPORTED_TYPES = {
    "60001": "text",
    "60014": "quote",
}

def parse_quote(text):
    try:
        root = ET.fromstring(text)
        for tag in ("content", "quotemsgdesc", "desc"):
            node = root.find(tag)
            if node is not None and node.text is not None:
                return node.text
    except Exception:
        pass
    return text

@app.route("/message", methods=["POST"]) 
def message():
    if not request.is_json:
        return jsonify({"status": "error", "message": "Request must be JSON"}), 400
    data = request.get_json()
    wcid = data.get("wcId")
    msg_type = data.get("messageType")
    payload = data.get("data") or {}
    if not wcid:
        return jsonify({"status": "error", "message": "No wcId provided"}), 400
    if msg_type not in SUPPORTED_TYPES:
        return jsonify({"status": "success", "message": "not supported message type"}), 200
    kind = SUPPORTED_TYPES[msg_type]
    content = payload.get("content")
    if kind == "quote" and isinstance(content, str):
        content = parse_quote(content)
    logger.info({"wcId": wcid, "type": kind, "from": payload.get("fromUser"), "to": payload.get("toUser"), "content": content})
    return jsonify({"status": "success", "type": kind, "message": "received"}), 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8090"))
    app.run(host="0.0.0.0", port=port, debug=True)

