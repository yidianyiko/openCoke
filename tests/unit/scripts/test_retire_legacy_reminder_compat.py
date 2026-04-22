import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_script_module():
    script_path = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "retire_legacy_reminder_compat.py"
    )
    spec = importlib.util.spec_from_file_location(
        "retire_legacy_reminder_compat_script",
        script_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeConversationsCollection:
    def __init__(self, future_count: int):
        self.future_count = future_count
        self.update_calls = []

    def count_documents(self, query):
        assert query == {"conversation_info.future": {"$exists": True}}
        return self.future_count

    def update_many(self, query, update):
        self.update_calls.append((query, update))
        return SimpleNamespace(
            matched_count=self.future_count,
            modified_count=self.future_count,
        )


class FakeRemindersCollection:
    def __init__(self, document_count: int):
        self.document_count = document_count
        self.renamed_to = None

    def count_documents(self, query):
        assert query == {}
        return self.document_count

    def rename(self, new_name):
        self.renamed_to = new_name
        return SimpleNamespace(name=new_name)


class FakeDatabase:
    def __init__(
        self,
        *,
        future_count: int,
        reminder_count: int,
        reminders_exists: bool = True,
    ):
        self.conversations = FakeConversationsCollection(future_count)
        self.reminders = FakeRemindersCollection(reminder_count)
        self.reminders_exists = reminders_exists

    def list_collection_names(self):
        names = ["conversations"]
        if self.reminders_exists:
            names.append("reminders")
        return names

    def get_collection(self, name):
        if name == "conversations":
            return self.conversations
        if name == "reminders":
            if not self.reminders_exists:
                raise KeyError(name)
            return self.reminders
        raise KeyError(name)


class FakeMongoClient:
    def __init__(self, db, *args, **kwargs):
        self._db = db
        self.args = args
        self.kwargs = kwargs
        self.admin = SimpleNamespace(command=lambda command: None)
        self.closed = False

    def __getitem__(self, name):
        assert name == "test_db"
        return self._db

    def close(self):
        self.closed = True


def test_retire_legacy_reminder_compat_reports_counts_without_mutating_data():
    script = _load_script_module()
    db = FakeDatabase(future_count=3, reminder_count=5, reminders_exists=True)
    client = FakeMongoClient(db, "mongodb://example", serverSelectionTimeoutMS=5000)

    report = script.retire_legacy_reminder_compat(
        mongo_client_factory=lambda *args, **kwargs: client,
        mongo_uri="mongodb://example",
        db_name="test_db",
        execute=False,
        now=datetime(2026, 4, 22, 9, 30, 45, tzinfo=UTC),
    )

    assert report == {
        "dry_run": True,
        "execute": False,
        "conversation_future": {
            "count": 3,
            "matched_count": 0,
            "modified_count": 0,
        },
        "reminders": {
            "exists": True,
            "document_count": 5,
            "archive_collection_name": None,
            "archived": False,
        },
    }
    assert db.conversations.update_calls == []
    assert db.reminders.renamed_to is None
    assert client.closed is True


def test_retire_legacy_reminder_compat_executes_unset_and_archive():
    script = _load_script_module()
    db = FakeDatabase(future_count=2, reminder_count=4, reminders_exists=True)
    client = FakeMongoClient(db, "mongodb://example", serverSelectionTimeoutMS=5000)

    report = script.retire_legacy_reminder_compat(
        mongo_client_factory=lambda *args, **kwargs: client,
        mongo_uri="mongodb://example",
        db_name="test_db",
        execute=True,
        now=datetime(2026, 4, 22, 9, 30, 45, tzinfo=UTC),
    )

    assert report == {
        "dry_run": False,
        "execute": True,
        "conversation_future": {
            "count": 2,
            "matched_count": 2,
            "modified_count": 2,
        },
        "reminders": {
            "exists": True,
            "document_count": 4,
            "archive_collection_name": "reminders_legacy_retired_20260422093045",
            "archived": True,
        },
    }
    assert db.conversations.update_calls == [
        (
            {"conversation_info.future": {"$exists": True}},
            {"$unset": {"conversation_info.future": ""}},
        )
    ]
    assert db.reminders.renamed_to == "reminders_legacy_retired_20260422093045"
    assert client.closed is True


def test_retire_legacy_reminder_compat_handles_absent_reminders_collection():
    script = _load_script_module()
    db = FakeDatabase(future_count=1, reminder_count=0, reminders_exists=False)
    client = FakeMongoClient(db, "mongodb://example", serverSelectionTimeoutMS=5000)

    report = script.retire_legacy_reminder_compat(
        mongo_client_factory=lambda *args, **kwargs: client,
        mongo_uri="mongodb://example",
        db_name="test_db",
        execute=True,
        now=datetime(2026, 4, 22, 9, 30, 45, tzinfo=UTC),
    )

    assert report == {
        "dry_run": False,
        "execute": True,
        "conversation_future": {
            "count": 1,
            "matched_count": 1,
            "modified_count": 1,
        },
        "reminders": {
            "exists": False,
            "document_count": 0,
            "archive_collection_name": None,
            "archived": False,
        },
    }
    assert db.conversations.update_calls == [
        (
            {"conversation_info.future": {"$exists": True}},
            {"$unset": {"conversation_info.future": ""}},
        )
    ]
    assert client.closed is True


def test_main_supports_cli_overrides_and_report_path(tmp_path, monkeypatch, capsys):
    script = _load_script_module()
    captured = {}

    def fake_retire_legacy_reminder_compat(**kwargs):
        captured.update(kwargs)
        return {
            "dry_run": False,
            "execute": True,
            "conversation_future": {
                "count": 1,
                "matched_count": 1,
                "modified_count": 1,
            },
            "reminders": {
                "exists": False,
                "document_count": 0,
                "archive_collection_name": None,
                "archived": False,
            },
        }

    monkeypatch.setattr(
        script,
        "retire_legacy_reminder_compat",
        fake_retire_legacy_reminder_compat,
    )

    report_path = tmp_path / "retirement-report.json"
    exit_code = script.main(
        [
            "--execute",
            "--mongo-uri",
            "mongodb://override",
            "--db-name",
            "test_db",
            "--report-path",
            str(report_path),
        ]
    )

    assert exit_code == 0
    assert captured["execute"] is True
    assert captured["mongo_uri"] == "mongodb://override"
    assert captured["db_name"] == "test_db"

    stdout = json.loads(capsys.readouterr().out)
    assert stdout["execute"] is True
    assert json.loads(report_path.read_text()) == stdout


def test_main_keeps_success_when_report_path_write_fails(
    tmp_path,
    monkeypatch,
    capsys,
):
    script = _load_script_module()

    monkeypatch.setattr(
        script,
        "retire_legacy_reminder_compat",
        lambda **kwargs: {
            "dry_run": False,
            "execute": True,
            "conversation_future": {
                "count": 1,
                "matched_count": 1,
                "modified_count": 1,
            },
            "reminders": {
                "exists": True,
                "document_count": 2,
                "archive_collection_name": "reminders_legacy_retired_20260422093045",
                "archived": True,
            },
        },
    )

    blocked_parent = tmp_path / "blocked-parent"
    blocked_parent.write_text("not-a-directory", encoding="utf-8")
    blocked_report_path = blocked_parent / "retirement-report.json"

    exit_code = script.main(
        [
            "--execute",
            "--report-path",
            str(blocked_report_path),
        ]
    )

    assert exit_code == 0
    stdout, stderr = capsys.readouterr()
    assert json.loads(stdout)["execute"] is True
    assert "warning" in stderr.lower()
    assert str(blocked_report_path) in stderr
