from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

import sqlalchemy as sa

from coke import schema
from coke.domains.identity_access.passwords import PasswordHasher


@dataclass(frozen=True)
class CredentialTarget:
    account_id: str
    email: str
    password: str


@dataclass(frozen=True)
class MigrationResult:
    updated: int
    skipped: int
    missing: list[str]


TARGET_CREDENTIALS = (
    CredentialTarget(
        account_id="ae02ff016fcd4d39a189e51c8c8a31e6",
        email="olivers@coke.keep4oforever.com",
        password="CokeTest-Olivers-2026!",
    ),
    CredentialTarget(
        account_id="635d3bdc1b024a08acf49940b91a9de5",
        email="lizihao@coke.keep4oforever.com",
        password="CokeTest-Lizihao-2026!",
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
    missing: list[str] = []

    for target in targets:
        row = conn.execute(
            sa.select(
                schema.credential.c.email,
                schema.credential.c.password_hash,
            ).where(
                schema.credential.c.account_id == target.account_id,
                sa.func.lower(schema.credential.c.email) == target.email.lower(),
            )
        ).mappings().one_or_none()
        if row is None:
            missing.append(target.account_id)
            continue
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

    return MigrationResult(updated=updated, skipped=skipped, missing=missing)


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
        f"updated={result.updated} skipped={result.skipped} missing={','.join(result.missing) or '-'}"
    )
    return 0 if not result.missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
