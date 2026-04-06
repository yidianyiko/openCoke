from flask import Flask, jsonify, render_template, request

from conf.config import CONF
from connector.clawscale_bridge.identity_service import IdentityService
from connector.clawscale_bridge.message_gateway import CokeMessageGateway
from connector.clawscale_bridge.reply_waiter import ReplyWaiter
from dao.binding_ticket_dao import BindingTicketDAO
from dao.external_identity_dao import ExternalIdentityDAO
from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO


def _mongo_uri() -> str:
    return (
        "mongodb://"
        + CONF["mongodb"]["mongodb_ip"]
        + ":"
        + CONF["mongodb"]["mongodb_port"]
        + "/"
    )


def _resolve_target_character_id(user_dao: UserDAO) -> str:
    character_alias = CONF.get("default_character_alias", "coke")
    characters = user_dao.find_characters({"name": character_alias}, limit=1)
    if not characters:
        raise ValueError(f"target character not found for alias={character_alias}")
    return str(characters[0]["_id"])


def _build_default_bridge_gateway():
    bridge_conf = CONF["clawscale_bridge"]
    mongo_uri = _mongo_uri()
    db_name = CONF["mongodb"]["mongodb_name"]

    user_dao = UserDAO(mongo_uri=mongo_uri, db_name=db_name)
    external_identity_dao = ExternalIdentityDAO(mongo_uri=mongo_uri, db_name=db_name)
    binding_ticket_dao = BindingTicketDAO(mongo_uri=mongo_uri, db_name=db_name)
    mongo = MongoDBBase(connection_string=mongo_uri, db_name=db_name)
    message_gateway = CokeMessageGateway(mongo=mongo, user_dao=user_dao)
    reply_waiter = ReplyWaiter(
        mongo=mongo,
        poll_interval_seconds=bridge_conf["poll_interval_seconds"],
        timeout_seconds=bridge_conf["reply_timeout_seconds"],
    )

    return IdentityService(
        external_identity_dao=external_identity_dao,
        binding_ticket_dao=binding_ticket_dao,
        message_gateway=message_gateway,
        reply_waiter=reply_waiter,
        bind_base_url=bridge_conf["bind_base_url"],
        target_character_id=_resolve_target_character_id(user_dao),
    )


def create_app(testing: bool = False):
    app = Flask(__name__, template_folder="templates")
    app.config["TESTING"] = testing
    if testing:
        app.config["COKE_BRIDGE_API_KEY"] = "test-bridge-key"
    else:
        app.config["COKE_BRIDGE_API_KEY"] = CONF["clawscale_bridge"]["api_key"]
        app.config["BRIDGE_GATEWAY"] = _build_default_bridge_gateway()

    @app.get("/bridge/healthz")
    def healthz():
        return jsonify({"ok": True})

    @app.post("/bridge/inbound")
    def inbound():
        from connector.clawscale_bridge.auth import require_bridge_auth

        ok, error = require_bridge_auth(app.config["COKE_BRIDGE_API_KEY"])
        if not ok:
            body, status = error
            return jsonify(body), status

        payload = request.get_json(force=True)
        gateway = app.config.get("BRIDGE_GATEWAY")
        if gateway is None:
            return jsonify({"ok": False, "error": "bridge service not wired"}), 500

        result = gateway.handle_inbound(payload)
        if result["status"] == "bind_required":
            response = {"ok": True, "reply": result["reply"]}
            if "bind_url" in result:
                response["bind_url"] = result["bind_url"]
            return jsonify(response)

        return jsonify({"ok": True, "reply": result["reply"]})

    @app.get("/bind/<ticket_id>")
    def bind_page(ticket_id: str):
        return render_template("bind.html", ticket_id=ticket_id)

    @app.post("/bind/<ticket_id>/submit")
    def submit_bind(ticket_id: str):
        return jsonify({"ok": True, "ticket_id": ticket_id})

    return app


if __name__ == "__main__":
    bridge_conf = CONF["clawscale_bridge"]
    create_app().run(
        host=bridge_conf["host"],
        port=bridge_conf["port"],
    )
