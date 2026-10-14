"""Сортировка сервисов и учётных записей.

Порядок отображения — это только представление: он вычисляется при
отрисовке списков и нигде не хранится, поэтому не синхронизируется между
устройствами. При открытии программы сервисы и записи показываются
отсортированными по алфавиту (А→Я).

Пароли в сортировке не участвуют.
"""

from __future__ import annotations

from .models import Account, Service

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


def sort_services(services: list[Service],
                  descending: bool = False) -> list[Service]:
    """Список сервисов по названию (регистронезависимо).

    Сервисы с пустым названием всегда в конце списка.
    """
    def name_key(svc: Service) -> str:
        return (svc.name or "").strip().lower()

    present, empty = _split_empty(services, name_key)
    present.sort(key=name_key, reverse=descending)
    return present + empty


def sort_accounts(accounts: list[Account], field: str,
                  descending: bool = False) -> list[Account]:
    """Список учётных записей по выбранному столбцу.

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

    present, empty = _split_empty(accounts, key)
    present.sort(key=key, reverse=descending)
    return present + empty
