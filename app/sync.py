"""Слияние двух копий хранилища.

Правило: для каждого объекта с одинаковым ``id`` побеждает версия с более
новым ``modified_at``. Объекты, помеченные tombstone (необратимо удалённые),
не возвращаются в хранилище ни из одной копии.

Расположение учётной записи (в каком сервисе она лежит или в корзине)
сливается отдельно — по метке ``location_at`` (для записи в корзине роль
метки играет ``deleted_at``). Благодаря этому перенос записи между
сервисами и удаление в корзину не «воскресают» и не дублируются при
синхронизации.
"""

from __future__ import annotations

from .models import (
    Account,
    Service,
    Tombstone,
    TrashItem,
    Vault,
    _normalize_order,
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


def _merge_services(local: Vault, remote: Vault,
                    tombs: dict[str, float]) -> dict[str, Service]:
    """Сливает сервисы по содержимому и порядку (без учётных записей).

    Учётные записи раскладываются отдельным проходом (см. :func:`merge`),
    поэтому здесь у сервисов пустые списки ``accounts``.
    """
    services: dict[str, Service] = {}
    for svc in local.services + remote.services:
        if svc.id in tombs:
            continue
        current = services.get(svc.id)
        if current is None:
            services[svc.id] = Service(
                id=svc.id,
                name=svc.name,
                icon=svc.icon,
                created_at=svc.created_at,
                modified_at=svc.modified_at,
                order=svc.order,
                order_at=svc.order_at,
            )
            continue
        if svc.modified_at > current.modified_at:
            current.name = svc.name
            current.icon = svc.icon
            current.modified_at = svc.modified_at
        if svc.order_at >= current.order_at:
            current.order = svc.order
        current.order_at = _max_ts(current.order_at, svc.order_at)
    return services


def _claim_location(claims: dict[str, tuple], acc: Account, service_id: str,
                    location_ts: float, in_trash: bool) -> None:
    """Обновляет лучшего кандидата для записи: содержимое, порядок, место.

    Содержимое берётся по ``modified_at``, порядок — по ``order_at``,
    а расположение — по ``location_ts``. Метки независимы, поэтому правка
    на одном устройстве и перенос на другом не затирают друг друга.
    """
    current = claims.get(acc.id)
    if current is None:
        acc.location_at = location_ts
        claims[acc.id] = (acc, service_id, location_ts, in_trash)
        return

    cur_acc, cur_service, cur_ts, cur_trash = current
    winner = acc if acc.modified_at > cur_acc.modified_at else cur_acc
    order_src = acc if acc.order_at >= cur_acc.order_at else cur_acc
    winner.order = order_src.order
    winner.order_at = _max_ts(acc.order_at, cur_acc.order_at)
    # При равном времени расположения предпочитаем корзину (удаление).
    if location_ts > cur_ts or (location_ts == cur_ts and in_trash and not cur_trash):
        winner.location_at = location_ts
        claims[acc.id] = (winner, service_id, location_ts, in_trash)
    else:
        winner.location_at = cur_ts
        claims[acc.id] = (winner, cur_service, cur_ts, cur_trash)


def _collect_account_claims(vaults: list[Vault],
                            tombs: dict[str, float]) -> dict[str, tuple]:
    """Собирает записи из активных сервисов и из корзины по обеим копиям.

    Возвращает ``id -> (account, service_id, location_ts, in_trash)``.
    """
    claims: dict[str, tuple] = {}
    for vault in vaults:
        for svc in vault.services:
            if svc.id in tombs:
                continue
            for acc in svc.accounts:
                if acc.id in tombs:
                    continue
                _claim_location(claims, acc, svc.id, acc.location_at, False)
        for item in vault.trash:
            if item.kind != "account" or item.id in tombs:
                continue
            payload = item.payload or {}
            acc = Account.from_dict(payload.get("account", {}))
            _claim_location(claims, acc, payload.get("service_id", ""),
                            item.deleted_at, True)
    return claims


def _merge_trash(local: Vault, remote: Vault,
                 tombs: dict[str, float]) -> dict[str, TrashItem]:
    trash: dict[str, TrashItem] = {}
    for item in local.trash + remote.trash:
        if item.id in tombs:
            continue
        current = trash.get(item.id)
        if current is None or item.modified_at > current.modified_at:
            trash[item.id] = item
    return trash


def merge(local: Vault, remote: Vault) -> Vault:
    """Возвращает новое объединённое хранилище."""
    vaults = [local, remote]
    tombs = _tombstone_ids(vaults)

    services = _merge_services(local, remote, tombs)
    claims = _collect_account_claims(vaults, tombs)
    trash = _merge_trash(local, remote, tombs)

    # Раскладываем записи по их актуальному месту.
    for acc, service_id, location_ts, in_trash in claims.values():
        if in_trash:
            continue
        service = services.get(service_id)
        if service is None:
            # Сервис исчез (удалён окончательно) — запись не воскрешаем.
            continue
        acc.location_at = location_ts
        service.accounts.append(acc)

    for service in services.values():
        _normalize_order(service.accounts)

    # Синхронизируем содержимое элементов корзины с победившими записями.
    for acc, service_id, location_ts, in_trash in claims.values():
        if not in_trash:
            # Запись активна — убираем её возможный след в корзине.
            trash.pop(acc.id, None)
            continue
        service = services.get(service_id)
        service_name = service.name if service is not None else ""
        item = trash.get(acc.id)
        if item is None:
            item = TrashItem(id=acc.id, kind="account",
                             name=acc.title or acc.login)
            trash[acc.id] = item
        if service_name:
            item.name = f"{service_name} / {acc.title or acc.login}"
        item.payload = {"service_id": service_id, "service_name": service_name,
                        "account": acc.to_dict()}
        item.modified_at = _max_ts(item.modified_at, acc.modified_at)

    tombstones: dict[str, Tombstone] = {}
    for vault in vaults:
        for ts in vault.tombstones:
            prev = tombstones.get(ts.id)
            if prev is None or ts.deleted_at > prev.deleted_at:
                tombstones[ts.id] = ts

    merged_services = list(services.values())
    merged_services.sort(key=lambda s: (s.order, s.id))

    return Vault(
        version=max(local.version, remote.version),
        services=merged_services,
        trash=list(trash.values()),
        tombstones=list(tombstones.values()),
    )


def is_same_content(a: Vault, b: Vault) -> bool:
    """Грубая проверка на идентичность (для пропуска лишней записи)."""
    return a.to_dict() == b.to_dict()
