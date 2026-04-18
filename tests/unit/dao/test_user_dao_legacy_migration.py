import importlib.util
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
        self.deleted = []

    def find(self, *args, **kwargs):
        return list(self.documents)

    def replace_one(self, selector, document, upsert=False):
        self.replaced.append((selector, document, upsert))
        return None

    def delete_one(self, selector):
        self.deleted.append(selector)
        return None


def make_collections(documents):
    return {
        "users": FakeCollection(documents),
        "user_profiles": FakeCollection([]),
        "coke_settings": FakeCollection([]),
        "characters": FakeCollection([]),
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

    with pytest.raises(ValueError, match="missing_account_id"):
        module.migrate_legacy_users(collections=collections, dry_run=False)

    assert collections["user_profiles"].replaced == []
    assert collections["coke_settings"].replaced == []
    assert collections["characters"].replaced == []


def test_real_migration_preserves_character_nickname_in_characters_collection():
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
    selector, document, upsert = collections["characters"].replaced[0]
    assert selector == {"_id": "507f1f77bcf86cd799439012"}
    assert upsert is True
    assert document["nickname"] == "Qiaoyun"
    assert document["migration"]["source_collection"] == "users"
