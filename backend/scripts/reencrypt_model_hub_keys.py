"""Re-encrypt Model Hub keys that are still stored in plaintext.

Rows written before the backend loaded the encryption code hold a plaintext
``api_key``.  The read path handles them, so the app works, but the column is not
actually protected until each key is saved again through the API.

This migrates them in place using the configured ``CREDENTIAL_ENCRYPTION_KEY``:
one pass reads the plaintext, re-writes it through the store's encrypting write
path, then confirms every row reads back correctly.

Safe to re-run — rows that are already ciphertext are left untouched.
"""

from __future__ import annotations

import asyncio
import shutil
import sqlite3
import sys
from pathlib import Path

BACKUP = Path("/tmp/opencode/hub-backup/model_hub.db.pre-reencrypt")


def main() -> int:
    sys.path.insert(0, ".")
    from app.config.settings import settings
    from app.model_hub import credentials
    from app.model_hub.schemas import ModelUpdate
    from app.model_hub.service import ModelHubService
    from app.model_hub.storage import ModelHubStore

    db = Path(settings.MODEL_HUB_DB_PATH)
    if not credentials.encryption_available():
        print("REFUSING: CREDENTIAL_ENCRYPTION_KEY is not configured, so anything")
        print("written now would be plaintext again and this run would be a no-op.")
        return 1

    print(f"db                 : {db}")
    print("encryption available: True")

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, name, api_key FROM hub_models WHERE api_key IS NOT NULL AND api_key != ''"
    ).fetchall()

    plaintext = [r for r in rows if not credentials.is_encrypted(r["api_key"])]
    already = [r for r in rows if credentials.is_encrypted(r["api_key"])]

    print(f"\n{len(rows)} models with a key: {len(plaintext)} plaintext, {len(already)} ciphertext")
    for row in plaintext:
        print(f"  plaintext: {row['name']!r}")

    if not plaintext:
        print("\nnothing to migrate.")
        conn.close()
        return 0

    # Read the plaintext BEFORE opening a second writer, then close.
    pending = {r["id"]: credentials.decrypt_secret(r["api_key"]) for r in plaintext}
    conn.close()

    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db, BACKUP)
    print(f"\nbackup written to {BACKUP}")

    service = ModelHubService(store=ModelHubStore(db_path=db))
    for model_id, secret in pending.items():
        asyncio.run(service.update_model(model_id, ModelUpdate(api_key=secret)))
    print(f"re-wrote {len(pending)} key(s) through the encrypting write path")

    # Verify: every row is now ciphertext and every row still decrypts.
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    check_rows = conn.execute(
        "SELECT name, api_key FROM hub_models WHERE api_key IS NOT NULL AND api_key != ''"
    ).fetchall()
    conn.close()

    print("\n--- after migration ---")
    failures = []
    for row in check_rows:
        encrypted = credentials.is_encrypted(row["api_key"])
        if not encrypted:
            failures.append(f"{row['name']}: still plaintext")
            print(f"  STILL PLAINTEXT  {row['name']!r}")
            continue
        secret = credentials.decrypt_secret(row["api_key"])
        if secret == credentials.CREDENTIAL_UNREADABLE:
            failures.append(f"{row['name']}: undecryptable")
            print(f"  UNREADABLE       {row['name']!r}")
        else:
            print(f"  encrypted+readable  {row['name']!r}")

    print(f"\n{'FAILURES: ' + '; '.join(failures) if failures else 'all keys encrypted and readable'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
