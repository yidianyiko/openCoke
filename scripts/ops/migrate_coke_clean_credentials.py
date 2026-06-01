from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa

from coke import schema
from coke.domains.identity_access.passwords import PasswordHasher


@dataclass(frozen=True)
class CredentialTarget:
    account_id: str
    email: str
    password: str
    display_name: str


@dataclass(frozen=True)
class MigrationResult:
    updated: int
    skipped: int
    profiles_created: int
    profiles_skipped: int
    missing: list[str]


TARGET_CREDENTIALS = (
    CredentialTarget(
        account_id="ae02ff016fcd4d39a189e51c8c8a31e6",
        email="olivers@coke.keep4oforever.com",
        password="CokeTest-Olivers-2026!",
        display_name="olivers",
    ),
    CredentialTarget(
        account_id="635d3bdc1b024a08acf49940b91a9de5",
        email="lizihao@coke.keep4oforever.com",
        password="CokeTest-Lizihao-2026!",
        display_name="lizihao",
    ),
)


def migrate_credentials(
    conn: sa.Connection,
    *,
    targets: Sequence[CredentialTarget] = TARGET_CREDENTIALS,
    hasher: PasswordHasher | None = None,
    dry_run: bool = False,
) -> MigrationResult:
    password_hasher = hasher or PasswordHasher()
    updated = 0
    skipped = 0
    profiles_created = 0
    profiles_skipped = 0
    missing: list[str] = []

    for target in targets:
        row = (
            conn.execute(
                sa.select(
                    schema.credential.c.email,
                    schema.credential.c.password_hash,
                ).where(
                    schema.credential.c.account_id == target.account_id,
                    sa.func.lower(schema.credential.c.email) == target.email.lower(),
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            missing.append(target.account_id)
            continue

        profile = (
            conn.execute(
                sa.select(schema.user_profile.c.id).where(
                    schema.user_profile.c.account_id == target.account_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if profile is None:
            profiles_created += 1
            if not dry_run:
                now = datetime.now(timezone.utc)
                conn.execute(
                    schema.user_profile.insert().values(
                        id=_stable_user_profile_id(target.account_id),
                        account_id=target.account_id,
                        real_name=None,
                        nickname=target.display_name,
                        description=None,
                        relationship_description=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
        else:
            profiles_skipped += 1

        if password_hasher.verify(row["password_hash"], target.password):
            skipped += 1
            continue

        updated += 1
        if dry_run:
            continue

        conn.execute(
            schema.credential.update()
            .where(
                schema.credential.c.account_id == target.account_id,
                sa.func.lower(schema.credential.c.email) == target.email.lower(),
            )
            .values(
                password_hash=password_hasher.hash(target.password),
                updated_at=datetime.now(timezone.utc),
            )
        )

    return MigrationResult(
        updated=updated,
        skipped=skipped,
        profiles_created=profiles_created,
        profiles_skipped=profiles_skipped,
        missing=missing,
    )


def _stable_user_profile_id(account_id: str) -> str:
    return uuid5(NAMESPACE_URL, f"coke-clean:user-profile:{account_id}").hex


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate the two coke-clean live credentials to Argon2 in place."
    )
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("DATABASE_URL is required")

    engine = sa.create_engine(args.database_url)
    with engine.begin() as conn:
        result = migrate_credentials(conn, dry_run=args.dry_run)

    print(
        "credential_migration "
        f"updated={result.updated} skipped={result.skipped} "
        f"profiles_created={result.profiles_created} "
        f"profiles_skipped={result.profiles_skipped} "
        f"missing={','.join(result.missing) or '-'}"
    )
    return 0 if not result.missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
