import sys
sys.path.append(".")

from flask import Flask, request, jsonify
from util.log_util import get_logger
import os
import json
from datetime import datetime
import os

logger = get_logger(__name__)
app = Flask(__name__)

LOG_PATH = os.path.join(os.path.dirname(__file__), "mock_langbot.log")
PORT = int(os.getenv("PORT", "8080"))


def append_log(entry: dict):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Failed to write mock log: {e}")


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "ok"}), 200


@app.route("/api/v1/platform/bots/<bot_uuid>/send_message", methods=["POST"])
def send_message(bot_uuid):
    # Optional API key check
    api_key = request.headers.get("X-API-Key", "")
    body = request.get_json(force=True, silent=True) or {}
    entry = {
        "ts": datetime.utcnow().isoformat(),
        "bot_uuid": bot_uuid,
        "api_key": "****" if api_key else "",
        "body": body,
    }
    append_log(entry)
    return jsonify({"code": 0, "msg": "ok", "data": {"sent": True}}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
