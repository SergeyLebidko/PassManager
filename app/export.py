"""Экспорт данных хранилища в обычный текстовый файл.

Экспортируются только «живые» сервисы и их учётные записи (без корзины).
Пароли выгружаются в открытом виде — файл не шифруется, поэтому его
следует хранить в защищённом месте.
"""

from __future__ import annotations

import time

from .models import Account, Vault, to_date

_SEP = "=" * 66
_SUB = "-" * 66


def _account_lines(acc: Account) -> list[str]:
    lines = [f"  • {acc.title or '(без названия)'}"]
    lines.append(f"      Логин:           {acc.login or '—'}")
    lines.append(f"      Пароль:          {acc.password or '—'}")
    lines.append(f"      Комментарий:     {acc.comment or '—'}")
    lines.append(f"      Создано:         {to_date(acc.created_at)}")
    lines.append(f"      Пароль изменён:  {to_date(acc.password_changed_at)}")
    return lines


def build_txt(vault: Vault) -> str:
    """Формирует текстовое представление всех сервисов и учётных записей."""
    stamp = time.strftime("%d.%m.%Y %H:%M", time.localtime())
    total_accounts = sum(len(s.accounts) for s in vault.services)

    parts: list[str] = [
        "PassManager — экспорт данных",
        f"Дата экспорта: {stamp}",
        f"Сервисов: {len(vault.services)}    Учётных записей: {total_accounts}",
        "",
    ]

    if not vault.services:
        parts.append("(Список сервисов пуст)")
        parts.append("")
        return "\n".join(parts)

    for service in vault.services:
        parts.append(_SEP)
        parts.append(f"СЕРВИС: {service.name or '(без названия)'}")
        parts.append(_SEP)
        parts.append("")
        if not service.accounts:
            parts.append("  (учётных записей нет)")
        else:
            for acc in service.accounts:
                parts.extend(_account_lines(acc))
                parts.append("")
        parts.append("")

    return "\n".join(parts).rstrip("\n") + "\n"
