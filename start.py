#!/usr/bin/env python3
"""PassManager - точка входа.

Запускается двойным кликом по start.py.

Логика:
    1. Проверяет, что запущено под Python 3.
    2. Проверяет наличие зависимостей (PySide6, cryptography, requests).
    3. Если чего-то нет - создаёт локальное виртуальное окружение .venv,
       устанавливает зависимости и перезапускает себя уже из него.
    4. В Windows перезапускается оконным интерпретатором (без консоли).
    5. Запускает графический интерфейс.
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


def _ensure_streams() -> None:
    """Гарантирует наличие ``sys.stdout``/``sys.stderr``.

    В оконном ``pythonw.exe`` стандартные потоки равны ``None``, из-за чего
    любой ``print`` падает с ошибкой. Подменяем их пустышкой.
    """
    devnull = None
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            if devnull is None:
                devnull = open(os.devnull, "w", encoding="utf-8")
            setattr(sys, name, devnull)


def _log(message: str) -> None:
    """Печатает сообщение, если есть куда (в оконном режиме потока нет)."""
    if sys.stdout is not None:
        print(message)


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _running_in_venv() -> bool:
    """Запущены ли из локального окружения ``.venv``.

    Опираемся на ``sys.prefix`` (а не на имя исполняемого файла), потому что
    в Windows окружение может быть запущено и ``python.exe``, и ``pythonw.exe``.
    """
    try:
        return Path(sys.prefix).resolve() == VENV_DIR.resolve()
    except OSError:
        return False


def _is_windowed() -> bool:
    """Запущены ли оконным интерпретатором (``pythonw.exe`` в Windows)."""
    return (os.name == "nt"
            and Path(sys.executable).name.lower() == "pythonw.exe")


def _missing_modules() -> list[str]:
    import importlib.util

    missing = []
    for module in REQUIRED_MODULES:
        if importlib.util.find_spec(module) is None:
            missing.append(module)
    return missing


def _no_window_flags() -> int:
    """Флаги для запуска подпроцесса без консольного окна (Windows)."""
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return 0


def _venv_has_modules(python: Path) -> bool:
    """Проверяет, что в виртуальном окружении есть все зависимости."""
    check = "import " + ", ".join(REQUIRED_MODULES)
    try:
        return subprocess.call(
            [str(python), "-c", check],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=_no_window_flags(),
        ) == 0
    except OSError:
        return False


def _pip_install(python: str, args: list[str]) -> int:
    cmd = [python, "-m", "pip", "install", *args]
    return subprocess.call(cmd, creationflags=_no_window_flags())


def _windowed_python(python: Path) -> Path | None:
    """Ищет оконный ``pythonw.exe``, соответствующий интерпретатору ``python``.

    У ``py.exe`` (лаунчер Windows) рядом может не быть ``pythonw.exe``,
    поэтому дополнительно проверяются базовый интерпретатор окружения и PATH.
    """
    if os.name != "nt":
        return None
    candidates: list[Path] = [python.with_name("pythonw.exe")]
    base = getattr(sys, "_base_executable", None)
    if base:
        candidates.append(Path(base).with_name("pythonw.exe"))
    found = shutil.which("pythonw.exe") or shutil.which("pythonw")
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _relaunch(python: Path) -> NoReturn:
    """Перезапускает программу указанным интерпретатором.

    В Windows выбирается оконный ``pythonw.exe`` (если он есть), чтобы не
    появлялось консольное окно; запуск делается отсоединённым процессом без
    консоли, а текущий процесс завершается. Если оконный интерпретатор не
    найден или задана переменная ``PASSMANAGER_CONSOLE`` — запускается
    обычный. В остальных ОС интерпретатор заменяется напрямую через ``execv``.
    """
    target = python
    detached = False
    if os.name == "nt" and not os.environ.get("PASSMANAGER_CONSOLE"):
        windowed = _windowed_python(python)
        if windowed is not None:
            target = windowed
            detached = True

    args = [str(target), str(BASE_DIR / "start.py"), *sys.argv[1:]]
    if detached:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        try:
            subprocess.Popen(args, creationflags=flags, close_fds=True)
        except OSError:
            os.execv(str(target), args)
        raise SystemExit(0)

    os.execv(str(target), args)


def _ensure_dependencies() -> None:
    """Гарантирует наличие зависимостей.

    Сначала пытается использовать локальное виртуальное окружение .venv,
    а если его создать не удаётся (например, не установлен python3-venv) -
    ставит зависимости в пользовательский каталог и работает с ними.
    """
    if not _missing_modules():
        return

    if _running_in_venv():
        # Уже в venv, но зависимостей не хватает - доустанавливаем.
        _log("PassManager: доустанавливаю зависимости ...")
        if _pip_install(sys.executable, ["-r", str(REQUIREMENTS)]) != 0:
            _fatal("Не удалось установить зависимости. Установите их вручную:\n"
                   "    pip install -r requirements.txt")
        return

    venv_python = _venv_python(VENV_DIR)

    # .venv уже создан: если зависимости на месте - просто перезапускаемся,
    # не запуская pip каждый раз заново.
    if venv_python.exists() and _venv_has_modules(venv_python):
        _log("PassManager: перезапускаю программу из .venv ...")
        _relaunch(venv_python)

    if not venv_python.exists():
        _log("PassManager: создаю виртуальное окружение .venv ...")
        try:
            import venv as venv_module

            venv_module.create(str(VENV_DIR), with_pip=True)
        except Exception as exc:  # noqa: BLE001
            _log(f"PassManager: не удалось создать .venv ({exc}).")

    if venv_python.exists():
        python = str(venv_python)
        _log("PassManager: устанавливаю зависимости в .venv ...")
        _pip_install(python, ["--upgrade", "pip"])
        if _pip_install(python, ["-r", str(REQUIREMENTS)]) == 0:
            _log("PassManager: перезапускаю программу из .venv ...")
            _relaunch(venv_python)

    # Резервный вариант: пользовательская установка без venv.
    _log("PassManager: устанавливаю зависимости для текущего пользователя ...")
    if _pip_install(sys.executable, ["--user", "-r", str(REQUIREMENTS)]) != 0:
        _fatal("Не удалось установить зависимости. Установите их вручную:\n"
               "    pip install -r requirements.txt")

    # Может потребоваться перезапуск, чтобы Python увидел --user пакеты.
    if not _missing_modules():
        return
    _log("PassManager: перезапускаю программу ...")
    _relaunch(Path(sys.executable))


def _switch_to_windowed() -> None:
    """В Windows перезапускает программу без консольного окна.

    Двойной клик по ``start.py`` запускает ``py.exe`` — консольное
    приложение, поэтому появляется окно консоли. Здесь мы перезапускаем
    программу оконным ``pythonw.exe`` и завершаем консольный процесс.

    Перезапуск можно отключить переменной окружения ``PASSMANAGER_CONSOLE``
    (полезно для отладки, когда нужен вывод в консоль).
    """
    if os.name != "nt" or _is_windowed():
        return
    if os.environ.get("PASSMANAGER_CONSOLE"):
        return
    # Если оконного интерпретатора нет, перезапуск привёл бы к бесконечному
    # циклу (тот же консольный процесс запускался бы снова).
    if _windowed_python(Path(sys.executable)) is None:
        return
    _relaunch(Path(sys.executable))


def _pause_on_error() -> None:
    """Ждёт Enter только если есть консольный ввод (иначе просто выходим)."""
    if sys.stdin is None or sys.stdout is None:
        return
    try:
        input("\nНажмите Enter для выхода...")
    except EOFError:
        pass


def _fatal(message: str) -> NoReturn:
    if sys.stderr is not None:
        print("ОШИБКА: " + message, file=sys.stderr)
    _pause_on_error()
    sys.exit(1)


def _preload_local_libs() -> None:
    """Загружает локальные системные библиотеки из каталога libs/.

    Нужно только для Linux: Qt 6.5+ требует libxcb-cursor, которой может не
    быть в системе. Предзагрузка через ctypes позволяет обойтись без прав root.

    В ``libs/`` лежат Linux-библиотеки (формат ELF), поэтому на других ОС
    предзагрузка не выполняется: попытка загрузить ELF-файл в Windows
    приводит к системной ошибке «Bad Image» (0xc000012f).
    """
    if sys.platform != "linux":
        return
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
    if sys.stderr is not None:
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
    _pause_on_error()


def main() -> int:
    _ensure_streams()

    if sys.version_info < (3, 9):
        _fatal("Требуется Python 3.9 или новее.")

    _ensure_dependencies()
    # На Windows убираем консольное окно (перезапуск оконным интерпретатором).
    _switch_to_windowed()
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
