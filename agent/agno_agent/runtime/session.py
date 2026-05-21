from __future__ import annotations

from threading import Lock
from typing import Any

_agent_session_db: Any | None = None
_agent_session_db_lock = Lock()


def build_agent_session_db() -> Any:
    from agno.db.mongo import MongoDb
    from conf.config import CONF

    return MongoDb(
        session_collection="agent_sessions",
        db_url=(
            "mongodb://"
            f"{CONF['mongodb']['mongodb_ip']}:{CONF['mongodb']['mongodb_port']}/"
        ),
        db_name=CONF["mongodb"]["mongodb_name"],
    )


def initialize_agent_session_db(db: Any | None = None) -> Any:
    global _agent_session_db

    with _agent_session_db_lock:
        if db is not None:
            _agent_session_db = db
        elif _agent_session_db is None:
            _agent_session_db = build_agent_session_db()
        return _agent_session_db


def get_agent_session_db() -> Any:
    if _agent_session_db is None:
        return initialize_agent_session_db()
    return _agent_session_db


def reset_agent_session_db_for_tests() -> None:
    global _agent_session_db

    _agent_session_db = None
