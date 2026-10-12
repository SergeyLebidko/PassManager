"""Модели данных менеджера паролей.

Иерархия:
    Vault
      ├─ services: list[Service]
      └─ trash:    list[TrashItem]

    Service
      └─ accounts: list[Account]

    Account
      └─ history: list[HistoryEntry]

Каждый объект имеет уникальный ``id`` и метку ``modified_at`` (UNIX-время,
секунды, float). Метка используется при синхронизации: при конфликте
побеждает версия с более новым ``modified_at``.
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
    login: str = ""
    password: str = ""
    changed_at: float = field(default_factory=now)
    comment: str = ""
    kind: str = "password"  # "password" | "login"

    def to_dict(self) -> dict[str, Any]:
        return {
            "login": self.login,
            "password": self.password,
            "changed_at": self.changed_at,
            "comment": self.comment,
            "kind": self.kind,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HistoryEntry":
        return cls(
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
    created_at: float = field(default_factory=now)
    password_changed_at: float = field(default_factory=now)
    login_changed_at: float = field(default_factory=now)
    history: list[HistoryEntry] = field(default_factory=list)
    modified_at: float = field(default_factory=now)

    def touch(self) -> None:
        self.modified_at = now()

    def change_password(self, new_password: str, comment: str | None = None) -> None:
        """Меняет пароль, сохраняя предыдущее состояние в истории."""
        if new_password == self.password:
            return
        self.history.insert(0, HistoryEntry(
            login=self.login,
            password=self.password,
            changed_at=self.password_changed_at,
            comment=self.comment if comment is None else comment,
            kind="password",
        ))
        self.password = new_password
        self.password_changed_at = now()
        self.touch()

    def change_login(self, new_login: str, comment: str | None = None) -> None:
        """Меняет логин, сохраняя предыдущее состояние в истории."""
        if new_login == self.login:
            return
        self.history.insert(0, HistoryEntry(
            login=self.login,
            password=self.password,
            changed_at=self.login_changed_at,
            comment=self.comment if comment is None else comment,
            kind="login",
        ))
        self.login = new_login
        self.login_changed_at = now()
        self.touch()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "login": self.login,
            "password": self.password,
            "comment": self.comment,
            "created_at": self.created_at,
            "password_changed_at": self.password_changed_at,
            "login_changed_at": self.login_changed_at,
            "history": [h.to_dict() for h in self.history],
            "modified_at": self.modified_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Account":
        return cls(
            id=data.get("id") or new_id(),
            title=data.get("title", ""),
            login=data.get("login", ""),
            password=data.get("password", ""),
            comment=data.get("comment", ""),
            created_at=float(data.get("created_at", now())),
            password_changed_at=float(data.get("password_changed_at", now())),
            login_changed_at=float(data.get("login_changed_at",
                                           data.get("created_at", now()))),
            history=[HistoryEntry.from_dict(h) for h in data.get("history", [])],
            modified_at=float(data.get("modified_at", now())),
        )


@dataclass
class Service:
    id: str = field(default_factory=new_id)
    name: str = ""
    created_at: float = field(default_factory=now)
    accounts: list[Account] = field(default_factory=list)
    modified_at: float = field(default_factory=now)

    def touch(self) -> None:
        self.modified_at = now()

    def account(self, account_id: str) -> Account | None:
        for acc in self.accounts:
            if acc.id == account_id:
                return acc
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "accounts": [a.to_dict() for a in self.accounts],
            "modified_at": self.modified_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Service":
        return cls(
            id=data.get("id") or new_id(),
            name=data.get("name", ""),
            created_at=float(data.get("created_at", now())),
            accounts=[Account.from_dict(a) for a in data.get("accounts", [])],
            modified_at=float(data.get("modified_at", now())),
        )


@dataclass
class TrashItem:
    """Удалённый объект, хранящийся в корзине неограниченно долго.

    ``payload`` - сериализованное представление удалённого ``Service``
    или ``Account``.
    """
    id: str
    kind: str  # "service" | "account"
    name: str
    payload: dict[str, Any]
    deleted_at: float = field(default_factory=now)
    modified_at: float = field(default_factory=now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "payload": self.payload,
            "deleted_at": self.deleted_at,
            "modified_at": self.modified_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TrashItem":
        return cls(
            id=data.get("id") or new_id(),
            kind=data.get("kind", "account"),
            name=data.get("name", ""),
            payload=data.get("payload", {}),
            deleted_at=float(data.get("deleted_at", now())),
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
    trash: list[TrashItem] = field(default_factory=list)
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

    # ---- корзина -----------------------------------------------------
    def trash_service(self, service: Service) -> None:
        self.trash.append(TrashItem(
            id=service.id,
            kind="service",
            name=service.name,
            payload=service.to_dict(),
        ))
        self.services = [s for s in self.services if s.id != service.id]

    def trash_account(self, service: Service, account: Account) -> None:
        self.trash.append(TrashItem(
            id=account.id,
            kind="account",
            name=f"{service.name} / {account.title or account.login}",
            payload={"service_id": service.id, "service_name": service.name,
                     "account": account.to_dict()},
        ))
        service.accounts = [a for a in service.accounts if a.id != account.id]
        service.touch()

    def _trashed_service(self, service_id: str) -> TrashItem | None:
        for item in self.trash:
            if item.kind == "service" and item.id == service_id:
                return item
        return None

    def restore(self, item: TrashItem) -> None:
        if item.kind == "service":
            svc = Service.from_dict(item.payload)
            existing = self.service(svc.id)
            if existing is None:
                self.services.append(svc)
            else:
                # Сервис уже есть — переносим отсутствующие учётные записи.
                for acc in svc.accounts:
                    if existing.account(acc.id) is None:
                        existing.accounts.append(acc)
                existing.touch()
        else:
            data = item.payload
            service_id = data.get("service_id", "")
            svc = self.service(service_id)
            if svc is None:
                # Сервиса нет среди активных. Возможно, он лежит в корзине —
                # тогда восстанавливаем его, чтобы не создавать дубликат.
                trashed = self._trashed_service(service_id)
                if trashed is not None:
                    svc = Service.from_dict(trashed.payload)
                    self.services.append(svc)
                    self.trash = [t for t in self.trash if t.id != trashed.id]
                else:
                    svc = Service(id=service_id or new_id(),
                                  name=data.get("service_name",
                                                "Восстановленный сервис"))
                    self.services.append(svc)
            acc = Account.from_dict(data["account"])
            if svc.account(acc.id) is None:
                svc.accounts.append(acc)
            svc.touch()
        self.trash = [t for t in self.trash if t.id != item.id]

    def purge(self, item: TrashItem) -> None:
        """Полностью удаляет элемент корзины и ставит tombstone."""
        self.trash = [t for t in self.trash if t.id != item.id]
        self.tombstones.append(Tombstone(id=item.id))

    def clear_trash(self) -> int:
        count = len(self.trash)
        for item in self.trash:
            self.tombstones.append(Tombstone(id=item.id))
        self.trash = []
        return count

    # ---- сериализация -----------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "services": [s.to_dict() for s in self.services],
            "trash": [t.to_dict() for t in self.trash],
            "tombstones": [t.to_dict() for t in self.tombstones],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Vault":
        return cls(
            version=int(data.get("version", 1)),
            services=[Service.from_dict(s) for s in data.get("services", [])],
            trash=[TrashItem.from_dict(t) for t in data.get("trash", [])],
            tombstones=[Tombstone.from_dict(t) for t in data.get("tombstones", [])],
        )

    @classmethod
    def empty(cls) -> "Vault":
        return cls()
