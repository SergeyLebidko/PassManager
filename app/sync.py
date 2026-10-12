"""Слияние двух копий хранилища.

Правило: для каждого объекта с одинаковым ``id`` побеждает версия с более
новым ``modified_at``. Объекты, помеченные tombstone (необратимо удалённые),
не возвращаются в хранилище ни из одной копии.
"""

from __future__ import annotations

from .models import (
    Account,
    Service,
    Tombstone,
    TrashItem,
    Vault,
)


def _max_ts(a: float, b: float) -> float:
    return a if a >= b else b


def _tombstone_ids(vaults: list[Vault]) -> dict[str, float]:
    result: dict[str, float] = {}
    for vault in vaults:
        for ts in vault.tombstones:
            prev = result.get(ts.id)
            if prev is None or ts.deleted_at > prev:
                result[ts.id] = ts.deleted_at
    return result


def _merge_accounts(local: list[Account], remote: list[Account],
                    tombs: dict[str, float]) -> list[Account]:
    by_id: dict[str, Account] = {}
    for acc in local + remote:
        if acc.id in tombs:
            continue
        current = by_id.get(acc.id)
        if current is None or acc.modified_at > current.modified_at:
            by_id[acc.id] = acc
    return list(by_id.values())


def merge(local: Vault, remote: Vault) -> Vault:
    """Возвращает новое объединённое хранилище."""
    tombs = _tombstone_ids([local, remote])

    services_by_id: dict[str, Service] = {}
    for svc in local.services + remote.services:
        if svc.id in tombs:
            continue
        current = services_by_id.get(svc.id)
        if current is None:
            services_by_id[svc.id] = svc
            continue
        # Берём более новую версию сервиса, но аккаунты сливаем попарно.
        newer, older = (svc, current) if svc.modified_at > current.modified_at else (current, svc)
        newer.accounts = _merge_accounts(newer.accounts, older.accounts, tombs)
        services_by_id[svc.id] = newer

    trash_by_id: dict[str, TrashItem] = {}
    for item in local.trash + remote.trash:
        if item.id in tombs:
            continue
        current = trash_by_id.get(item.id)
        if current is None or item.modified_at > current.modified_at:
            trash_by_id[item.id] = item

    tombstones: dict[str, Tombstone] = {}
    for vault in (local, remote):
        for ts in vault.tombstones:
            prev = tombstones.get(ts.id)
            if prev is None or ts.deleted_at > prev.deleted_at:
                tombstones[ts.id] = ts

    merged = Vault(
        version=max(local.version, remote.version),
        services=list(services_by_id.values()),
        trash=list(trash_by_id.values()),
        tombstones=list(tombstones.values()),
    )
    merged.services.sort(key=lambda s: s.name.lower())
    return merged


def is_same_content(a: Vault, b: Vault) -> bool:
    """Грубая проверка на идентичность (для пропуска лишней записи)."""
    return a.to_dict() == b.to_dict()
