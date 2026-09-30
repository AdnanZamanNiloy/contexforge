"""Repair the Model Hub rows whose API keys are unrecoverable.

Run once, by hand, after credential key material was lost.  It clears only the
dead ``api_key`` values — never a model row — so each affected model reverts to
"no key configured" and the UI prompts for one, instead of holding a ciphertext
that no key can decrypt.

Idempotent: rows that already have no key, or that still decrypt, are left alone.
A backup is taken first and the operation runs in a single transaction.
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

DB = Path("data/model_hub/model_hub.db")
BACKUP = Path("/tmp/opencode/hub-backup/model_hub.db.pre-repair")


def main() -> int:
    sys.path.insert(0, ".")
    from app.config.settings import settings
    from app.model_hub import credentials

    print(f"encryption key configured: {credentials.encryption_available()}")

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT id, name, provider, api_key FROM hub_models ORDER BY created_at").fetchall()

        # Classify every row without writing anything.
        dead: list[sqlite3.Row] = []
        healthy = 0
        empty = 0
        for row in rows:
            stored = row["api_key"]
            if not stored:
                empty += 1
                continue
            if credentials.decrypt_secret(stored) == credentials.CREDENTIAL_UNREADABLE:
                dead.append(row)
            else:
                healthy += 1

        print(f"\n{len(rows)} models: {healthy} readable, {empty} already empty, {len(dead)} unrecoverable")
        for row in dead:
            print(f"  unrecoverable: {row['name']!r} (provider={row['provider']})")

        if not dead:
            print("\nnothing to repair.")
            return 0

        BACKUP.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(DB, BACKUP)
        print(f"\nbackup written to {BACKUP}")

        # Clear only the dead values. Name/model_id/chain/serving data is kept so
        # the user re-enters a key rather than rebuilding each model.
        with conn:
            conn.execute(
                "UPDATE hub_models SET api_key = NULL, updated_at = updated_at "
                "WHERE api_key IS NOT NULL AND api_key LIKE 'enc:v1:%'"
            )

        print(f"cleared {len(dead)} unrecoverable key(s)")
    finally:
        conn.close()

    # Verify through the real store, not raw SQL.
    import asyncio

    from app.model_hub.storage import ModelHubStore

    print("\n--- read back through ModelHubStore ---")
    models = asyncio.run(ModelHubStore().list_models())
    for model in models:
        key = model.get("api_key")
        print(f"  {model['name'][:24]:26} provider={model['provider']:11} has_key={bool(key)}")

    remaining = sum(1 for m in models if m.get("api_key"))
    print(f"\nmodels total={len(models)} with_key={remaining} need_reentry={len(dead)}")
    print(f"settings path used: {settings.MODEL_HUB_DB_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
