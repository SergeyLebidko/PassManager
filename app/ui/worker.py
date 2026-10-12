"""Фоновые задачи, чтобы не подвешивать интерфейс.

В качестве потоков используются демон-потоки Python, а не ``QThread``.
Это важно: демон-поток не удерживает процесс при выходе, поэтому программу
всегда можно закрыть, даже если сетевой запрос к серверу ещё выполняется
(``QThread`` в такой ситуации приводил к зависанию или падению
«QThread: Destroyed while thread is still running»).

Результаты доставляются в поток интерфейса через сигналы Qt: объект-воркер
создаётся в главном потоке, поэтому подключённые к нему слоты вызываются
в главном потоке автоматически (queued connection).
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal

from ..manager import Manager
from ..webdav import WebDAVClient, WebDAVError

# Живые воркеры удерживаются здесь, чтобы Python не удалил объект, пока
# работает его поток (иначе сигнал может быть отправлен с уже удалённого
# C++-объекта). Запись удаляется по завершении задачи.
_ACTIVE: set["BackgroundWorker"] = set()
_ACTIVE_LOCK = threading.Lock()


def _register(worker: "BackgroundWorker") -> None:
    with _ACTIVE_LOCK:
        _ACTIVE.add(worker)


def _unregister(worker: "BackgroundWorker") -> None:
    with _ACTIVE_LOCK:
        _ACTIVE.discard(worker)


class BackgroundWorker(QObject):
    """Выполняет ``run()`` в отдельном демон-потоке."""

    finished = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        _register(self)
        self._thread = threading.Thread(target=self._run_guarded, daemon=True)
        self._thread.start()

    def _run_guarded(self) -> None:
        try:
            self.run()
        except RuntimeError:
            # Обычно это «Signal source has been deleted»: приложение уже
            # завершается, а фоновый поток ещё жив. Это не ошибка.
            pass
        except Exception:  # noqa: BLE001 - защита от падения потока
            import traceback

            traceback.print_exc()
        finally:
            try:
                self.finished.emit()
            except RuntimeError:
                pass
            _unregister(self)

    def run(self) -> None:  # pragma: no cover - переопределяется
        raise NotImplementedError

    def is_running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    # Совместимость с прежним интерфейсом QThread.
    def isRunning(self) -> bool:  # noqa: N802
        return self.is_running()

    def wait(self, msecs: int = 0) -> bool:
        """Ожидает завершения до ``msecs`` мс. Возвращает True, если поток завершён."""
        thread = self._thread
        if thread is None:
            return True
        thread.join(msecs / 1000 if msecs else None)
        return not thread.is_alive()


class SyncWorker(BackgroundWorker):
    finished_ok = Signal(object)

    def __init__(self, manager: Manager, parent=None) -> None:
        super().__init__(parent)
        self.manager = manager

    def run(self) -> None:
        result = self.manager.try_sync(save_after=False)
        self.finished_ok.emit(result)


class CheckWorker(BackgroundWorker):
    """Проверка подключения к WebDAV в фоне с пошаговым логом.

    Сигналы:
        log(str)             - строка лога (этап проверки).
        finished_check(bool) - True: каталог есть; False: каталог будет создан.
        failed(str)          - текст ошибки.
    """

    log = Signal(str)
    finished_check = Signal(bool)
    failed = Signal(str)

    def __init__(self, url: str, login: str, password: str, parent=None) -> None:
        super().__init__(parent)
        self.url = url
        self.login = login
        self.password = password

    def run(self) -> None:
        try:
            client = WebDAVClient(self.url, self.login, self.password,
                                  logger=self.log.emit)
            exists = client.test()
        except WebDAVError as exc:
            self.log.emit(f"✗ {exc}")
            self.failed.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self.log.emit(f"✗ Непредвиденная ошибка: {exc}")
            self.failed.emit(f"Непредвиденная ошибка: {exc}")
            return
        self.finished_check.emit(exists)
