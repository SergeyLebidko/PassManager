"""Поиск по сервисам и учётным записям.

Поиск регистронезависимый и ищет по подстроке в полях:
    • имя сервиса;
    • название учётной записи;
    • логин;
    • комментарий.

Пароли в поиске не участвуют.
"""

from __future__ import annotations

from .models import Account, Service


def normalize(query: str) -> str:
    """Приводит поисковый запрос к виду для сравнения."""
    return (query or "").strip().lower()


def matching_fields(account: Account, query: str) -> set[str]:
    """Возвращает имена полей записи, в которых найдено совпадение."""
    q = normalize(query)
    result: set[str] = set()
    if not q:
        return result
    if q in (account.title or "").lower():
        result.add("title")
    if q in (account.login or "").lower():
        result.add("login")
    if q in (account.comment or "").lower():
        result.add("comment")
    return result


def account_matches(account: Account, query: str) -> bool:
    """Есть ли совпадение в названии, логине или комментарии записи."""
    return bool(matching_fields(account, query))


def service_name_matches(service: Service, query: str) -> bool:
    """Совпадает ли сам запрос с именем сервиса."""
    q = normalize(query)
    return bool(q) and q in (service.name or "").lower()


def service_matches(service: Service, query: str) -> bool:
    """Показывать ли сервис: совпало имя или хотя бы одна запись."""
    q = normalize(query)
    if not q:
        return True
    if service_name_matches(service, query):
        return True
    return any(account_matches(acc, query) for acc in service.accounts)


def matched_account_count(service: Service, query: str) -> int:
    """Сколько учётных записей сервиса совпало с запросом."""
    q = normalize(query)
    if not q:
        return 0
    return sum(1 for acc in service.accounts if account_matches(acc, query))
