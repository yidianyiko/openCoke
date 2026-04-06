from flask import Flask, jsonify, render_template


def create_app(testing: bool = False):
    app = Flask(__name__, template_folder="templates")
    app.config["TESTING"] = testing
    app.config.setdefault("COKE_BRIDGE_API_KEY", "test-bridge-key")

    @app.get("/bridge/healthz")
    def healthz():
        return jsonify({"ok": True})

    @app.post("/bridge/inbound")
    def inbound():
        from connector.clawscale_bridge.auth import require_bridge_auth

        ok, error = require_bridge_auth(app.config["COKE_BRIDGE_API_KEY"])
        if not ok:
            return error

        if "TEST_BRIDGE_RESPONSE" in app.config:
            return jsonify(app.config["TEST_BRIDGE_RESPONSE"])

        return jsonify({"ok": False, "error": "bridge service not wired"}), 500

    @app.get("/bind/<ticket_id>")
    def bind_page(ticket_id: str):
        return render_template("bind.html", ticket_id=ticket_id)

    @app.post("/bind/<ticket_id>/submit")
    def submit_bind(ticket_id: str):
        return jsonify({"ok": True, "ticket_id": ticket_id})

    return app
