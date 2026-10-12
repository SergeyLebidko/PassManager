"""Управление хранилищем: загрузка, сохранение, синхронизация с WebDAV.

Здесь сосредоточена вся прикладная логика, независимая от интерфейса.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from . import crypto, storage
from .models import Vault
from .sync import merge
from .webdav import WebDAVClient, WebDAVError


class ManagerError(Exception):
    pass


@dataclass
class SyncResult:
    ok: bool
    remote_available: bool
    message: str
    changed: bool = False


class Manager:
    """Связывает локальную копию, ключ шифрования и удалённый WebDAV."""

    def __init__(self) -> None:
        self.vault = Vault.empty()
        self.key: bytes = b""
        self.salt: bytes = b""
        self.iterations: int = crypto.KDF_ITERATIONS
        self.config = storage.load_config()
        self._current_password: str = ""
        self._lock = threading.RLock()

    # ---- локальная копия --------------------------------------------
    def has_local(self) -> bool:
        return storage.vault_exists()

    def create_new(self, password: str) -> None:
        """Создаёт новое пустое хранилище под заданным мастер-паролем."""
        self.salt = crypto.new_salt()
        self.iterations = crypto.KDF_ITERATIONS
        self.key = crypto.derive_key(password, self.salt, self.iterations)
        self.vault = Vault.empty()
        self.save_local()

    def unlock(self, password: str) -> None:
        vault, key, salt, iterations = storage.load_vault(password)
        self.vault = vault
        self.key = key
        self.salt = salt
        self.iterations = iterations

    def save_local(self) -> None:
        with self._lock:
            storage.save_vault(self.vault, self.key, self.salt, self.iterations)

    def save(self) -> None:
        """Сохраняет локально. Синхронизация выполняется отдельно, в фоне."""
        self.save_local()

    # ---- настройки ---------------------------------------------------
    @property
    def webdav_url(self) -> str:
        return self.config.get("webdav_url", "")

    def server_password(self) -> str:
        return storage.decrypt_server_password(self.config, self.key)

    def update_server_settings(self, url: str, login: str, password: str) -> None:
        self.config["webdav_url"] = url
        self.config["webdav_login"] = login
        self.config = storage.encrypt_server_password(
            {**self.config, "webdav_password": password}, self.key)
        storage.save_config(self.config)

    def _client(self) -> WebDAVClient:
        return WebDAVClient(
            self.webdav_url,
            self.config.get("webdav_login", ""),
            self.server_password(),
        )

    # ---- удалённая копия ---------------------------------------------
    def test_connection(self) -> SyncResult:
        try:
            client = self._client()
        except WebDAVError as exc:
            return SyncResult(False, False, str(exc))
        try:
            exists = client.check()
        except WebDAVError as exc:
            return SyncResult(False, True, str(exc))
        if exists:
            return SyncResult(True, True, "Подключение успешно, каталог доступен.")
        return SyncResult(True, True,
                          "Подключение успешно, каталог будет создан при синхронизации.")

    def try_sync(self, save_after: bool = True) -> SyncResult:
        """Пытается синхронизироваться; при недоступности сервера ошибкой не падает."""
        try:
            return self._sync()
        except WebDAVError as exc:
            if save_after:
                self.save_local()
            return SyncResult(True, False, f"Сервер недоступен, работаем локально: {exc}")
        except Exception as exc:  # неожиданное - не роняем программу
            if save_after:
                self.save_local()
            return SyncResult(False, False, f"Ошибка синхронизации: {exc}")

    def _sync(self) -> SyncResult:
        client = self._client()
        # check() возвращает False только для отсутствующего каталога (404).
        # Ошибки соединения/авторизации выбрасывают WebDAVError и обрабатываются
        # в try_sync как «сервер недоступен».
        available = client.check()

        if not available:
            # Каталога нет - создаём и заливаем локальную копию.
            client.ensure_dirs()
            with self._lock:
                local_text = self._encrypted_local_text()
            client.upload(storage.REMOTE_FILENAME, local_text)
            return SyncResult(True, True, "Создана удалённая копия данных.")

        remote_text = client.download(storage.REMOTE_FILENAME)
        if remote_text is None:
            with self._lock:
                local_text = self._encrypted_local_text()
            client.upload(storage.REMOTE_FILENAME, local_text)
            return SyncResult(True, True, "Удалённая копия создана из локальной.")

        # Расшифровываем удалённую копию тем же мастер-паролем.
        try:
            remote_vault = storage.decrypt_vault_text(self._current_password, remote_text)
        except crypto.CryptoError:
            # Не удалось расшифровать (иной мастер-пароль) - не затираем сервер.
            return SyncResult(
                False, True,
                "Удалённая копия зашифрована другим мастер-паролем. "
                "Синхронизация пропущена для защиты данных.")

        # Короткая критическая секция: слияние и локальная запись.
        with self._lock:
            merged = merge(self.vault, remote_vault)
            self.vault = merged
            self.save_local()
            local_text = self._encrypted_local_text()

        # Сеть - вне блокировки.
        client.upload(storage.REMOTE_FILENAME, local_text)
        return SyncResult(True, True, "Данные синхронизированы.")

    # ---- вспомогательное ---------------------------------------------
    def autosync_enabled(self) -> bool:
        return bool(self.config.get("autosync", True))

    def set_password(self, password: str) -> None:
        self._current_password = password

    def _encrypted_local_text(self) -> str:
        path = Path(storage.VAULT_FILE)
        return path.read_text(encoding="utf-8")
