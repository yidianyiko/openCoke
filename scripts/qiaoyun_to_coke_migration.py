#!/usr/bin/env python3
"""Rename the live qiaoyun character document to coke and delete the empty coke stub."""

from __future__ import annotations

import argparse
from typing import Any

from dao.user_dao import UserDAO


DEPENDENCY_QUERIES = {
    "relations": lambda coke_id: {"cid": coke_id},
    "inputmessages": lambda coke_id: {"to_user": coke_id},
    "outputmessages": lambda coke_id: {"from_user": coke_id},
    "reminders": lambda coke_id: {"character_id": coke_id},
    "conversations": lambda coke_id: {
        "$or": [
            {"conversation_info.chat_history.from_user": coke_id},
            {"conversation_info.chat_history.to_user": coke_id},
        ]
    },
}


def _stringify_id(document: dict[str, Any]) -> str:
    return str(document["_id"])


def _count_dependencies(db, coke_id: str) -> dict[str, int]:
    counts = {}
    for collection_name, build_query in DEPENDENCY_QUERIES.items():
        counts[collection_name] = db[collection_name].count_documents(
            build_query(coke_id)
        )
    return counts


def build_migration_plan(qiaoyun: dict[str, Any], coke: dict[str, Any], db) -> dict:
    qiaoyun_id = _stringify_id(qiaoyun)
    coke_id = _stringify_id(coke)
    dependency_counts = _count_dependencies(db, coke_id)

    if any(dependency_counts.values()):
        raise RuntimeError(
            "legacy coke character is not empty: "
            + ", ".join(
                f"{collection}={count}"
                for collection, count in dependency_counts.items()
                if count
            )
        )

    qiaoyun_wechat = qiaoyun.get("platforms", {}).get("wechat", {}).get("id")
    coke_wechat = coke.get("platforms", {}).get("wechat", {}).get("id")
    if qiaoyun_wechat and coke_wechat and qiaoyun_wechat != coke_wechat:
        raise RuntimeError("qiaoyun and coke do not share the same wechat id")

    return {
        "target_character_id": qiaoyun_id,
        "legacy_character_id": coke_id,
        "dependency_counts": dependency_counts,
        "rename_update": {
            "$set": {
                "name": "coke",
                "platforms.wechat.nickname": "coke",
            }
        },
    }


def execute_migration_plan(plan: dict[str, Any], db) -> None:
    from bson import ObjectId

    users = db["users"]
    users.update_one(
        {"_id": ObjectId(plan["target_character_id"])},
        plan["rename_update"],
    )
    users.delete_one({"_id": ObjectId(plan["legacy_character_id"])})


def _find_character(user_dao: UserDAO, name: str) -> dict[str, Any]:
    characters = user_dao.find_characters({"name": name}, limit=2)
    if len(characters) != 1:
        raise RuntimeError(f"expected exactly one character named {name}")
    return characters[0]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare or execute the qiaoyun -> coke character migration."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="apply the migration; default is dry-run",
    )
    args = parser.parse_args()

    user_dao = UserDAO()
    try:
        qiaoyun = _find_character(user_dao, "qiaoyun")
        coke = _find_character(user_dao, "coke")
        plan = build_migration_plan(qiaoyun, coke, user_dao.db)

        print("qiaoyun -> coke migration plan")
        print(f"target_character_id={plan['target_character_id']}")
        print(f"legacy_character_id={plan['legacy_character_id']}")
        print(f"dependency_counts={plan['dependency_counts']}")

        if not args.execute:
            print("dry-run only; rerun with --execute to apply")
            return 0

        execute_migration_plan(plan, user_dao.db)
        print("migration applied")
        print("next steps: update conf/config.json on the server before restart")
        return 0
    finally:
        user_dao.close()


if __name__ == "__main__":
    raise SystemExit(main())
