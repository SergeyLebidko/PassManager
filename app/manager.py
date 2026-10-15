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
    # Удалённая копия зашифрована другим мастер-паролем: нужно спросить новый.
    password_mismatch: bool = False
    # Смена пароля упрётся в перезапись сервера — требуется подтверждение.
    needs_overwrite: bool = False


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

        # После смены мастер-пароля удалённая копия обычно зашифрована старым
        # паролем, и расшифровать её нельзя. Пробуем прочитать её текущим
        # (новым) паролем: если удалось — сливаем, иначе перезаливаем локальную
        # копию (она уже содержит актуальные данные) и снимаем отметку.
        if self.config.get("pending_reencrypt"):
            client.ensure_dirs()
            remote_text = client.download(storage.REMOTE_FILENAME)
            with self._lock:
                if remote_text:
                    try:
                        remote_vault = storage.decrypt_vault_text(
                            self._current_password, remote_text)
                    except crypto.CryptoError:
                        remote_vault = None
                    if remote_vault is not None:
                        self.vault = merge(self.vault, remote_vault)
                self.save_local()
                local_text = self._encrypted_local_text()
            client.upload(storage.REMOTE_FILENAME, local_text)
            self.config.pop("pending_reencrypt", None)
            storage.save_config(self.config)
            return SyncResult(
                True, True,
                "Удалённая копия обновлена после смены мастер-пароля.")

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
            # Интерфейс предложит ввести новый пароль и слить копии (adopt_remote).
            return SyncResult(
                False, True,
                "Удалённая копия зашифрована другим мастер-паролем. "
                "Синхронизация пропущена для защиты данных.",
                password_mismatch=True)

        # Короткая критическая секция: слияние и локальная запись.
        with self._lock:
            merged = merge(self.vault, remote_vault)
            self.vault = merged
            self.save_local()
            local_text = self._encrypted_local_text()

        # Сеть - вне блокировки.
        client.upload(storage.REMOTE_FILENAME, local_text)
        return SyncResult(True, True, "Данные синхронизированы.")

    # ---- смена мастер-пароля ------------------------------------------
    def check_password(self, password: str) -> bool:
        """Верен ли текущий мастер-пароль разблокированного хранилища."""
        if not password or not self.key:
            return False
        try:
            return crypto.derive_key(password, self.salt, self.iterations) == self.key
        except Exception:  # noqa: BLE001 - проверка не должна падать
            return False

    def change_master_password(self, new_password: str,
                               allow_overwrite: bool = False) -> SyncResult:
        """Меняет мастер-пароль, перешифровывая хранилище и пароль сервера.

        Порядок действий:
        1. синхронизация под старым паролем (best effort) — чтобы слить
           возможные правки с сервера;
        2. если серверная копия зашифрована другим паролем, пробуем прочитать
           её НОВЫМ паролем и слить — тогда ничего не перезаписывается;
        3. перешифровка локального ``vault.txt`` и пароля WebDAV новым ключом;
        4. перезалив копии на сервер.

        Если прочитать серверную копию новым паролем не удалось, смена
        отменяется и возвращается результат с ``needs_overwrite=True``:
        вызывающий код должен подтвердить перезапись сервера и вызвать метод
        повторно с ``allow_overwrite=True``.

        Если сервер недоступен, смена выполняется локально, а удалённая копия
        обновляется при первой же удачной синхронизации (флаг
        ``pending_reencrypt``).
        """
        if not new_password:
            return SyncResult(False, False,
                              "Новый мастер-пароль не может быть пустым.")

        # 1) Слияние с сервером под старым паролем (сервер может быть недоступен).
        pre = self.try_sync()

        # 2) Серверная копия под другим паролем? Пробуем прочитать её новым.
        if pre.password_mismatch:
            try:
                remote_vault = self._read_remote_with(new_password)
            except WebDAVError as exc:
                return SyncResult(
                    False, True,
                    "Не удалось прочитать удалённую копию: " + str(exc),
                    password_mismatch=True)
            if remote_vault is not None:
                # Сливаем серверные данные в локальную копию — без вытеснения.
                self.vault = merge(self.vault, remote_vault)
            elif not allow_overwrite:
                return SyncResult(
                    False, True,
                    "Удалённая копия зашифрована другим мастер-паролем и не "
                    "открывается новым. Продолжение перезапишет серверную копию.",
                    password_mismatch=True, needs_overwrite=True)

        # 3) Перешифровка локальных данных. Пароль WebDAV тоже зашифрован
        #    мастер-ключом, поэтому сначала читаем его старым ключом.
        with self._lock:
            server_password = self.server_password()
            self.salt = crypto.new_salt()
            self.key = crypto.derive_key(new_password, self.salt, self.iterations)
            self._current_password = new_password
            self.config = storage.encrypt_server_password(
                {**self.config, "webdav_password": server_password}, self.key)
            storage.save_config(self.config)
            self.save_local()
            local_text = self._encrypted_local_text()

        # 4) Заливаем перешифрованную копию на сервер.
        try:
            client = self._client()
            client.ensure_dirs()
            client.upload(storage.REMOTE_FILENAME, local_text)
        except WebDAVError as exc:
            self.config["pending_reencrypt"] = True
            storage.save_config(self.config)
            return SyncResult(
                True, False,
                "Мастер-пароль изменён. Удалённую копию залить не удалось, "
                "она будет обновлена при следующей синхронизации: " + str(exc))
        except Exception as exc:  # noqa: BLE001 - не роняем программу
            self.config["pending_reencrypt"] = True
            storage.save_config(self.config)
            return SyncResult(
                False, False,
                "Мастер-пароль изменён, но при заливке на сервер произошла "
                "ошибка: " + str(exc))

        self.config.pop("pending_reencrypt", None)
        storage.save_config(self.config)
        return SyncResult(True, True, "Мастер-пароль изменён и синхронизирован.")

    def adopt_remote(self, new_password: str) -> SyncResult:
        """Переходит на мастер-пароль удалённой копии и сливает данные.

        Используется, когда серверная копия зашифрована другим мастер-паролем:
        чтобы не перезаписывать её, читаем её ``new_password``, объединяем с
        локальной копией и переводим это устройство на тот же пароль.
        """
        if not new_password:
            return SyncResult(False, False, "Мастер-пароль не может быть пустым.")
        try:
            client = self._client()
        except WebDAVError as exc:
            return SyncResult(False, False, str(exc))
        try:
            remote_text = client.download(storage.REMOTE_FILENAME)
        except WebDAVError as exc:
            return SyncResult(
                False, True, "Не удалось скачать удалённую копию: " + str(exc),
                password_mismatch=True)
        if remote_text is None:
            return SyncResult(
                False, True, "Удалённая копия не найдена.",
                password_mismatch=True)
        try:
            remote_vault = storage.decrypt_vault_text(new_password, remote_text)
        except crypto.CryptoError:
            return SyncResult(
                False, True, "Неверный мастер-пароль удалённой копии.",
                password_mismatch=True)

        with self._lock:
            server_password = self.server_password()
            self.salt = crypto.new_salt()
            self.key = crypto.derive_key(new_password, self.salt, self.iterations)
            self._current_password = new_password
            self.vault = merge(self.vault, remote_vault)
            self.config = storage.encrypt_server_password(
                {**self.config, "webdav_password": server_password}, self.key)
            storage.save_config(self.config)
            self.save_local()
            local_text = self._encrypted_local_text()

        try:
            client.ensure_dirs()
            client.upload(storage.REMOTE_FILENAME, local_text)
        except WebDAVError as exc:
            self.config["pending_reencrypt"] = True
            storage.save_config(self.config)
            return SyncResult(
                True, False,
                "Данные объединены, но залить на сервер не удалось: " + str(exc))
        except Exception as exc:  # noqa: BLE001 - не роняем программу
            self.config["pending_reencrypt"] = True
            storage.save_config(self.config)
            return SyncResult(
                False, False,
                "Данные объединены, но при заливке произошла ошибка: " + str(exc))

        self.config.pop("pending_reencrypt", None)
        storage.save_config(self.config)
        return SyncResult(True, True, "Данные объединены с серверной копией.")

    def _read_remote_with(self, password: str) -> "Vault | None":
        """Читает удалённую копию указанным паролем (None — нет/не открылась)."""
        client = self._client()
        remote_text = client.download(storage.REMOTE_FILENAME)
        if remote_text is None:
            return None
        try:
            return storage.decrypt_vault_text(password, remote_text)
        except crypto.CryptoError:
            return None

    # ---- вспомогательное ---------------------------------------------
    def set_password(self, password: str) -> None:
        self._current_password = password

    def _encrypted_local_text(self) -> str:
        path = Path(storage.VAULT_FILE)
        return path.read_text(encoding="utf-8")
