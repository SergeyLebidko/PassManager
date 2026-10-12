"""Экспорт данных хранилища в обычный текстовый файл.

Экспортируются только «живые» сервисы и их учётные записи (без корзины).
Пароли выгружаются в открытом виде — файл не шифруется, поэтому его
следует хранить в защищённом месте.
"""

from __future__ import annotations

import time
from pathlib import Path

from . import storage
from .models import Account, Vault, to_date

_SEP = "=" * 66
_SUB = "-" * 66

EXPORT_DIR_NAME = "exports"


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


def export_dir(base_dir: Path | None = None) -> Path:
    """Каталог для экспортированных файлов (по умолчанию рядом с программой)."""
    root = base_dir if base_dir is not None else storage.BASE_DIR
    return Path(root) / EXPORT_DIR_NAME


def export_filename(when: time.struct_time | None = None) -> str:
    """Имя файла экспорта с датой и временем (уникально для каждого экспорта)."""
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S", when if when is not None
                          else time.localtime())
    return f"passmanager-{stamp}.txt"


def write_export(vault: Vault, base_dir: Path | None = None) -> Path:
    """Сохраняет экспорт в каталог exports/ и возвращает путь к файлу.

    Каталог создаётся при необходимости. Имя файла содержит дату и время,
    а при совпадении (например, два экспорта за одну секунду) добавляется
    числовой суффикс — поэтому файлы не перезаписывают друг друга.
    """
    directory = export_dir(base_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / export_filename()
    if path.exists():
        stem = path.stem
        index = 2
        while True:
            candidate = directory / f"{stem}-{index}.txt"
            if not candidate.exists():
                path = candidate
                break
            index += 1
    path.write_text(build_txt(vault), encoding="utf-8")
    return path
