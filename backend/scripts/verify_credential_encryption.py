"""Prove the encrypted read/write path against an isolated temp database.

Deliberately does NOT touch backend/data/.  Everything runs under ``--base-dir``,
which the caller points at a temporary directory, using throwaway key material.
"""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-dir",
        required=True,
        help="Directory to run in. Must NOT be the live backend/ directory.",
    )
    args = parser.parse_args()

    base = Path(args.base_dir).resolve()
    live = Path(__file__).resolve().parents[1] / "data" / "model_hub" / "model_hub.db"
    if base == live.parent or live.is_relative_to(base):
        print(f"REFUSING to run against the live database at {live}")
        return 1

    # Import from the app, but point every store path at the temp directory.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from cryptography.fernet import Fernet

    from app.config.settings import settings
    from app.model_hub import credentials
    from app.model_hub.schemas import ModelCreate, ModelUpdate
    from app.model_hub.service import ModelHubService
    from app.model_hub.storage import ModelHubStore

    db = base / "model_hub" / "model_hub.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    settings.MODEL_HUB_DB_PATH = db

    # A fresh key, distinct from anything real.
    settings.CREDENTIAL_ENCRYPTION_KEY = Fernet.generate_key().decode()
    print(f"isolated db : {db}")
    print(f"encryption  : available={credentials.encryption_available()}")
    print(f"live db     : {live}  (untouched)\n")

    service = ModelHubService(store=ModelHubStore(db_path=db))
    failures: list[str] = []

    def check(label: str, ok: bool) -> None:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
        if not ok:
            failures.append(label)

    secret = "sk-verify-0123456789abcdef"

    print("--- write then read with the configured key ---")
    created = asyncio.run(
        service.create_model(
            ModelCreate(
                name="Verify model",
                model_type="llm",
                runtime="api",
                provider="groq",
                model_id="llama-3.3-70b",
                api_key=secret,
            )
        )
    )
    check("response exposes has_api_key, never the secret", created["has_api_key"] is True)
    check("response does not contain the secret", secret not in str(created))

    raw = sqlite3.connect(db).execute("SELECT api_key FROM hub_models WHERE id = ?", (created["id"],)).fetchone()[0]
    check("column holds a ciphertext, not the secret", raw != secret)
    check("ciphertext is tagged", credentials.is_encrypted(raw))
    check("ciphertext does not contain the secret", secret not in raw)

    fetched = asyncio.run(service.get_model(created["id"]))
    check("read path decrypts back to the secret", fetched["has_api_key"] is True)

    print("\n--- update and re-read ---")
    replacement = "sk-verify-replaced-9876543210"
    asyncio.run(service.update_model(created["id"], ModelUpdate(api_key=replacement)))
    raw2 = sqlite3.connect(db).execute("SELECT api_key FROM hub_models WHERE id = ?", (created["id"],)).fetchone()[0]
    check("replacement is stored encrypted", credentials.is_encrypted(raw2))
    check("replacement ciphertext differs from the first", raw2 != raw)
    fetched2 = asyncio.run(service.get_model(created["id"]))
    check("replacement decrypts", fetched2["has_api_key"] is True)

    print("\n--- updating an unrelated field keeps the key ---")
    asyncio.run(service.update_model(created["id"], ModelUpdate(name="Renamed")))
    fetched3 = asyncio.run(service.get_model(created["id"]))
    check("name updated", fetched3["name"] == "Renamed")
    check("key still readable", fetched3["has_api_key"] is True)

    print("\n--- clearing a key ---")
    asyncio.run(service.update_model(created["id"], ModelUpdate(api_key="")))
    fetched4 = asyncio.run(service.get_model(created["id"]))
    check("cleared key reports has_api_key False", fetched4["has_api_key"] is False)

    print("\n--- a fresh store instance reads the same data ---")
    reopened = ModelHubStore(db_path=db)
    listed = asyncio.run(reopened.list_models())
    check("model survives a store reopen", len(listed) == 1)
    check("name persists across reopen", listed[0]["name"] == "Renamed")

    print(f"\n{'FAILURES: ' + ', '.join(failures) if failures else 'all checks passed'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
