"""Garmin session per user with encrypted token cache and retry-once auth."""

from __future__ import annotations

import base64
import logging
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from garminconnect import Garmin, GarminConnectAuthenticationError

logger = logging.getLogger(__name__)


def _salt(user_name: str) -> bytes:
    import hashlib

    return hashlib.sha256(f"garmin-mcp:{user_name}".encode()).digest()[:16]


def _derive_key(secret: str, user_name: str) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_salt(user_name),
        iterations=390000,
    )
    return base64.urlsafe_b64encode(kdf.derive(secret.encode("utf-8")))


class EncryptedTokenStore:
    def __init__(self, path: str, encryption_secret: str, user_name: str) -> None:
        self.path = Path(path)
        self._fernet = Fernet(_derive_key(encryption_secret, user_name))

    def load_string(self) -> str | None:
        if not self.path.exists():
            return None
        raw = self.path.read_bytes()
        try:
            dec = self._fernet.decrypt(raw)
            return dec.decode("utf-8")
        except (InvalidToken, UnicodeDecodeError) as e:
            logger.warning("Token cache decrypt failed: %s", e)
            return None

    def save_string(self, token_str: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._fernet.encrypt(token_str.encode("utf-8"))
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_bytes(payload)
        tmp.replace(self.path)


class GarminAuthManager:
    """Per-user Garmin client with encrypted garth token string on disk."""

    def __init__(self, email: str, password: str, token_path: str, encryption_secret: str, user_name: str) -> None:
        self.email = email
        self.password = password
        self.user_name = user_name
        self._store = EncryptedTokenStore(token_path, encryption_secret, user_name)
        self._client: Garmin | None = None

    def get_client(self) -> Garmin:
        if self._client is not None:
            return self._client
        self._client = self._login_with_retry()
        return self._client

    def _invalidate_cache(self) -> None:
        try:
            if self._store.path.exists():
                self._store.path.unlink()
        except OSError:
            pass

    def _login_with_retry(self) -> Garmin:
        token_str = self._store.load_string()
        client = Garmin(self.email, self.password)
        try:
            if token_str and len(token_str) > 10:
                try:
                    client.login(tokenstore=token_str)
                    logger.info("Garmin token reuse user=%s", self.user_name)
                    return client
                except GarminConnectAuthenticationError:
                    logger.warning("Stored token rejected user=%s; re-login", self.user_name)
                    self._invalidate_cache()
            client.login()
            self._persist(client)
            logger.info("Garmin fresh login user=%s", self.user_name)
            return client
        except GarminConnectAuthenticationError:
            self._invalidate_cache()
            client2 = Garmin(self.email, self.password)
            client2.login()
            self._persist(client2)
            logger.info("Garmin login after retry user=%s", self.user_name)
            return client2

    def _persist(self, client: Garmin) -> None:
        try:
            s = client.garth.dumps()
            self._store.save_string(s)
        except Exception as e:
            logger.error("Could not persist Garmin tokens user=%s: %s", self.user_name, e)

    def call_with_retry(self, fn, *args, **kwargs):
        """Call Garmin API method; on auth error invalidate and retry once."""
        try:
            return fn(self.get_client(), *args, **kwargs)
        except GarminConnectAuthenticationError:
            logger.warning("API auth error user=%s; invalidate and retry once", self.user_name)
            self._invalidate_cache()
            self._client = None
            return fn(self.get_client(), *args, **kwargs)

    def close(self) -> None:
        self._client = None
