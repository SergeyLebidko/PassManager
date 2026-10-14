"""Слияние двух копий хранилища.

Правило: для каждого объекта с одинаковым ``id`` побеждает версия с более
новым ``modified_at``. Объекты, помеченные tombstone (необратимо удалённые),
не возвращаются в хранилище ни из одной копии.

Расположение объекта (в каком списке он лежит — активном или в корзине)
сливается отдельно по метке времени: у учётной записи это ``location_at``
(в корзине роль метки играет ``deleted_at``), у сервиса — тоже
``location_at`` (а в корзине — ``deleted_at``). Благодаря этому перенос
записи между сервисами и удаление в корзину не «воскресают» и не
дублируются при синхронизации.
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


def _service_copy(svc: Service) -> Service:
    """Копия сервиса без учётных записей (они раскладываются отдельно)."""
    return Service(
        id=svc.id,
        name=svc.name,
        icon=svc.icon,
        created_at=svc.created_at,
        modified_at=svc.modified_at,
        order=svc.order,
        order_at=svc.order_at,
        location_at=svc.location_at,
    )


def _claim_service(claims: dict[str, tuple], svc: Service, location_ts: float,
                   in_trash: bool, trash_item: TrashItem | None) -> None:
    """Обновляет лучшего кандидата для сервиса: содержимое, порядок, место.

    Содержимое берётся по ``modified_at``, порядок — по ``order_at``,
    а расположение (активен сервис или в корзине) — по ``location_ts``.
    При равном времени расположения предпочитаем корзину (удаление).
    """
    current = claims.get(svc.id)
    if current is None:
        copy = _service_copy(svc)
        copy.location_at = location_ts
        claims[svc.id] = (copy, location_ts, in_trash, trash_item)
        return

    cur_svc, cur_ts, cur_trash, cur_item = current
    # Содержимое — по более новой версии.
    if svc.modified_at > cur_svc.modified_at:
        cur_svc.name = svc.name
        cur_svc.icon = svc.icon
        cur_svc.modified_at = svc.modified_at
    # Порядок — по более новой метке ручного изменения.
    if svc.order_at >= cur_svc.order_at:
        cur_svc.order = svc.order
    cur_svc.order_at = _max_ts(svc.order_at, cur_svc.order_at)
    # Расположение.
    if location_ts > cur_ts or (location_ts == cur_ts and in_trash and not cur_trash):
        cur_svc.location_at = location_ts
        claims[svc.id] = (cur_svc, location_ts, in_trash,
                          trash_item if in_trash else cur_item)
    else:
        cur_svc.location_at = cur_ts
        claims[svc.id] = (cur_svc, cur_ts, cur_trash, cur_item)


def _collect_service_claims(vaults: list[Vault],
                            tombs: dict[str, float]) -> dict[str, tuple]:
    """Собирает сервисы из активных списков и из корзины по обеим копиям.

    Возвращает ``id -> (service, location_ts, in_trash, trash_item)``.
    """
    claims: dict[str, tuple] = {}
    for vault in vaults:
        for svc in vault.services:
            if svc.id in tombs:
                continue
            _claim_service(claims, svc, svc.location_at, False, None)
        for item in vault.trash:
            if item.kind != "service" or item.id in tombs:
                continue
            svc = Service.from_dict(item.payload)
            _claim_service(claims, svc, item.deleted_at, True, item)
    return claims


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


def _merge_payload_accounts(item: TrashItem, active: list[Account],
                            elsewhere: set[str]) -> None:
    """Дополняет payload удалённого сервиса актуальными записями.

    Если сервис удалили на одном устройстве, а на другом в это время правили
    или добавляли его учётные записи, при слиянии нельзя терять эти правки.

    ``active`` — победившие активные записи этого сервиса; ``elsewhere`` — id
    записей, которые сейчас живут в других сервисах (их из payload удаляем,
    чтобы при восстановлении сервиса не появилось дубликатов). Существующие
    записи payload сохраняются, более новые версии побеждают.
    """
    payload = item.payload if isinstance(item.payload, dict) else {}
    existing: dict[str, dict] = {}
    for acc in payload.get("accounts", []):
        if not isinstance(acc, dict) or not acc.get("id"):
            continue
        if acc["id"] in elsewhere:
            continue  # запись уехала в другой сервис
        existing[acc["id"]] = acc
    for acc in active:
        data = acc.to_dict()
        current = existing.get(acc.id)
        if current is None or data["modified_at"] > current.get("modified_at", 0):
            existing[acc.id] = data
    payload["accounts"] = list(existing.values())
    item.payload = payload


def merge(local: Vault, remote: Vault) -> Vault:
    """Возвращает новое объединённое хранилище."""
    vaults = [local, remote]
    tombs = _tombstone_ids(vaults)

    service_claims = _collect_service_claims(vaults, tombs)
    acc_claims = _collect_account_claims(vaults, tombs)
    trash = _merge_trash(local, remote, tombs)

    # Активные сервисы (победитель по месту — не в корзине).
    services: dict[str, Service] = {}
    for svc, location_ts, in_trash, _item in service_claims.values():
        if in_trash:
            continue
        svc.location_at = location_ts
        services[svc.id] = svc

    # Раскладываем записи по их актуальному месту.
    for acc, service_id, location_ts, in_trash in acc_claims.values():
        if in_trash:
            continue
        service = services.get(service_id)
        if service is None:
            # Сервис исчез (удалён окончательно или перемещён в корзину) —
            # запись не воскрешаем.
            continue
        acc.location_at = location_ts
        service.accounts.append(acc)

    for service in services.values():
        _normalize_order(service.accounts)

    # Синхронизируем корзину сервисов с победившим расположением.
    for svc, location_ts, in_trash, item in service_claims.values():
        if not in_trash:
            # Сервис активен — убираем его возможный след в корзине.
            trash.pop(svc.id, None)
            continue
        entry = trash.get(svc.id)
        if entry is None:
            entry = item if item is not None else TrashItem(
                id=svc.id, kind="service", name=svc.name, payload={})
            trash[svc.id] = entry
        entry.kind = "service"
        entry.name = svc.name
        # Содержимое (название, иконка) берём из победившей версии, но
        # учётные записи не теряем: они лежат в payload удалённого сервиса.
        payload = entry.payload if isinstance(entry.payload, dict) else {}
        payload["id"] = svc.id
        payload["name"] = svc.name
        payload["icon"] = svc.icon
        entry.payload = payload
        entry.modified_at = _max_ts(entry.modified_at, svc.modified_at)
        # Офлайн-правки записей этого сервиса (сделанные на другом устройстве
        # после удаления) не теряем — переносим их в payload корзины.
        active = [acc for acc, sid, _ts, tr in acc_claims.values()
                  if sid == svc.id and not tr]
        elsewhere = {acc.id for acc, sid, _ts, tr in acc_claims.values()
                     if tr or sid != svc.id}
        _merge_payload_accounts(entry, active, elsewhere)

    # Синхронизируем содержимое элементов корзины учётных записей.
    for acc, service_id, location_ts, in_trash in acc_claims.values():
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
