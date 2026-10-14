"""Модели данных менеджера паролей.

Иерархия:
    Vault
      └─ services: list[Service]

    Service
      └─ accounts: list[Account]

    Account
      └─ history: list[HistoryEntry]

Каждый объект имеет уникальный ``id`` и метку ``modified_at`` (UNIX-время,
секунды, float). Метка используется при синхронизации: при конфликте
побеждает версия с более новым ``modified_at``.

Удаление необратимо: объект убирается из хранилища, а в ``tombstones``
остаётся метка, чтобы удалённое не «воскресало» при синхронизации с копией,
где оно ещё присутствует.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


def now() -> float:
    return time.time()


def new_id() -> str:
    return uuid.uuid4().hex


def to_iso(ts: float | None) -> str:
    if not ts:
        return "—"
    return time.strftime("%d.%m.%Y %H:%M", time.localtime(ts))


def to_date(ts: float | None) -> str:
    if not ts:
        return "—"
    return time.strftime("%d.%m.%Y", time.localtime(ts))


@dataclass
class HistoryEntry:
    title: str = ""
    login: str = ""
    password: str = ""
    changed_at: float = field(default_factory=now)
    comment: str = ""
    kind: str = "password"  # "password" | "login" | "title" | "comment"

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "login": self.login,
            "password": self.password,
            "changed_at": self.changed_at,
            "comment": self.comment,
            "kind": self.kind,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HistoryEntry":
        return cls(
            title=data.get("title", ""),
            login=data.get("login", ""),
            password=data.get("password", ""),
            changed_at=float(data.get("changed_at", now())),
            comment=data.get("comment", ""),
            kind=data.get("kind", "password"),
        )


@dataclass
class Account:
    id: str = field(default_factory=new_id)
    title: str = ""
    login: str = ""
    password: str = ""
    comment: str = ""
    icon: str = ""  # имя иконки из пула ("" — без иконки)
    created_at: float = field(default_factory=now)
    password_changed_at: float = field(default_factory=now)
    login_changed_at: float = field(default_factory=now)
    title_changed_at: float = field(default_factory=now)
    comment_changed_at: float = field(default_factory=now)
    history: list[HistoryEntry] = field(default_factory=list)
    modified_at: float = field(default_factory=now)

    def touch(self) -> None:
        self.modified_at = now()

    def _snapshot(self, kind: str, changed_at: float) -> HistoryEntry:
        """Снимок текущего состояния записи для истории."""
        return HistoryEntry(
            title=self.title,
            login=self.login,
            password=self.password,
            changed_at=changed_at,
            comment=self.comment,
            kind=kind,
        )

    def change_password(self, new_password: str, comment: str | None = None) -> None:
        """Меняет пароль, сохраняя предыдущее состояние в истории."""
        if new_password == self.password:
            return
        entry = self._snapshot("password", self.password_changed_at)
        if comment is not None:
            entry.comment = comment
        self.history.insert(0, entry)
        self.password = new_password
        self.password_changed_at = now()
        self.touch()

    def change_login(self, new_login: str, comment: str | None = None) -> None:
        """Меняет логин, сохраняя предыдущее состояние в истории."""
        if new_login == self.login:
            return
        entry = self._snapshot("login", self.login_changed_at)
        if comment is not None:
            entry.comment = comment
        self.history.insert(0, entry)
        self.login = new_login
        self.login_changed_at = now()
        self.touch()

    def change_title(self, new_title: str) -> None:
        """Меняет название, сохраняя предыдущее состояние в истории."""
        if new_title == self.title:
            return
        self.history.insert(0, self._snapshot("title", self.title_changed_at))
        self.title = new_title
        self.title_changed_at = now()
        self.touch()

    def change_comment(self, new_comment: str) -> None:
        """Меняет комментарий, сохраняя предыдущее состояние в истории."""
        if new_comment == self.comment:
            return
        self.history.insert(0, self._snapshot("comment", self.comment_changed_at))
        self.comment = new_comment
        self.comment_changed_at = now()
        self.touch()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "login": self.login,
            "password": self.password,
            "comment": self.comment,
            "icon": self.icon,
            "created_at": self.created_at,
            "password_changed_at": self.password_changed_at,
            "login_changed_at": self.login_changed_at,
            "title_changed_at": self.title_changed_at,
            "comment_changed_at": self.comment_changed_at,
            "history": [h.to_dict() for h in self.history],
            "modified_at": self.modified_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Account":
        created = float(data.get("created_at", now()))
        return cls(
            id=data.get("id") or new_id(),
            title=data.get("title", ""),
            login=data.get("login", ""),
            password=data.get("password", ""),
            comment=data.get("comment", ""),
            icon=data.get("icon", ""),
            created_at=created,
            password_changed_at=float(data.get("password_changed_at", now())),
            login_changed_at=float(data.get("login_changed_at", created)),
            title_changed_at=float(data.get("title_changed_at", created)),
            comment_changed_at=float(data.get("comment_changed_at", created)),
            history=[HistoryEntry.from_dict(h) for h in data.get("history", [])],
            modified_at=float(data.get("modified_at", now())),
        )


@dataclass
class Service:
    id: str = field(default_factory=new_id)
    name: str = ""
    icon: str = ""  # имя иконки из пула ("" — без иконки)
    created_at: float = field(default_factory=now)
    accounts: list[Account] = field(default_factory=list)
    modified_at: float = field(default_factory=now)

    def touch(self) -> None:
        self.modified_at = now()

    def add_account(self, account: Account) -> None:
        """Добавляет учётную запись в сервис."""
        self.accounts.append(account)

    def account(self, account_id: str) -> Account | None:
        for acc in self.accounts:
            if acc.id == account_id:
                return acc
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "icon": self.icon,
            "created_at": self.created_at,
            "accounts": [a.to_dict() for a in self.accounts],
            "modified_at": self.modified_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Service":
        return cls(
            id=data.get("id") or new_id(),
            name=data.get("name", ""),
            icon=data.get("icon", ""),
            created_at=float(data.get("created_at", now())),
            accounts=[Account.from_dict(a) for a in data.get("accounts", [])],
            modified_at=float(data.get("modified_at", now())),
        )


@dataclass
class Tombstone:
    """Метка необратимого удаления.

    Нужна, чтобы удалённый объект не «воскресал» при синхронизации с копией,
    где он ещё присутствует.
    """
    id: str
    deleted_at: float = field(default_factory=now)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "deleted_at": self.deleted_at}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Tombstone":
        return cls(id=data["id"], deleted_at=float(data.get("deleted_at", now())))


@dataclass
class Vault:
    version: int = 1
    services: list[Service] = field(default_factory=list)
    tombstones: list[Tombstone] = field(default_factory=list)

    # ---- поиск -------------------------------------------------------
    def service(self, service_id: str) -> Service | None:
        for svc in self.services:
            if svc.id == service_id:
                return svc
        return None

    def account(self, account_id: str) -> tuple[Service, Account] | None:
        for svc in self.services:
            for acc in svc.accounts:
                if acc.id == account_id:
                    return svc, acc
        return None

    def all_account_count(self) -> int:
        return sum(len(s.accounts) for s in self.services)

    # ---- операции ----------------------------------------------------
    def add_service(self, service: Service) -> None:
        """Добавляет сервис."""
        self.services.append(service)

    def delete_service(self, service: Service) -> None:
        """Необратимо удаляет сервис вместе с его учётными записями."""
        doomed = {service.id} | {acc.id for acc in service.accounts}
        self.tombstones = [t for t in self.tombstones if t.id not in doomed]
        for item_id in doomed:
            self.tombstones.append(Tombstone(id=item_id))
        self.services = [s for s in self.services if s.id != service.id]

    def delete_account(self, service: Service, account: Account) -> None:
        """Необратимо удаляет учётную запись из сервиса."""
        service.accounts = [a for a in service.accounts if a.id != account.id]
        service.touch()
        self.tombstones = [t for t in self.tombstones if t.id != account.id]
        self.tombstones.append(Tombstone(id=account.id))

    # ---- сериализация -----------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "services": [s.to_dict() for s in self.services],
            "tombstones": [t.to_dict() for t in self.tombstones],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Vault":
        services = [Service.from_dict(s) for s in data.get("services", [])]
        tombstones = [Tombstone.from_dict(t) for t in data.get("tombstones", [])]
        # Совместимость со старым форматом с корзиной: объекты из корзины
        # считаются окончательно удалёнными (ставятся метки удаления).
        known = {t.id for t in tombstones}
        for item in data.get("trash", []):
            if not isinstance(item, dict):
                continue
            item_id = item.get("id")
            if item_id and item_id not in known:
                tombstones.append(Tombstone(id=item_id,
                                            deleted_at=float(item.get("deleted_at",
                                                                      now()))))
                known.add(item_id)
        return cls(
            version=int(data.get("version", 1)),
            services=services,
            tombstones=tombstones,
        )

    @classmethod
    def empty(cls) -> "Vault":
        return cls()
