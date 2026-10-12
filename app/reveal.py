"""Открытие каталога в системном файловом менеджере.

После экспорта каталог с файлом открывается в файловом менеджере, а сам
файл по возможности выделяется. Реализация не зависит от внешних
Python-библиотек и деградирует мягко: если показать файл не удалось,
просто пытаемся открыть содержащий его каталог.

Все ошибки подавляются — неудача при показе файла не должна мешать
основной работе программы.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _run(command: list[str]) -> bool:
    """Запускает команду, не дожидаясь её завершения. Не бросает исключений."""
    kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name != "nt":
        # Отсоединяем процесс от нашего (POSIX), чтобы закрытие программы
        # не влияло на файловый менеджер.
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen(command, **kwargs)
        return True
    except (OSError, ValueError):
        return False


def _reveal_windows(path: Path) -> bool:
    # explorer возвращает код 1 даже при успехе, поэтому не проверяем его.
    return _run(["explorer", f"/select,{path}"])


def _reveal_macos(path: Path) -> bool:
    return _run(["open", "-R", str(path)])


def _reveal_linux(path: Path) -> bool:
    if _reveal_linux_dbus(path):
        return True
    if _reveal_linux_gdbus(path):
        return True
    # Резервный вариант: открыть каталог без выделения файла.
    opener = shutil.which("xdg-open")
    if opener:
        return _run([opener, str(path.parent)])
    return False


def _reveal_linux_dbus(path: Path) -> bool:
    """Показывает файл через D-Bus org.freedesktop.FileManager1 (QtDBus)."""
    try:
        from PySide6.QtDBus import QDBusConnection, QDBusMessage
    except ImportError:
        return False
    try:
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return False
        message = QDBusMessage.createMethodCall(
            "org.freedesktop.FileManager1",
            "/org/freedesktop/FileManager1",
            "org.freedesktop.FileManager1",
            "ShowItems",
        )
        message.setArguments([[str(path)], ""])
        reply = bus.call(message, timeout=3000)
        return reply.type() != QDBusMessage.MessageType.ErrorMessage
    except Exception:  # noqa: BLE001
        return False


def _reveal_linux_gdbus(path: Path) -> bool:
    """Резервный показ файла через утилиту gdbus (если нет QtDBus)."""
    gdbus = shutil.which("gdbus")
    if not gdbus:
        return False
    return _run([
        gdbus, "call", "--session",
        "--dest", "org.freedesktop.FileManager1",
        "--object-path", "/org/freedesktop/FileManager1",
        "--method", "org.freedesktop.FileManager1.ShowItems",
        "['" + str(path) + "']", "",
    ])


def reveal_in_file_manager(path: str | os.PathLike[str]) -> bool:
    """Открывает файловый менеджер с выделенным файлом ``path``.

    Возвращает ``True``, если удалось запустить открытие. На Linux, если
    показать файл нельзя, открывает содержащий каталог.
    """
    target = Path(path)
    if sys.platform.startswith("win"):
        return _reveal_windows(target)
    if sys.platform == "darwin":
        return _reveal_macos(target)
    return _reveal_linux(target)
