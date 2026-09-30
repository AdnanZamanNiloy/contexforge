"""Tests for Model Hub credential encryption at rest.

Every other secret in ContextForge arrives through the environment and is never
written down.  The Model Hub is the exception: the user types provider keys into
the UI and they land in SQLite, which makes ``hub_models`` the one table holding
live credentials on disk.

These tests pin the behaviour that matters for an existing install: encryption is
opt-in, plaintext rows keep working, a wrong key degrades to "unreadable" rather
than to a wrong value, and the key never reaches an API response.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.config import settings as settings_module
from app.model_hub import credentials
from app.model_hub.credentials import (
    CREDENTIAL_UNREADABLE,
    decrypt_secret,
    encrypt_secret,
    encryption_available,
    is_encrypted,
    redact,
)
from app.model_hub.storage import ModelHubStore

SECRET = "sk-live-abcdef0123456789"


@pytest.fixture
def key(monkeypatch):
    """Enable encryption with a throwaway key for the duration of a test."""
    value = Fernet.generate_key().decode()
    monkeypatch.setattr(settings_module.settings, "CREDENTIAL_ENCRYPTION_KEY", value)
    monkeypatch.setattr(credentials, "_warned", False)
    return value


@pytest.fixture
def no_key(monkeypatch):
    monkeypatch.setattr(settings_module.settings, "CREDENTIAL_ENCRYPTION_KEY", "")
    monkeypatch.setattr(credentials, "_warned", False)
    return None


class TestRoundTrip:
    def test_round_trips_a_secret(self, key):
        stored = encrypt_secret(SECRET)

        assert stored != SECRET
        assert is_encrypted(stored)
        assert decrypt_secret(stored) == SECRET

    def test_two_encryptions_differ(self, key):
        # Fresh nonce per call, so identical keys do not produce identical rows.
        assert encrypt_secret(SECRET) != encrypt_secret(SECRET)

    def test_does_not_double_encrypt(self, key):
        once = encrypt_secret(SECRET)

        assert encrypt_secret(once) == once
        assert decrypt_secret(decrypt_secret(once)) == SECRET

    def test_preserves_empty_and_none(self, key):
        assert encrypt_secret("") == ""
        assert encrypt_secret(None) is None
        assert decrypt_secret("") == ""
        assert decrypt_secret(None) is None


class TestWithoutAnEncryptionKey:
    def test_reports_unavailable(self, no_key):
        assert encryption_available() is False

    def test_stores_plaintext_rather_than_failing(self, no_key):
        # The app must keep working for anyone who upgrades without setting a
        # key; refusing to start would lock them out of a working install.
        assert encrypt_secret(SECRET) == SECRET
        assert decrypt_secret(SECRET) == SECRET

    def test_warns_once(self, no_key, caplog):
        with caplog.at_level("WARNING"):
            credentials.warn_once_if_unencrypted()
            credentials.warn_once_if_unencrypted()

        assert sum("CREDENTIAL_ENCRYPTION_KEY is not set" in r.message for r in caplog.records) == 1

    def test_does_not_warn_when_a_key_is_configured(self, key, caplog):
        with caplog.at_level("WARNING"):
            credentials.warn_once_if_unencrypted()

        assert not [r for r in caplog.records if "CREDENTIAL_ENCRYPTION_KEY is not set" in r.message]


class TestUpgradePath:
    def test_a_plaintext_row_still_decrypts(self, key):
        # A database written before the key was configured holds plaintext.
        assert decrypt_secret(SECRET) == SECRET
        assert is_encrypted(SECRET) is False

    def test_a_mixed_database_is_read_row_by_row(self, key):
        legacy = decrypt_secret("written-before-encryption")
        current = decrypt_secret(encrypt_secret("written-after"))

        assert legacy == "written-before-encryption"
        assert current == "written-after"

    def test_an_ignored_key_falls_back_to_plaintext(self, monkeypatch):
        # A malformed key must not break the store.
        monkeypatch.setattr(settings_module.settings, "CREDENTIAL_ENCRYPTION_KEY", "not-a-fernet-key")

        assert encrypt_secret(SECRET) == SECRET
        assert encryption_available() is True


class TestUnreadableCredential:
    def test_a_wrong_key_yields_the_sentinel(self, monkeypatch):
        monkeypatch.setattr(
            settings_module.settings,
            "CREDENTIAL_ENCRYPTION_KEY",
            Fernet.generate_key().decode(),
        )
        stored = encrypt_secret(SECRET)

        monkeypatch.setattr(
            settings_module.settings,
            "CREDENTIAL_ENCRYPTION_KEY",
            Fernet.generate_key().decode(),
        )

        assert decrypt_secret(stored) == CREDENTIAL_UNREADABLE

    def test_no_key_for_a_ciphertext_yields_the_sentinel(self, monkeypatch):
        # Encrypt while a key is configured, then remove it — as would happen if
        # the environment lost CREDENTIAL_ENCRYPTION_KEY between restarts.
        monkeypatch.setattr(
            settings_module.settings,
            "CREDENTIAL_ENCRYPTION_KEY",
            Fernet.generate_key().decode(),
        )
        stored = encrypt_secret(SECRET)
        monkeypatch.setattr(settings_module.settings, "CREDENTIAL_ENCRYPTION_KEY", "")

        assert decrypt_secret(stored) == CREDENTIAL_UNREADABLE

    def test_a_tampered_ciphertext_yields_the_sentinel(self, key):
        stored = encrypt_secret(SECRET)
        tampered = stored[:-4] + ("AAAA" if not stored.endswith("AAAA") else "BBBB")

        assert decrypt_secret(tampered) == CREDENTIAL_UNREADABLE


class TestRedaction:
    def test_never_returns_the_secret(self, key):
        assert SECRET not in redact(SECRET)

    def test_hides_short_values_entirely(self, key):
        # A four-character key is still a secret; a prefix would leak most of it.
        assert redact("abcd") == "***"

    def test_passes_the_sentinel_through(self):
        assert redact(CREDENTIAL_UNREADABLE) == CREDENTIAL_UNREADABLE

    def test_handles_empty(self):
        assert redact("") is None
        assert redact(None) is None


class TestStoreEncryption:
    def _raw_key(self, store, model_id):
        """Read the api_key column straight from SQLite, bypassing the store."""
        conn = store._connect()
        try:
            row = conn.execute("SELECT api_key FROM hub_models WHERE id = ?", (model_id,)).fetchone()
            return row["api_key"] if row else None
        finally:
            conn.close()

    def _make_model(self, store, **overrides):
        import asyncio

        fields = {
            "name": "Primary",
            "model_type": "llm",
            "runtime": "api",
            "provider": "groq",
            "model_id": "llama-3.3-70b",
            "api_key": SECRET,
            **overrides,
        }
        return asyncio.run(store.create_model(fields))

    def test_the_column_holds_a_ciphertext_when_a_key_is_set(self, key, tmp_path):
        store = ModelHubStore(db_path=tmp_path / "hub.db")
        created = self._make_model(store)

        stored = self._raw_key(store, created["id"])
        assert stored != SECRET
        assert is_encrypted(stored)

    def test_the_column_holds_plaintext_without_a_key(self, no_key, tmp_path):
        store = ModelHubStore(db_path=tmp_path / "hub.db")
        created = self._make_model(store)

        assert self._raw_key(store, created["id"]) == SECRET

    def test_reads_return_the_plaintext_secret(self, key, tmp_path):
        import asyncio

        store = ModelHubStore(db_path=tmp_path / "hub.db")
        created = self._make_model(store)

        listed = asyncio.run(store.list_models())
        assert listed[0]["api_key"] == SECRET
        assert asyncio.run(store.get_model(created["id"]))["api_key"] == SECRET

    def test_an_update_round_trips(self, key, tmp_path):
        import asyncio

        store = ModelHubStore(db_path=tmp_path / "hub.db")
        created = self._make_model(store)

        asyncio.run(store.update_model(created["id"], {"api_key": "sk-replaced-9876543210"}))

        assert asyncio.run(store.get_model(created["id"]))["api_key"] == "sk-replaced-9876543210"
        assert is_encrypted(self._raw_key(store, created["id"]))

    def test_updating_another_field_leaves_the_key_encrypted_and_readable(self, key, tmp_path):
        import asyncio

        store = ModelHubStore(db_path=tmp_path / "hub.db")
        created = self._make_model(store)

        asyncio.run(store.update_model(created["id"], {"name": "Renamed"}))

        row = asyncio.run(store.get_model(created["id"]))
        assert row["name"] == "Renamed"
        assert row["api_key"] == SECRET
        assert is_encrypted(self._raw_key(store, created["id"]))

    def test_a_legacy_row_written_before_the_key_is_still_readable(self, key, tmp_path):
        import asyncio

        store = ModelHubStore(db_path=tmp_path / "hub.db")
        created = self._make_model(store)
        # Simulate the pre-upgrade state.
        conn = store._connect()
        try:
            with conn:
                conn.execute("UPDATE hub_models SET api_key = ? WHERE id = ?", (SECRET, created["id"]))
        finally:
            conn.close()

        assert asyncio.run(store.get_model(created["id"]))["api_key"] == SECRET

    def test_deleting_a_model_removes_its_key(self, key, tmp_path):
        import asyncio

        store = ModelHubStore(db_path=tmp_path / "hub.db")
        created = self._make_model(store)

        asyncio.run(store.delete_model(created["id"]))

        assert self._raw_key(store, created["id"]) is None


class TestSuiteIsolation:
    """Guards that keep the credential tests away from real data.

    The encryption tests were first verified by hand against the live database,
    which encrypted real API keys with a throwaway key and made them
    unrecoverable.  These tests make that failure mode impossible to repeat: the
    autouse ``isolate_storage`` fixture already redirects every store path to
    ``tmp_path``, and this class proves it rather than assuming it.
    """

    def test_the_hub_store_path_points_at_tmp_path(self, tmp_path):
        from app.config.settings import settings

        assert tmp_path / "model_hub" / "model_hub.db" == settings.MODEL_HUB_DB_PATH

    def test_no_encryption_key_is_inherited_from_the_environment(self):
        from app.config.settings import settings

        # Inherited rather than generated: a test must never encrypt with the
        # key that protects real credentials.
        assert settings.CREDENTIAL_ENCRYPTION_KEY == ""

    def test_the_store_defaults_to_the_isolated_path(self, tmp_path):
        from app.config.settings import settings
        from app.model_hub.storage import ModelHubStore

        store = ModelHubStore()

        assert store._db_path == settings.MODEL_HUB_DB_PATH
        assert str(tmp_path) in str(store._db_path)

    def test_no_test_writes_to_the_developer_database(self, tmp_path):
        from app.config.settings import settings

        # The real database lives outside tmp_path; a store built with no
        # explicit db_path must not be one of them.
        assert str(settings.MODEL_HUB_DB_PATH).startswith(str(tmp_path))
