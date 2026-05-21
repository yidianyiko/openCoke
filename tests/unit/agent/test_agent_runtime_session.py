from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from agent.agno_agent.runtime import session
from conf.config import CONF


@pytest.fixture(autouse=True)
def reset_session_db():
    session.reset_agent_session_db_for_tests()
    yield
    session.reset_agent_session_db_for_tests()


def test_build_agent_session_db_uses_configured_mongodb_session_collection(
    monkeypatch,
):
    captured = {}

    class FakeMongoDb:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(
        sys.modules,
        "agno.db.mongo",
        SimpleNamespace(MongoDb=FakeMongoDb),
    )
    monkeypatch.setitem(
        CONF,
        "mongodb",
        {
            "mongodb_ip": "mongo-host",
            "mongodb_port": "27018",
            "mongodb_name": "coke-test",
        },
    )

    db = session.build_agent_session_db()

    assert isinstance(db, FakeMongoDb)
    assert captured == {
        "session_collection": "agent_sessions",
        "db_url": "mongodb://mongo-host:27018/",
        "db_name": "coke-test",
    }


def test_initialize_agent_session_db_stores_and_returns_injected_object():
    injected = object()

    assert session.initialize_agent_session_db(injected) is injected
    assert session.get_agent_session_db() is injected


def test_initialize_agent_session_db_without_injected_db_is_idempotent(
    monkeypatch,
):
    built = [object(), object()]

    def fake_build_agent_session_db():
        return built.pop(0)

    monkeypatch.setattr(
        session,
        "build_agent_session_db",
        fake_build_agent_session_db,
    )

    first = session.initialize_agent_session_db()
    second = session.initialize_agent_session_db()

    assert first is second
    assert len(built) == 1


def test_get_agent_session_db_lazily_initializes_then_returns_stored_object(
    monkeypatch,
):
    built = object()
    calls = 0

    def fake_build_agent_session_db():
        nonlocal calls
        calls += 1
        return built

    monkeypatch.setattr(
        session,
        "build_agent_session_db",
        fake_build_agent_session_db,
    )

    assert session.get_agent_session_db() is built
    assert session.get_agent_session_db() is built
    assert calls == 1


def test_reset_agent_session_db_for_tests_clears_stored_state(monkeypatch):
    injected = object()
    rebuilt = object()

    monkeypatch.setattr(session, "build_agent_session_db", lambda: rebuilt)

    assert session.initialize_agent_session_db(injected) is injected

    session.reset_agent_session_db_for_tests()

    assert session.get_agent_session_db() is rebuilt


def test_get_agent_session_db_serializes_concurrent_lazy_initialization(
    monkeypatch,
):
    built_objects = []

    def fake_build_agent_session_db():
        built = object()
        built_objects.append(built)
        time.sleep(0.02)
        return built

    monkeypatch.setattr(
        session,
        "build_agent_session_db",
        fake_build_agent_session_db,
    )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: session.get_agent_session_db(), range(8)))

    assert len(set(map(id, results))) == 1
    assert len(built_objects) == 1
