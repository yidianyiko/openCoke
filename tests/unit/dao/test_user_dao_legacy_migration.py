import importlib.util
import json
from contextlib import redirect_stdout
from datetime import datetime
from io import StringIO
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "connector" / "scripts" / "migrate-legacy-users.py"


def load_migration_module():
    spec = importlib.util.spec_from_file_location("migrate_legacy_users", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeCollection:
    def __init__(self, documents):
        self.documents = list(documents)
        self.replaced = []
        self.updated = []
        self.deleted = []

    def find(self, *args, **kwargs):
        return list(self.documents)

    def replace_one(self, selector, document, upsert=False):
        self.replaced.append((selector, document, upsert))
        return None

    def update_one(self, selector, update, upsert=False):
        self.updated.append((selector, update, upsert))
        matched = None
        for document in self.documents:
            if all(document.get(key) == value for key, value in selector.items()):
                matched = document
                break

        if matched is None:
            matched = dict(selector)
            self.documents.append(matched)

        for key, value in update.get("$set", {}).items():
            matched[key] = value

        for key, value in update.get("$setOnInsert", {}).items():
            matched.setdefault(key, value)

        return None

    def delete_one(self, selector):
        self.deleted.append(selector)
        return None


def make_collections(
    user_documents,
    profile_documents=None,
    settings_documents=None,
    character_documents=None,
):
    return {
        "users": FakeCollection(user_documents),
        "user_profiles": FakeCollection(profile_documents or []),
        "coke_settings": FakeCollection(settings_documents or []),
        "characters": FakeCollection(character_documents or []),
    }


def test_dry_run_reports_missing_account_id_and_auth_only_fields():
    module = load_migration_module()
    collections = make_collections(
        [
            {
                "_id": "507f1f77bcf86cd799439011",
                "name": "Alice",
                "display_name": "Alice",
                "timezone": "Asia/Tokyo",
                "email": "alice@example.com",
            }
        ]
    )

    report = module.migrate_legacy_users(collections=collections, dry_run=True)

    assert report["dry_run"] is True
    assert report["users_scanned"] == 1
    assert report["profiles_to_write"] == 0
    assert report["settings_to_write"] == 0
    assert report["characters_to_write"] == 0
    assert report["auth_only_fields_to_drop"] == ["email"]
    assert report["missing_account_id"] == ["507f1f77bcf86cd799439011"]


def test_dry_run_surfaces_unknown_fields_instead_of_treating_them_as_auth_only():
    module = load_migration_module()
    collections = make_collections(
        [
            {
                "_id": "507f1f77bcf86cd799439013",
                "account_id": "acct_123",
                "name": "Alice",
                "session_preferences": {"theme": "dark"},
            }
        ]
    )

    report = module.migrate_legacy_users(collections=collections, dry_run=True)

    assert report["auth_only_fields_to_drop"] == []
    assert report["unclassified_fields"] == [
        {
            "document_id": "507f1f77bcf86cd799439013",
            "fields": ["session_preferences"],
        }
    ]


def test_real_migration_stops_on_missing_account_id_without_writes():
    module = load_migration_module()
    collections = make_collections(
        [
            {
                "_id": "507f1f77bcf86cd799439011",
                "name": "Alice",
            }
        ]
    )

    with pytest.raises(module.MigrationSafetyError, match="missing_account_id"):
        module.migrate_legacy_users(collections=collections, dry_run=False)

    assert collections["user_profiles"].updated == []
    assert collections["coke_settings"].updated == []
    assert collections["characters"].replaced == []


def test_real_migration_preserves_character_phase1_shape():
    module = load_migration_module()
    collections = make_collections(
        [
            {
                "_id": "507f1f77bcf86cd799439012",
                "is_character": True,
                "name": "qiaoyun",
                "nickname": "Qiaoyun",
                "platforms": {"wechat": {"nickname": "Qiaoyun"}},
                "user_info": {"description": "prompt"},
                "status": "normal",
            }
        ]
    )

    report = module.migrate_legacy_users(collections=collections, dry_run=False)

    assert report["characters_to_write"] == 1
    selector, update, upsert = collections["characters"].updated[0]
    assert selector == {"_id": "507f1f77bcf86cd799439012"}
    assert upsert is True
    document = collections["characters"].documents[0]
    assert document["_id"] == "507f1f77bcf86cd799439012"
    assert document["name"] == "qiaoyun"
    assert document["nickname"] == "Qiaoyun"
    assert document["platforms"] == {"wechat": {"nickname": "Qiaoyun"}}
    assert document["user_info"] == {"description": "prompt"}
    assert document["legacy_user_id"] == "507f1f77bcf86cd799439012"
    assert isinstance(document["migrated_at"], datetime)
    assert "migration" not in document
    assert collections["characters"].replaced == []


def test_real_migration_merges_character_docs_without_erasing_existing_fields():
    module = load_migration_module()
    collections = make_collections(
        [
            {
                "_id": "507f1f77bcf86cd799439015",
                "is_character": True,
                "name": "coke",
                "nickname": "Coke",
                "platforms": {"wechat": {"nickname": "Coke"}},
                "user_info": {"description": "prompt"},
            }
        ],
        character_documents=[
            {
                "_id": "507f1f77bcf86cd799439015",
                "avatar_url": "https://example.com/avatar.png",
            }
        ],
    )

    report = module.migrate_legacy_users(collections=collections, dry_run=False)

    assert report["characters_to_write"] == 1
    character_doc = collections["characters"].documents[0]
    assert character_doc["avatar_url"] == "https://example.com/avatar.png"
    assert character_doc["name"] == "coke"
    assert character_doc["legacy_user_id"] == "507f1f77bcf86cd799439015"
    assert collections["characters"].replaced == []
    assert collections["characters"].updated != []


def test_real_migration_merges_customer_docs_without_erasing_existing_fields():
    module = load_migration_module()
    collections = make_collections(
        [
            {
                "_id": "507f1f77bcf86cd799439014",
                "account_id": "acct_123",
                "name": "Alice",
                "display_name": "Alice",
                "timezone": "Asia/Tokyo",
            }
        ],
        profile_documents=[{"account_id": "acct_123", "notes": "keep-me"}],
        settings_documents=[{"account_id": "acct_123", "ui_theme": "dark"}],
    )

    report = module.migrate_legacy_users(collections=collections, dry_run=False)

    assert report["profiles_to_write"] == 1
    profile_doc = collections["user_profiles"].documents[0]
    settings_doc = collections["coke_settings"].documents[0]
    assert profile_doc["notes"] == "keep-me"
    assert profile_doc["name"] == "Alice"
    assert settings_doc["ui_theme"] == "dark"
    assert settings_doc["timezone"] == "Asia/Tokyo"
    assert collections["user_profiles"].replaced == []
    assert collections["coke_settings"].replaced == []


def test_main_prints_real_failure_report_and_exits_nonzero(monkeypatch):
    module = load_migration_module()
    failure_report = {
        "dry_run": False,
        "users_scanned": 1,
        "profiles_to_write": 0,
        "settings_to_write": 0,
        "characters_to_write": 0,
        "auth_only_fields_to_drop": [],
        "missing_account_id": [],
        "unclassified_fields": [{"document_id": "u1", "fields": ["session_preferences"]}],
    }

    def fake_migrate_legacy_users(**kwargs):
        raise module.MigrationSafetyError("unclassified_fields", failure_report)

    monkeypatch.setattr(module, "migrate_legacy_users", fake_migrate_legacy_users)
    monkeypatch.setattr("sys.argv", ["migrate-legacy-users.py"])

    output = StringIO()
    with redirect_stdout(output):
        exit_code = module.main()

    assert exit_code == 1
    assert json.loads(output.getvalue()) == failure_report
