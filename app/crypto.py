"""Шифрование хранилища.

Ключ выводится из мастер-пароля с помощью PBKDF2-HMAC-SHA256.
Сам файл хранилища шифруется целиком алгоритмом AES-256-GCM.

Формат файла (JSON, обёрнутый в base64-строку)::

    {
        "format": "PassManagerVault",
        "version": 1,
        "kdf": {"name": "pbkdf2-sha256", "salt": "<base64>", "iterations": 200000},
        "cipher": {"name": "AES-256-GCM", "nonce": "<base64>"},
        "data": "<base64 ciphertext+tag>"
    }
"""

from __future__ import annotations

import base64
import json
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

FORMAT_NAME = "PassManagerVault"
FORMAT_VERSION = 1
KDF_ITERATIONS = 200_000
SALT_BYTES = 16
NONCE_BYTES = 12
KEY_BYTES = 32


class CryptoError(Exception):
    """Ошибка шифрования/расшифровки."""


class WrongPasswordError(CryptoError):
    """Неверный мастер-пароль."""


def _b64e(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def derive_key(password: str, salt: bytes, iterations: int = KDF_ITERATIONS) -> bytes:
    """Выводит 32-байтный ключ из мастер-пароля."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_BYTES,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(password.encode("utf-8"))


def new_salt() -> bytes:
    return os.urandom(SALT_BYTES)


def encrypt_bytes(key: bytes, plaintext: bytes, salt: bytes,
                  iterations: int = KDF_ITERATIONS) -> str:
    """Шифрует данные и возвращает готовую текстовую строку файла."""
    nonce = os.urandom(NONCE_BYTES)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    envelope = {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "kdf": {
            "name": "pbkdf2-sha256",
            "salt": _b64e(salt),
            "iterations": iterations,
        },
        "cipher": {
            "name": "AES-256-GCM",
            "nonce": _b64e(nonce),
        },
        "data": _b64e(ciphertext),
    }
    return json.dumps(envelope, ensure_ascii=False, indent=2)


def decrypt_text(password: str, text: str) -> tuple[bytes, bytes, int]:
    """Расшифровывает текстовое содержимое файла.

    Возвращает ``(plaintext, salt, iterations)``, чтобы вызывающий код мог
    повторно использовать те же параметры при следующем сохранении.
    """
    try:
        envelope = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise CryptoError("Файл хранилища повреждён: не удаётся разобрать формат.") from exc

    if not isinstance(envelope, dict) or envelope.get("format") != FORMAT_NAME:
        raise CryptoError("Неизвестный формат файла хранилища.")

    try:
        salt = _b64d(envelope["kdf"]["salt"])
        iterations = int(envelope["kdf"]["iterations"])
        nonce = _b64d(envelope["cipher"]["nonce"])
        data = _b64d(envelope["data"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CryptoError("Файл хранилища повреждён: отсутствуют нужные поля.") from exc

    key = derive_key(password, salt, iterations)
    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, data, None)
    except Exception as exc:  # InvalidTag и прочее
        raise WrongPasswordError("Неверный мастер-пароль или файл повреждён.") from exc

    return plaintext, salt, iterations
