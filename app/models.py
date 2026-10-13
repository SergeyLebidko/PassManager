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


def _normalize_order(items: list) -> None:
    """Стабильно сортирует объекты по ``order`` и делает позиции плотными.

    В старых файлах поле ``order`` отсутствует — тогда у всех элементов
    одинаковый ноль, и стабильная сортировка сохраняет прежний порядок из
    файла. После этого позиции становятся уникальными (0..n-1).
    """
    items.sort(key=lambda obj: obj.order)
    for index, obj in enumerate(items):
        obj.order = float(index)


def _next_top_order(items: list) -> float:
    """Позиция для нового элемента — выше всех существующих."""
    if not items:
        return 0.0
    return min(item.order for item in items) - 1.0


def _next_bottom_order(items: list) -> float:
    """Позиция для элемента в конце списка."""
    if not items:
        return 0.0
    return max(item.order for item in items) + 1.0


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
    order: float = 0.0
    order_at: float = 0.0  # когда менялся порядок (для синхронизации)
    location_at: float = 0.0  # когда запись меняла сервис (для синхронизации)

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
            "order": self.order,
            "order_at": self.order_at,
            "location_at": self.location_at,
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
            order=float(data.get("order", 0.0)),
            order_at=float(data.get("order_at", 0.0)),
            location_at=float(data.get("location_at", 0.0)),
        )


@dataclass
class Service:
    id: str = field(default_factory=new_id)
    name: str = ""
    icon: str = ""  # имя иконки из пула ("" — без иконки)
    created_at: float = field(default_factory=now)
    accounts: list[Account] = field(default_factory=list)
    modified_at: float = field(default_factory=now)
    order: float = 0.0
    order_at: float = 0.0  # когда менялся порядок (для синхронизации)

    def touch(self) -> None:
        self.modified_at = now()

    def reorder(self, ordered_ids: list[str]) -> None:
        """Расставляет учётные записи в заданном порядке (drag & drop/сортировка)."""
        by_id = {acc.id: acc for acc in self.accounts}
        new_items = [by_id[i] for i in ordered_ids if i in by_id]
        # Записи, которых не было в списке, сохраняем в конце.
        new_items += [acc for acc in self.accounts if acc.id not in set(ordered_ids)]
        stamp = now()
        for index, acc in enumerate(new_items):
            acc.order = float(index)
            acc.order_at = stamp
        self.accounts = new_items

    def add_account_top(self, account: Account) -> None:
        """Добавляет учётную запись в начало списка."""
        account.order = _next_top_order(self.accounts)
        account.order_at = now()
        account.location_at = now()
        self.accounts.append(account)
        _normalize_order(self.accounts)

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
            "order": self.order,
            "order_at": self.order_at,
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
            order=float(data.get("order", 0.0)),
            order_at=float(data.get("order_at", 0.0)),
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

    # ---- порядок -----------------------------------------------------
    def add_service(self, service: Service) -> None:
        """Добавляет сервис в начало списка."""
        service.order = _next_top_order(self.services)
        service.order_at = now()
        self.services.append(service)
        _normalize_order(self.services)

    def reorder_services(self, ordered_ids: list[str]) -> None:
        """Расставляет сервисы в заданном порядке (drag & drop/сортировка)."""
        by_id = {svc.id: svc for svc in self.services}
        new_items = [by_id[i] for i in ordered_ids if i in by_id]
        new_items += [s for s in self.services if s.id not in set(ordered_ids)]
        stamp = now()
        for index, svc in enumerate(new_items):
            svc.order = float(index)
            svc.order_at = stamp
        self.services = new_items

    def move_account(self, account: Account, source: Service,
                     target: Service) -> None:
        """Переносит учётную запись из одного сервиса в другой.

        Запись встаёт в начало целевого сервиса (ручное изменение порядка),
        а факт переноса фиксируется в её журнале.
        """
        if source is target:
            return
        source.accounts = [a for a in source.accounts if a.id != account.id]
        source.touch()
        entry = account._snapshot("move", now())
        entry.comment = f"{source.name} → {target.name}"
        account.history.insert(0, entry)
        account.location_at = now()
        account.touch()
        target.add_account_top(account)
        target.touch()

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
                svc.order = _next_bottom_order(self.services)
                svc.order_at = now()
                self.services.append(svc)
                _normalize_order(self.services)
            else:
                # Сервис уже есть — переносим отсутствующие учётные записи.
                for acc in svc.accounts:
                    if existing.account(acc.id) is None:
                        acc.order = _next_bottom_order(existing.accounts)
                        acc.order_at = now()
                        acc.location_at = now()
                        existing.accounts.append(acc)
                _normalize_order(existing.accounts)
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
                    svc.order = _next_bottom_order(self.services)
                    svc.order_at = now()
                    self.services.append(svc)
                    _normalize_order(self.services)
                    self.trash = [t for t in self.trash if t.id != trashed.id]
                else:
                    svc = Service(id=service_id or new_id(),
                                  name=data.get("service_name",
                                                "Восстановленный сервис"))
                    svc.order = _next_bottom_order(self.services)
                    svc.order_at = now()
                    self.services.append(svc)
                    _normalize_order(self.services)
            acc = Account.from_dict(data["account"])
            if svc.account(acc.id) is None:
                acc.order = _next_bottom_order(svc.accounts)
                acc.order_at = now()
                acc.location_at = now()
                svc.accounts.append(acc)
                _normalize_order(svc.accounts)
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
        services = [Service.from_dict(s) for s in data.get("services", [])]
        _normalize_order(services)
        for service in services:
            _normalize_order(service.accounts)
        return cls(
            version=int(data.get("version", 1)),
            services=services,
            trash=[TrashItem.from_dict(t) for t in data.get("trash", [])],
            tombstones=[Tombstone.from_dict(t) for t in data.get("tombstones", [])],
        )

    @classmethod
    def empty(cls) -> "Vault":
        return cls()
