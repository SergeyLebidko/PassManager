"""Сортировка сервисов и учётных записей.

Порядок отображения хранится в самих объектах (поле ``order``) и является
единым для всех устройств: он меняется только явным действием пользователя
(сортировка или перетаскивание) и помечается собственной меткой ``order_at``,
поэтому ручной порядок не конфликтует с правками содержимого при синхронизации.

Пароли в сортировке не участвуют.
"""

from __future__ import annotations

from .models import Account, Service, Vault

# Столбцы, по которым разрешено сортировать учётные записи.
ACCOUNT_SORT_FIELDS = ("title", "login", "comment", "password_changed_at")

ACCOUNT_SORT_LABELS = {
    "title": "Название",
    "login": "Логин",
    "comment": "Комментарий",
    "password_changed_at": "Пароль изменён",
}


def _split_empty(items: list, value) -> tuple[list, list]:
    """Делит элементы на непустые и пустые (пустые всегда идут в конец)."""
    present, empty = [], []
    for item in items:
        (empty if not value(item) else present).append(item)
    return present, empty


def sort_service_ids(services: list[Service], descending: bool = False) -> list[str]:
    """Порядок id сервисов по названию (регистронезависимо).

    Сервисы с пустым названием всегда в конце списка.
    """
    def name_key(svc: Service) -> str:
        return (svc.name or "").strip().lower()

    present, empty = _split_empty(services, name_key)
    present.sort(key=name_key, reverse=descending)
    return [svc.id for svc in present + empty]


def sort_account_ids(service: Service, field: str,
                     descending: bool = False) -> list[str]:
    """Порядок id учётных записей по выбранному столбцу.

    Пустые значения (в том числе отсутствующая дата) всегда в конце.
    Пароль сортировать нельзя.
    """
    if field not in ACCOUNT_SORT_FIELDS:
        raise ValueError(f"Недопустимое поле сортировки: {field!r}")

    if field == "password_changed_at":
        def key(acc: Account) -> float:
            return acc.password_changed_at or 0.0
    else:
        def key(acc: Account) -> str:
            return (getattr(acc, field, "") or "").strip().lower()

    present, empty = _split_empty(service.accounts, key)
    present.sort(key=key, reverse=descending)
    return [acc.id for acc in present + empty]


def apply_service_sort(vault: Vault, descending: bool) -> None:
    """Сортирует сервисы по названию и сохраняет порядок в данных."""
    vault.reorder_services(sort_service_ids(vault.services, descending))


def apply_account_sort(service: Service, field: str, descending: bool) -> None:
    """Сортирует записи сервиса по столбцу и сохраняет порядок в данных."""
    service.reorder(sort_account_ids(service, field, descending))
