"""Чтение и запись локальных данных.

Файлы:
    vault.txt   - зашифрованное хранилище (текстовый файл).
    config.json - настройки программы (адрес WebDAV, логин, пароль сервера).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from . import crypto
from .crypto import CryptoError
from .models import Vault

BASE_DIR = Path(__file__).resolve().parent.parent
VAULT_FILE = BASE_DIR / "vault.txt"
CONFIG_FILE = BASE_DIR / "config.json"
REMOTE_FILENAME = "vault.txt"

DEFAULT_CONFIG: dict[str, Any] = {
    "webdav_url": "https://lebidko-krd2.netcraze.pro/webdav/PassManager",
    "webdav_login": "",
    "webdav_password_enc": "",
    "autosync": True,
    "pending_reencrypt": False,
}


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=path.suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


# --------------------------------------------------------------------------
# Хранилище паролей
# --------------------------------------------------------------------------

def vault_exists(path: Path | None = None) -> bool:
    path = path or VAULT_FILE
    return path.exists() and path.stat().st_size > 0


def save_vault(vault: Vault, key: bytes, salt: bytes,
               iterations: int = crypto.KDF_ITERATIONS,
               path: Path | None = None) -> None:
    path = path or VAULT_FILE
    plaintext = json.dumps(vault.to_dict(), ensure_ascii=False).encode("utf-8")
    text = crypto.encrypt_bytes(key, plaintext, salt, iterations)
    _atomic_write(path, text)


def load_vault(password: str, path: Path | None = None) -> tuple[Vault, bytes, bytes, int]:
    """Расшифровывает локальный файл.

    Возвращает ``(vault, key, salt, iterations)``.
    """
    path = path or VAULT_FILE
    text = path.read_text(encoding="utf-8")
    plaintext, salt, iterations = crypto.decrypt_text(password, text)
    key = crypto.derive_key(password, salt, iterations)
    data = json.loads(plaintext.decode("utf-8"))
    return Vault.from_dict(data), key, salt, iterations


def decrypt_vault_text(password: str, text: str) -> Vault:
    plaintext, _salt, _iters = crypto.decrypt_text(password, text)
    return Vault.from_dict(json.loads(plaintext.decode("utf-8")))


# --------------------------------------------------------------------------
# Настройки
# --------------------------------------------------------------------------

def load_config(path: Path | None = None) -> dict[str, Any]:
    path = path or CONFIG_FILE
    config = dict(DEFAULT_CONFIG)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                config.update(data)
        except (ValueError, OSError):
            pass
    return config


def save_config(config: dict[str, Any], path: Path | None = None) -> None:
    path = path or CONFIG_FILE
    merged = dict(DEFAULT_CONFIG)
    merged.update(config)
    _atomic_write(path, json.dumps(merged, ensure_ascii=False, indent=2))


def encrypt_server_password(config: dict[str, Any], key: bytes) -> dict[str, Any]:
    """Шифрует пароль WebDAV мастер-ключом для хранения в config.json."""
    password = config.get("webdav_password", "")
    result = dict(config)
    result.pop("webdav_password", None)
    if key and password:
        # Используем префикс-соль на основе мастер-ключа: переиспользуем
        # AES-GCM напрямую, без собственного KDF.
        import base64
        import os as _os

        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        nonce = _os.urandom(12)
        ct = AESGCM(key).encrypt(nonce, password.encode("utf-8"), None)
        result["webdav_password_enc"] = base64.b64encode(nonce + ct).decode("ascii")
    elif not password:
        result["webdav_password_enc"] = ""
    return result


def decrypt_server_password(config: dict[str, Any], key: bytes) -> str:
    enc = config.get("webdav_password_enc", "")
    if not enc or not key:
        return ""
    import base64

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    try:
        raw = base64.b64decode(enc)
        nonce, ct = raw[:12], raw[12:]
        return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")
    except Exception:
        return ""


__all__ = [
    "BASE_DIR", "VAULT_FILE", "CONFIG_FILE", "REMOTE_FILENAME",
    "DEFAULT_CONFIG", "vault_exists", "save_vault", "load_vault",
    "decrypt_vault_text", "load_config", "save_config",
    "encrypt_server_password", "decrypt_server_password", "CryptoError",
]
