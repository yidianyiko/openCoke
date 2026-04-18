import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from bson import ObjectId
from pymongo import MongoClient

from conf.config import CONF


AUTH_ONLY_FIELDS = {
    "email",
    "phone_number",
    "status",
    "is_character",
    "password",
    "password_hash",
    "password_salt",
    "bind_secret_hash",
    "bind_token",
    "verify_token",
    "verify_token_expires_at",
    "verification_token",
    "verification_token_expires_at",
    "email_verified",
    "reset_password_token",
    "reset_password_expires_at",
    "password_reset_token",
    "password_reset_expires_at",
    "session_id",
    "session_token",
    "session_expires_at",
    "session_started_at",
    "last_login_at",
}
PROFILE_FIELDS = {"name", "display_name", "platforms", "user_info"}
SETTINGS_FIELDS = {"timezone", "access"}
CHARACTER_FIELDS = {"name", "nickname", "platforms", "user_info"}


class MigrationSafetyError(ValueError):
    def __init__(self, code: str, report: Dict[str, Any]):
        super().__init__(code)
        self.code = code
        self.report = report


def _json_default(value: Any):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, ObjectId):
        return str(value)
    raise TypeError(f"unsupported_json_value:{type(value)!r}")


def _normalize_account_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _stringify_id(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _is_auth_only_field(field_name: str) -> bool:
    return field_name in AUTH_ONLY_FIELDS


def _current_migration_timestamp() -> datetime:
    return datetime.utcnow()


def _classify_non_character(document: Dict[str, Any]) -> Dict[str, Any]:
    account_id = _normalize_account_id(document.get("account_id"))
    doc_id = _stringify_id(document.get("_id"))

    auth_only_fields = sorted(
        field for field in document if field != "_id" and _is_auth_only_field(field)
    )
    unsupported_fields = sorted(
        field
        for field in document
        if field not in PROFILE_FIELDS
        and field not in SETTINGS_FIELDS
        and field not in AUTH_ONLY_FIELDS
        and field != "_id"
        and field != "account_id"
    )

    if account_id is None:
        return {
            "kind": "missing_account_id",
            "document_id": doc_id,
            "auth_only_fields": auth_only_fields,
            "unsupported_fields": unsupported_fields,
        }

    migrated_at = _current_migration_timestamp()
    profile_doc = {
        "account_id": account_id,
        "migration": {
            "source_collection": "users",
            "source_user_id": doc_id,
            "migrated_at": migrated_at,
        },
    }
    settings_doc = {
        "account_id": account_id,
        "migration": {
            "source_collection": "users",
            "source_user_id": doc_id,
            "migrated_at": migrated_at,
        },
    }

    for field in PROFILE_FIELDS:
        if field in document:
            profile_doc[field] = document[field]

    for field in SETTINGS_FIELDS:
        if field in document:
            settings_doc[field] = document[field]

    return {
        "kind": "customer",
        "document_id": doc_id,
        "account_id": account_id,
        "profile_doc": profile_doc,
        "settings_doc": settings_doc,
        "auth_only_fields": auth_only_fields,
        "unsupported_fields": unsupported_fields,
    }


def _classify_character(document: Dict[str, Any]) -> Dict[str, Any]:
    auth_only_fields = sorted(
        field for field in document if field != "_id" and _is_auth_only_field(field)
    )
    unsupported_fields = sorted(
        field
        for field in document
        if field not in CHARACTER_FIELDS
        and field not in AUTH_ONLY_FIELDS
        and field != "_id"
    )

    doc_id = _stringify_id(document.get("_id"))
    character_doc = {
        "_id": document.get("_id"),
        "legacy_user_id": doc_id,
        "migrated_at": _current_migration_timestamp(),
    }
    for field in CHARACTER_FIELDS:
        if field in document:
            character_doc[field] = document[field]

    return {
        "kind": "character",
        "document_id": doc_id,
        "character_doc": character_doc,
        "auth_only_fields": auth_only_fields,
        "unsupported_fields": unsupported_fields,
    }


def _build_report(classifications: Iterable[Dict[str, Any]], dry_run: bool) -> Dict[str, Any]:
    classifications = list(classifications)
    auth_only_fields = sorted(
        {
            field
            for classification in classifications
            for field in classification.get("auth_only_fields", [])
        }
    )
    missing_account_ids = [
        classification["document_id"]
        for classification in classifications
        if classification["kind"] == "missing_account_id"
    ]
    unsupported_fields = [
        {
            "document_id": classification["document_id"],
            "fields": classification["unsupported_fields"],
        }
        for classification in classifications
        if classification.get("unsupported_fields")
    ]

    return {
        "dry_run": dry_run,
        "users_scanned": len(classifications),
        "profiles_to_write": sum(
            1 for classification in classifications if classification["kind"] == "customer"
        ),
        "settings_to_write": sum(
            1 for classification in classifications if classification["kind"] == "customer"
        ),
        "characters_to_write": sum(
            1 for classification in classifications if classification["kind"] == "character"
        ),
        "auth_only_fields_to_drop": auth_only_fields,
        "missing_account_id": missing_account_ids,
        "unclassified_fields": unsupported_fields,
    }


def _merge_account_document(collection, account_id: str, document: Dict[str, Any]) -> None:
    set_fields = {key: value for key, value in document.items() if key != "account_id"}
    collection.update_one(
        {"account_id": account_id},
        {"$set": set_fields, "$setOnInsert": {"account_id": account_id}},
        upsert=True,
    )


def migrate_legacy_users(
    *,
    collections: Optional[Dict[str, Any]] = None,
    dry_run: bool = True,
    mongo_uri: str = "mongodb://"
    + CONF["mongodb"]["mongodb_ip"]
    + ":"
    + CONF["mongodb"]["mongodb_port"]
    + "/",
    db_name: str = CONF["mongodb"]["mongodb_name"],
) -> Dict[str, Any]:
    client = None
    owns_client = False
    if collections is None:
        client = MongoClient(mongo_uri)
        db = client[db_name]
        collections = {
            "users": db.get_collection("users"),
            "user_profiles": db.get_collection("user_profiles"),
            "coke_settings": db.get_collection("coke_settings"),
            "characters": db.get_collection("characters"),
        }
        owns_client = True

    try:
        user_documents = list(collections["users"].find({}))
        classifications = []
        for document in user_documents:
            if document.get("is_character") is True:
                classifications.append(_classify_character(document))
            else:
                classifications.append(_classify_non_character(document))

        report = _build_report(classifications, dry_run=dry_run)
        if dry_run:
            return report

        if report["missing_account_id"]:
            raise MigrationSafetyError("missing_account_id", report)
        if report["unclassified_fields"]:
            raise MigrationSafetyError("unclassified_fields", report)

        for document, classification in zip(user_documents, classifications):
            if classification["kind"] == "customer":
                _merge_account_document(
                    collections["user_profiles"],
                    classification["account_id"],
                    classification["profile_doc"],
                )
                _merge_account_document(
                    collections["coke_settings"],
                    classification["account_id"],
                    classification["settings_doc"],
                )
            elif classification["kind"] == "character":
                character_doc = classification["character_doc"]
                collections["characters"].replace_one(
                    {"_id": character_doc["_id"]},
                    character_doc,
                    upsert=True,
                )

            collections["users"].delete_one({"_id": document["_id"]})

        report["dry_run"] = False
        return report
    finally:
        if owns_client and client is not None:
            client.close()


def _write_report(report: Dict[str, Any], report_path: Optional[str]) -> None:
    if not report_path:
        return
    target_path = Path(report_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate legacy Mongo users into business collections.")
    parser.add_argument("--dry-run", action="store_true", help="Scan and classify without writing.")
    parser.add_argument("--mongo-uri", default=None)
    parser.add_argument("--db-name", default=None)
    parser.add_argument("--report-path", default=None)
    args = parser.parse_args()

    mongo_uri = args.mongo_uri or (
        "mongodb://"
        + CONF["mongodb"]["mongodb_ip"]
        + ":"
        + CONF["mongodb"]["mongodb_port"]
        + "/"
    )
    db_name = args.db_name or CONF["mongodb"]["mongodb_name"]

    try:
        report = migrate_legacy_users(
            dry_run=args.dry_run,
            mongo_uri=mongo_uri,
            db_name=db_name,
        )
        exit_code = 0
    except MigrationSafetyError as exc:
        report = exc.report
        exit_code = 1

    _write_report(report, args.report_path)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=_json_default))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
