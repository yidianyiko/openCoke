#!/usr/bin/env python3
import argparse
import itertools
import threading

from flask import Flask, jsonify, request


def create_app(public_base_url: str) -> Flask:
    app = Flask(__name__)
    lock = threading.Lock()
    qr_counter = itertools.count(1)
    bot_counter = itertools.count(1)
    update_counter = itertools.count(1)
    sent_counter = itertools.count(1)
    state: dict[str, object] = {
        "last_qrcode": None,
        "qrcodes": {},
        "bots": {},
    }

    def _reset_state() -> None:
        state["last_qrcode"] = None
        state["qrcodes"] = {}
        state["bots"] = {}

    def _require_bot_token() -> str:
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
          raise PermissionError("missing_bearer_token")
        token = header.split(" ", 1)[1].strip()
        bots = state["bots"]
        if not isinstance(bots, dict) or token not in bots:
            raise PermissionError("unknown_bot_token")
        return token

    def _bot_state(bot_token: str) -> dict:
        bots = state["bots"]
        if not isinstance(bots, dict):
            raise RuntimeError("invalid_state")
        return bots[bot_token]

    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True})

    @app.get("/ilink/bot/get_bot_qrcode")
    def get_bot_qrcode():
        with lock:
            qrcode = f"qr_{next(qr_counter)}"
            bot_token = f"bot_{next(bot_counter)}"
            bot_id = f"ilink_bot_{bot_token}"
            qrcodes = state["qrcodes"]
            bots = state["bots"]
            assert isinstance(qrcodes, dict)
            assert isinstance(bots, dict)
            qrcodes[qrcode] = {
                "status": "wait",
                "bot_token": bot_token,
                "bot_id": bot_id,
            }
            bots[bot_token] = {
                "bot_id": bot_id,
                "updates": [],
                "sent": [],
            }
            state["last_qrcode"] = qrcode

        return jsonify(
            {
                "qrcode": qrcode,
                "qrcode_img_content": f"{public_base_url}/scan/{qrcode}",
            }
        )

    @app.get("/ilink/bot/get_qrcode_status")
    def get_qrcode_status():
        qrcode = request.args.get("qrcode", "").strip()
        qrcodes = state["qrcodes"]
        assert isinstance(qrcodes, dict)
        record = qrcodes.get(qrcode)
        if not isinstance(record, dict):
            return jsonify({"status": "expired"}), 404

        if record["status"] != "confirmed":
            return jsonify({"status": record["status"]})

        return jsonify(
            {
                "status": "confirmed",
                "bot_token": record["bot_token"],
                "baseurl": public_base_url,
                "ilink_bot_id": record["bot_id"],
            }
        )

    @app.post("/ilink/bot/getupdates")
    def getupdates():
        try:
            bot_token = _require_bot_token()
        except PermissionError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 401

        bot = _bot_state(bot_token)
        with lock:
            msgs = list(bot["updates"])
            bot["updates"].clear()
            cursor = f"cursor_{next(update_counter)}"
        return jsonify({"msgs": msgs, "get_updates_buf": cursor})

    @app.post("/ilink/bot/sendmessage")
    def sendmessage():
        try:
            bot_token = _require_bot_token()
        except PermissionError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 401

        payload = request.get_json(force=True)
        bot = _bot_state(bot_token)
        msg = payload.get("msg", {}) if isinstance(payload, dict) else {}
        item_list = msg.get("item_list", []) if isinstance(msg, dict) else []
        first_text = ""
        if item_list and isinstance(item_list[0], dict):
            first_text = (
                item_list[0].get("text_item", {}).get("text", "")
                if isinstance(item_list[0].get("text_item", {}), dict)
                else ""
            )
        with lock:
            bot["sent"].append(
                {
                    "id": next(sent_counter),
                    "to_user_id": msg.get("to_user_id"),
                    "context_token": msg.get("context_token"),
                    "text": first_text,
                    "raw": payload,
                }
            )
        return jsonify({"ok": True})

    @app.post("/__e2e/reset")
    def reset():
        with lock:
            _reset_state()
        return jsonify({"ok": True})

    @app.post("/__e2e/confirm")
    def confirm():
        payload = request.get_json(silent=True) or {}
        requested_qrcode = payload.get("qrcode")
        with lock:
            qrcodes = state["qrcodes"]
            assert isinstance(qrcodes, dict)
            qrcode = requested_qrcode or state["last_qrcode"]
            record = qrcodes.get(qrcode)
            if not isinstance(record, dict):
                return jsonify({"ok": False, "error": "qrcode_not_found"}), 404
            record["status"] = "confirmed"
        return jsonify({"ok": True, "qrcode": qrcode, "bot_token": record["bot_token"]})

    @app.post("/__e2e/inbound")
    def inbound():
        payload = request.get_json(force=True)
        bot_token = payload.get("bot_token")
        from_user_id = payload.get("from_user_id")
        text = payload.get("text")
        context_token = payload.get("context_token") or "ctx_e2e"
        if not isinstance(bot_token, str) or not bot_token.strip():
            return jsonify({"ok": False, "error": "missing_bot_token"}), 400
        if not isinstance(from_user_id, str) or not from_user_id.strip():
            return jsonify({"ok": False, "error": "missing_from_user_id"}), 400
        if not isinstance(text, str) or not text.strip():
            return jsonify({"ok": False, "error": "missing_text"}), 400

        try:
            bot = _bot_state(bot_token)
        except KeyError:
            return jsonify({"ok": False, "error": "bot_not_found"}), 404

        with lock:
            bot["updates"].append(
                {
                    "from_user_id": from_user_id,
                    "context_token": context_token,
                    "item_list": [{"type": 1, "text_item": {"text": text}}],
                }
            )
        return jsonify({"ok": True})

    @app.get("/__e2e/sent")
    def sent():
        bot_token = request.args.get("bot_token", "").strip()
        clear = request.args.get("clear", "0") == "1"
        try:
            bot = _bot_state(bot_token)
        except KeyError:
            return jsonify({"ok": False, "error": "bot_not_found"}), 404

        with lock:
            sent_messages = list(bot["sent"])
            if clear:
                bot["sent"].clear()
        return jsonify({"ok": True, "data": sent_messages})

    @app.get("/__e2e/state")
    def snapshot():
        with lock:
            return jsonify({"ok": True, "data": state})

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Fake iLink WeChat provider for local E2E.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=19090)
    parser.add_argument("--public-base-url", default=None)
    args = parser.parse_args()

    public_base_url = args.public_base_url or f"http://{args.host}:{args.port}"
    app = create_app(public_base_url=public_base_url)
    app.run(host=args.host, port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
