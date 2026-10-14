"""Слияние двух копий хранилища.

Правило: для каждого объекта с одинаковым ``id`` побеждает версия с более
новым ``modified_at``. Объекты, помеченные tombstone (удалённые), не
возвращаются в хранилище ни из одной копии.

Поскольку объект живёт ровно в одном месте (переноса между сервисами и
корзины нет), отдельной синхронизации «расположения» не требуется: сервисы
сливаются по id, а учётные записи — внутри своих сервисов.
"""

from __future__ import annotations

from .models import (
    Account,
    Service,
    Tombstone,
    Vault,
)


def _merge_tombstones(vaults: list[Vault]) -> dict[str, Tombstone]:
    tombstones: dict[str, Tombstone] = {}
    for vault in vaults:
        for ts in vault.tombstones:
            prev = tombstones.get(ts.id)
            if prev is None or ts.deleted_at > prev.deleted_at:
                tombstones[ts.id] = ts
    return tombstones


def _service_copy(svc: Service) -> Service:
    """Копия сервиса без учётных записей (они сливаются отдельно)."""
    return Service(
        id=svc.id,
        name=svc.name,
        icon=svc.icon,
        created_at=svc.created_at,
        modified_at=svc.modified_at,
    )


def _merge_accounts(account_lists: list[list[Account]],
                    tomb_ids: set[str]) -> dict[str, Account]:
    """Объединяет записи по id: побеждает версия с более новым ``modified_at``."""
    merged: dict[str, Account] = {}
    for accounts in account_lists:
        for acc in accounts:
            if acc.id in tomb_ids:
                continue
            current = merged.get(acc.id)
            if current is None or acc.modified_at > current.modified_at:
                merged[acc.id] = acc
    return merged


def merge(local: Vault, remote: Vault) -> Vault:
    """Возвращает новое объединённое хранилище."""
    vaults = [local, remote]
    tombstones = _merge_tombstones(vaults)
    tomb_ids = set(tombstones)

    services: dict[str, Service] = {}
    account_lists: dict[str, list[list[Account]]] = {}
    for vault in vaults:
        for svc in vault.services:
            if svc.id in tomb_ids:
                continue
            current = services.get(svc.id)
            if current is None:
                services[svc.id] = _service_copy(svc)
                account_lists[svc.id] = []
            elif svc.modified_at > current.modified_at:
                current.name = svc.name
                current.icon = svc.icon
                current.modified_at = svc.modified_at
            account_lists[svc.id].append(svc.accounts)

    for service_id, lists in account_lists.items():
        merged = _merge_accounts(lists, tomb_ids)
        services[service_id].accounts = list(merged.values())

    # Детерминированный порядок в файле (порядок отображения задаёт интерфейс).
    merged_services = list(services.values())
    for service in merged_services:
        service.accounts.sort(key=lambda a: ((a.title or "").casefold(), a.id))
    merged_services.sort(key=lambda s: ((s.name or "").casefold(), s.id))

    return Vault(
        version=max(local.version, remote.version),
        services=merged_services,
        tombstones=list(tombstones.values()),
    )


def is_same_content(a: Vault, b: Vault) -> bool:
    """Грубая проверка на идентичность (для пропуска лишней записи)."""
    return a.to_dict() == b.to_dict()
