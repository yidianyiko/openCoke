#!/usr/bin/env python3
import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pymongo import MongoClient

from conf.config import CONF


def default_mongo_uri() -> str:
    return (
        "mongodb://"
        + CONF["mongodb"]["mongodb_ip"]
        + ":"
        + CONF["mongodb"]["mongodb_port"]
        + "/"
    )


def default_db_name() -> str:
    return CONF["mongodb"]["mongodb_name"]


def archive_collection_name(now: datetime) -> str:
    return f"reminders_legacy_retired_{now.astimezone(UTC).strftime('%Y%m%d%H%M%S')}"


def retire_legacy_reminder_compat(
    *,
    mongo_client_factory: Callable[..., Any] = MongoClient,
    mongo_uri: Optional[str] = None,
    db_name: Optional[str] = None,
    execute: bool = False,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    mongo_uri = mongo_uri or default_mongo_uri()
    db_name = db_name or default_db_name()
    now = now or datetime.now(UTC)

    client = mongo_client_factory(
        mongo_uri,
        serverSelectionTimeoutMS=5000,
    )

    try:
        client.admin.command("ping")
        db = client[db_name]

        conversations = db.get_collection("conversations")
        future_query = {"conversation_info.future": {"$exists": True}}
        future_count = conversations.count_documents(future_query)
        matched_count = 0
        modified_count = 0

        if execute:
            update_result = conversations.update_many(
                future_query,
                {"$unset": {"conversation_info.future": ""}},
            )
            matched_count = int(getattr(update_result, "matched_count", 0) or 0)
            modified_count = int(getattr(update_result, "modified_count", 0) or 0)

        collection_names = set(db.list_collection_names())
        reminders_exists = "reminders" in collection_names
        reminder_count = 0
        archived = False
        archived_name = None

        if reminders_exists:
            reminders = db.get_collection("reminders")
            reminder_count = reminders.count_documents({})
            if execute:
                archived_name = archive_collection_name(now)
                reminders.rename(archived_name)
                archived = True

        return {
            "dry_run": not execute,
            "execute": execute,
            "conversation_future": {
                "count": future_count,
                "matched_count": matched_count,
                "modified_count": modified_count,
            },
            "reminders": {
                "exists": reminders_exists,
                "document_count": reminder_count,
                "archive_collection_name": archived_name,
                "archived": archived,
            },
        }
    finally:
        client.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Report legacy reminder compatibility data in MongoDB. "
            "Dry-run is the default; pass --execute to unset "
            "`conversation_info.future` and archive the `reminders` collection."
        )
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply the cleanup instead of reporting only.",
    )
    parser.add_argument(
        "--mongo-uri",
        default=default_mongo_uri(),
        help="MongoDB connection URI. Defaults to the repo config.",
    )
    parser.add_argument(
        "--db-name",
        default=default_db_name(),
        help="MongoDB database name. Defaults to the repo config.",
    )
    parser.add_argument(
        "--report-path",
        help="Optional file path to write the JSON report.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    report = retire_legacy_reminder_compat(
        mongo_uri=args.mongo_uri,
        db_name=args.db_name,
        execute=args.execute,
    )

    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)

    if args.report_path:
        Path(args.report_path).write_text(rendered + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
