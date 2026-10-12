#!/usr/bin/env python3
"""PassManager - точка входа.

Запускается двойным кликом по start.py.

Логика:
    1. Проверяет, что запущено под Python 3.
    2. Проверяет наличие зависимостей (PySide6, cryptography, requests).
    3. Если чего-то нет - создаёт локальное виртуальное окружение .venv,
       устанавливает зависимости и перезапускает себя уже из него.
    4. Запускает графический интерфейс.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

BASE_DIR = Path(__file__).resolve().parent
VENV_DIR = BASE_DIR / ".venv"
REQUIREMENTS = BASE_DIR / "requirements.txt"

REQUIRED_MODULES = ("PySide6", "cryptography", "requests")


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _missing_modules() -> list[str]:
    import importlib.util

    missing = []
    for module in REQUIRED_MODULES:
        if importlib.util.find_spec(module) is None:
            missing.append(module)
    return missing


def _pip_install(python: str, args: list[str]) -> int:
    cmd = [python, "-m", "pip", "install", *args]
    return subprocess.call(cmd)


def _ensure_dependencies() -> None:
    """Гарантирует наличие зависимостей.

    Сначала пытается использовать локальное виртуальное окружение .venv,
    а если его создать не удаётся (например, не установлен python3-venv) -
    ставит зависимости в пользовательский каталог и работает с ними.
    """
    missing = _missing_modules()
    if not missing:
        return

    running_in_venv = Path(sys.executable).resolve() == _venv_python(VENV_DIR).resolve()

    if running_in_venv:
        # Уже в venv, но зависимостей не хватает - доустанавливаем.
        print("PassManager: доустанавливаю зависимости ...")
        if _pip_install(sys.executable, ["-r", str(REQUIREMENTS)]) != 0:
            _fatal("Не удалось установить зависимости. Установите их вручную:\n"
                   "    pip install -r requirements.txt")
        return

    venv_ok = _venv_python(VENV_DIR).exists()
    if not venv_ok:
        print("PassManager: создаю виртуальное окружение .venv ...")
        try:
            import venv as venv_module

            venv_module.create(str(VENV_DIR), with_pip=True)
            venv_ok = _venv_python(VENV_DIR).exists()
        except Exception as exc:  # noqa: BLE001
            print(f"PassManager: не удалось создать .venv ({exc}).")
            venv_ok = False

    if venv_ok:
        python = str(_venv_python(VENV_DIR))
        print("PassManager: устанавливаю зависимости в .venv ...")
        _pip_install(python, ["--upgrade", "pip"])
        if _pip_install(python, ["-r", str(REQUIREMENTS)]) == 0:
            print("PassManager: перезапускаю программу из .venv ...")
            os.execv(python, [python, str(BASE_DIR / "start.py"), *sys.argv[1:]])

    # Резервный вариант: пользовательская установка без venv.
    print("PassManager: устанавливаю зависимости для текущего пользователя ...")
    if _pip_install(sys.executable, ["--user", "-r", str(REQUIREMENTS)]) != 0:
        _fatal("Не удалось установить зависимости. Установите их вручную:\n"
               "    pip install -r requirements.txt")

    # Может потребоваться перезапуск, чтобы Python увидел --user пакеты.
    if not _missing_modules():
        return
    print("PassManager: перезапускаю программу ...")
    os.execv(sys.executable, [sys.executable, str(BASE_DIR / "start.py"), *sys.argv[1:]])


def _fatal(message: str) -> NoReturn:
    print("ОШИБКА: " + message, file=sys.stderr)
    try:
        input("\nНажмите Enter для выхода...")
    except EOFError:
        pass
    sys.exit(1)


def _preload_local_libs() -> None:
    """Загружает локальные системные библиотеки из каталога libs/.

    Нужно для Linux: Qt 6.5+ требует libxcb-cursor, которой может не быть
    в системе. Предзагрузка через ctypes позволяет обойтись без прав root.
    """
    libs_dir = BASE_DIR / "libs"
    if not libs_dir.is_dir():
        return
    try:
        import ctypes
    except ImportError:
        return
    for lib in sorted(libs_dir.glob("*.so*")):
        try:
            ctypes.CDLL(str(lib), mode=ctypes.RTLD_GLOBAL)
        except OSError:
            continue


def _report_crash(exc: BaseException) -> None:
    """Показывает сообщение об ошибке, даже при запуске двойным кликом."""
    import traceback

    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    log_path = BASE_DIR / "PassManager-error.log"
    try:
        log_path.write_text(tb, encoding="utf-8")
    except OSError:
        pass

    message = (f"Произошла ошибка при запуске PassManager:\n\n{exc}\n\n"
               f"Подробности сохранены в файле:\n{log_path}")
    print(message, file=sys.stderr)

    # Пытаемся показать окно доступными средствами.
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        if QApplication.instance() is None:
            QApplication(sys.argv)
        QMessageBox.critical(None, "PassManager — ошибка", message)
        return
    except Exception:  # noqa: BLE001
        pass
    for tool in ("zenity", "xmessage"):
        if shutil.which(tool):
            try:
                if tool == "zenity":
                    subprocess.call([tool, "--error", "--text=" + message])
                else:
                    subprocess.call([tool, message])
                return
            except OSError:
                continue
    try:
        input("Нажмите Enter для выхода...")
    except EOFError:
        pass


def main() -> int:
    if sys.version_info < (3, 9):
        _fatal("Требуется Python 3.9 или новее.")

    _ensure_dependencies()
    _preload_local_libs()

    # Импорт после гарантии установки зависимостей.
    from app.ui.main_window import run

    return run()


def _run_guarded() -> int:
    try:
        return main()
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001
        _report_crash(exc)
        return 1


if __name__ == "__main__":
    sys.exit(_run_guarded())
