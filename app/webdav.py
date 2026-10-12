"""Небольшой клиент WebDAV на основе requests.

Поддерживает операции: проверка существования файла, чтение, запись,
создание каталогов (по сегментам пути).

Адрес вида ``davs://host/path`` трактуется как HTTPS.
"""

from __future__ import annotations

from urllib.parse import quote, urlparse, urlunparse

import requests
from requests.auth import HTTPBasicAuth

_TIMEOUT = 20


class WebDAVError(Exception):
    """Ошибка обмена с WebDAV-сервером."""


def normalize_url(url: str) -> str:
    """Приводит davs:// и путь к виду https://host/path (без хвостового /)."""
    url = (url or "").strip()
    if not url:
        return ""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme in ("davs", "dav"):
        parsed = parsed._replace(scheme="https")
    elif scheme == "dav+http":
        parsed = parsed._replace(scheme="http")
    path = parsed.path.rstrip("/")
    return urlunparse(parsed._replace(path=path))


def _split_base(base_url: str) -> tuple[str, list[str]]:
    """Возвращает (origin, сегменты пути)."""
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    segments = [seg for seg in parsed.path.split("/") if seg]
    return origin, segments


class WebDAVClient:
    def __init__(self, base_url: str, login: str = "", password: str = "",
                 logger=None) -> None:
        self.base_url = normalize_url(base_url)
        if not self.base_url:
            raise WebDAVError("Не задан адрес WebDAV-каталога.")
        self.auth = HTTPBasicAuth(login, password) if login else None
        self._log = logger if logger is not None else (lambda _msg: None)

    def _emit(self, message: str) -> None:
        try:
            self._log(message)
        except Exception:  # noqa: BLE001 - логирование не должно ломать работу
            pass

    # ---- низкоуровневые операции ------------------------------------
    def _apply_auth(self, kwargs: dict) -> dict:
        if self.auth is not None:
            kwargs["auth"] = self.auth
        return kwargs

    def _request(self, method: str, url: str, **kwargs):
        kwargs.setdefault("timeout", _TIMEOUT)
        self._apply_auth(kwargs)
        self._emit(f"→ {method} {url}")
        try:
            resp = requests.request(method, url, **kwargs)
        except requests.RequestException as exc:
            self._emit(f"✗ Ошибка соединения: {exc}")
            raise WebDAVError(f"Не удалось соединиться с сервером: {exc}") from exc
        self._emit(f"← {resp.status_code} {resp.reason or ''}".rstrip())
        return resp

    def _url(self, *parts: str) -> str:
        base = self.base_url
        for part in parts:
            base = base.rstrip("/") + "/" + quote(part.strip("/"))
        return base

    # ---- публичные операции -----------------------------------------
    def check(self) -> bool:
        """Проверяет, что каталог существует и доступен."""
        resp = self._request("PROPFIND", self.base_url + "/",
                             headers={"Depth": "0"})
        if resp.status_code in (200, 207):
            return True
        if resp.status_code == 401:
            raise WebDAVError("Неверный логин или пароль WebDAV.")
        if resp.status_code == 403:
            raise WebDAVError("Доступ запрещён (403). Проверьте права доступа.")
        if resp.status_code == 404:
            return False
        raise WebDAVError(f"Сервер вернул код {resp.status_code} при проверке каталога.")

    def test(self) -> bool:
        """Полная проверка подключения с пошаговым логом.

        Возвращает ``True``, если каталог существует, ``False`` - если каталог
        отсутствует (будет создан). Ошибки поднимаются как ``WebDAVError``.
        """
        self._emit("Шаг 1. Проверяю адрес каталога.")
        self._emit(f"Адрес: {self.base_url}")
        if self.auth is None:
            self._emit("Авторизация: без логина (анонимно).")
        else:
            self._emit("Авторизация: Basic (логин и пароль).")
        self._emit("Шаг 2. Соединяюсь с сервером и проверяю каталог (PROPFIND).")
        exists = self.check()
        if exists:
            self._emit("Шаг 3. Каталог существует и доступен.")
            return True
        self._emit("Шаг 3. Каталог не найден (404) — будет создан при синхронизации.")
        return False

    def exists(self, filename: str) -> bool:
        resp = self._request("PROPFIND", self._url(filename), headers={"Depth": "0"})
        if resp.status_code in (200, 207):
            return True
        if resp.status_code == 404:
            return False
        if resp.status_code == 401:
            raise WebDAVError("Неверный логин или пароль WebDAV.")
        raise WebDAVError(f"Сервер вернул код {resp.status_code} для файла {filename}.")

    def download(self, filename: str) -> str | None:
        resp = self._request("GET", self._url(filename))
        if resp.status_code == 404:
            return None
        if resp.status_code == 401:
            raise WebDAVError("Неверный логин или пароль WebDAV.")
        if resp.status_code != 200:
            raise WebDAVError(f"Не удалось скачать {filename}: код {resp.status_code}.")
        return resp.content.decode("utf-8")

    def upload(self, filename: str, text: str) -> None:
        resp = self._request(
            "PUT", self._url(filename),
            data=text.encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8"},
        )
        if resp.status_code not in (200, 201, 204):
            raise WebDAVError(f"Не удалось загрузить {filename}: код {resp.status_code}.")

    def ensure_dirs(self) -> None:
        """Создаёт каталог (и родителей) при необходимости."""
        origin, segments = _split_base(self.base_url)
        current = origin
        for seg in segments:
            current = current + "/" + quote(seg)
            resp = self._request("PROPFIND", current + "/", headers={"Depth": "0"})
            if resp.status_code in (200, 207):
                continue
            if resp.status_code == 401:
                raise WebDAVError("Неверный логин или пароль WebDAV.")
            if resp.status_code == 404:
                mk = self._request("MKCOL", current + "/")
                if mk.status_code not in (200, 201, 204, 405):
                    raise WebDAVError(
                        f"Не удалось создать каталог {current}: код {mk.status_code}."
                    )
            else:
                raise WebDAVError(
                    f"Сервер вернул код {resp.status_code} при проверке {current}."
                )
