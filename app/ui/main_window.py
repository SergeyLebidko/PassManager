"""Главное окно PassManager."""

from __future__ import annotations

import sys

from PySide6.QtCore import QLibraryInfo, QTimer, Qt, QTranslator
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .. import storage
from ..crypto import CryptoError, WrongPasswordError
from ..export import write_export
from ..manager import Manager, SyncResult
from ..models import Account, Service, to_date
from ..reveal import reveal_in_file_manager
from . import style
from .icons import make_icon
from .widgets import IconColorButton
from .dialogs import (
    AccountDialog,
    HistoryDialog,
    MasterPasswordDialog,
    ServiceDialog,
    SettingsDialog,
    TrashDialog,
    CLIPBOARD_HINT,
    confirm,
    copy_to_clipboard,
    notify,
)
from .worker import CheckWorker, SyncWorker


class MainWindow(QMainWindow):
    def __init__(self, manager: Manager, app: QApplication) -> None:
        super().__init__()
        self.manager = manager
        self.app = app
        self.dark = False
        self._sync_worker: SyncWorker | None = None
        self._check_worker: CheckWorker | None = None

        self.setWindowTitle("PassManager")
        self.resize(1040, 640)
        self._build_toolbar()
        self._build_ui()
        self.setStatusBar(QStatusBar())
        self._apply_theme()
        self.refresh_services()
        QTimer.singleShot(400, lambda: self.start_sync(manual=False))

    # ------------------------------------------------------------------
    # Построение интерфейса
    # ------------------------------------------------------------------
    def _icon_button(self, icon_name: str, tooltip: str,
                     obj_name: str = "", color: str = "") -> IconColorButton:
        """Компактная кнопка-иконка с всплывающей подсказкой.

        Цветные роли (``primary``/``danger``) окрашиваются только при
        наведении; в покое иконка нейтральна к теме.
        """
        accent = obj_name in ("primary", "danger")
        btn = IconColorButton(icon_name, tooltip, obj_name, accent=accent)
        if color:
            btn.setIcon(make_icon(icon_name, color))
        return btn

    def _recolor_icons(self) -> None:
        """Перекрашивает иконки под цвет текущей темы."""
        color = style.icon_color()
        for btn in self.findChildren(QPushButton):
            if isinstance(btn, IconColorButton):
                btn.refresh_icon()
                continue
            name = btn.property("iconName")
            if name:
                btn.setIcon(make_icon(name, color))

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Менеджер паролей")
        title.setObjectName("titleLabel")
        header.addWidget(title)
        header.addStretch(1)
        self.theme_btn = self._icon_button("moon", "Включить тёмную тему")
        self.theme_btn.clicked.connect(self.toggle_theme)
        header.addWidget(self.theme_btn)
        root.addLayout(header)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, 1)

        # --- Левая панель: сервисы ---
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        search = QLineEdit()
        search.setPlaceholderText("Поиск сервиса...")
        search.textChanged.connect(self._filter_services)
        self.search = search
        left_layout.addWidget(search)

        self.service_list = QListWidget()
        self.service_list.currentItemChanged.connect(self._on_service_selected)
        self.service_list.itemDoubleClicked.connect(lambda _i: self.edit_service())
        left_layout.addWidget(self.service_list, 1)

        svc_buttons = QHBoxLayout()
        svc_buttons.setSpacing(6)
        add_service = self._icon_button("add", "Добавить сервис", "primary")
        add_service.clicked.connect(self.add_service)
        edit_service = self._icon_button("edit", "Изменить сервис")
        edit_service.clicked.connect(self.edit_service)
        del_service = self._icon_button("trash", "Удалить сервис в корзину",
                                        "danger")
        del_service.clicked.connect(self.delete_service)
        svc_buttons.addWidget(add_service)
        svc_buttons.addWidget(edit_service)
        svc_buttons.addWidget(del_service)
        svc_buttons.addStretch(1)
        left_layout.addLayout(svc_buttons)

        # --- Правая панель: учётные записи ---
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self.accounts_label = QLabel("Учётные записи")
        self.accounts_label.setObjectName("subtitleLabel")
        self.accounts_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        right_layout.addWidget(self.accounts_label)

        self.accounts_table = QTableWidget(0, 5)
        self.accounts_table.setHorizontalHeaderLabels(
            ["Название", "Логин", "Пароль", "Комментарий", "Пароль изменён"])
        self.accounts_table.verticalHeader().setVisible(False)
        self.accounts_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.accounts_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.accounts_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.accounts_table.setAlternatingRowColors(True)
        self.accounts_table.doubleClicked.connect(lambda _i: self.edit_account())
        header_view = self.accounts_table.horizontalHeader()
        header_view.setSectionResizeMode(QHeaderView.Interactive)
        header_view.setStretchLastSection(True)
        header_view.setMinimumSectionSize(60)
        header_view.setSectionsMovable(True)
        self.accounts_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        header_view.resizeSection(0, 180)
        header_view.resizeSection(1, 180)
        header_view.resizeSection(2, 120)
        header_view.resizeSection(3, 220)
        header_view.resizeSection(4, 120)
        right_layout.addWidget(self.accounts_table, 1)

        acc_buttons = QHBoxLayout()
        acc_buttons.setSpacing(6)
        add_acc = self._icon_button("add", "Добавить учётную запись",
                                    "primary")
        add_acc.clicked.connect(self.add_account)
        edit_acc = self._icon_button("edit", "Изменить учётную запись")
        edit_acc.clicked.connect(self.edit_account)
        del_acc = self._icon_button("trash", "Удалить учётную запись в корзину",
                                    "danger")
        del_acc.clicked.connect(self.delete_account)
        copy_login = self._icon_button("person", "Копировать логин")
        copy_login.clicked.connect(self.copy_login)
        copy_pass = self._icon_button("key", "Копировать пароль")
        copy_pass.clicked.connect(self.copy_password)
        history = self._icon_button("clock", "История изменений")
        history.clicked.connect(self.show_history)
        acc_buttons.addWidget(add_acc)
        acc_buttons.addWidget(edit_acc)
        acc_buttons.addWidget(del_acc)
        acc_buttons.addStretch(1)
        acc_buttons.addWidget(copy_login)
        acc_buttons.addWidget(copy_pass)
        acc_buttons.addWidget(history)
        right_layout.addLayout(acc_buttons)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 760])

        clipboard_hint = QLabel("🔒 " + CLIPBOARD_HINT + ".")
        clipboard_hint.setObjectName("subtitleLabel")
        clipboard_hint.setWordWrap(True)
        root.addWidget(clipboard_hint)

        self.setCentralWidget(central)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Основные действия")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        settings_action = QAction("Настройки", self)
        settings_action.triggered.connect(self.open_settings)
        toolbar.addAction(settings_action)

        sync_action = QAction("Синхронизировать", self)
        sync_action.setShortcut(QKeySequence("Ctrl+S"))
        sync_action.triggered.connect(lambda: self.start_sync(manual=True))
        toolbar.addAction(sync_action)

        export_action = QAction("Экспорт в TXT", self)
        export_action.triggered.connect(self.export_txt)
        toolbar.addAction(export_action)

        trash_action = QAction("Корзина", self)
        trash_action.triggered.connect(self.open_trash)
        toolbar.addAction(trash_action)

    # ------------------------------------------------------------------
    # Тема
    # ------------------------------------------------------------------
    def _apply_theme(self) -> None:
        style.apply_theme(self.app, self.dark)
        # На светлой теме показываем луну (включить тёмную) и наоборот.
        self.theme_btn.set_icon_name("sun" if self.dark else "moon")
        self.theme_btn.setToolTip("Включить светлую тему" if self.dark
                                  else "Включить тёмную тему")
        self._recolor_icons()
        # Высоту верхних строк считаем только после применения стилей,
        # иначе sizeHint поля поиска занижен (padding ещё не учтён).
        QTimer.singleShot(0, self._align_headers)

    def _align_headers(self) -> None:
        """Выравнивает верхние границы списка сервисов и таблицы записей.

        Слева сверху поле поиска, справа подпись — их высоты должны
        совпадать, иначе списки начинаются на разном уровне.
        """
        self.accounts_label.ensurePolished()
        self.search.ensurePolished()
        row = max(self.search.sizeHint().height(),
                  self.accounts_label.sizeHint().height())
        self.search.setFixedHeight(row)
        self.accounts_label.setFixedHeight(row)

    def toggle_theme(self) -> None:
        self.dark = not self.dark
        self._apply_theme()

    # ------------------------------------------------------------------
    # Список сервисов
    # ------------------------------------------------------------------
    def refresh_services(self, select_id: str | None = None) -> None:
        current_id = select_id
        if current_id is None:
            item = self.service_list.currentItem()
            if item is not None:
                current_id = item.data(Qt.UserRole)

        self.service_list.blockSignals(True)
        self.service_list.clear()
        for svc in self.manager.vault.services:
            count = len(svc.accounts)
            it = QListWidgetItem(f"{svc.name}  ({count})")
            it.setData(Qt.UserRole, svc.id)
            self.service_list.addItem(it)
        self.service_list.blockSignals(False)

        self._filter_services(self.search.text())
        self._restore_selection(current_id)
        if self.service_list.currentItem() is None and self.service_list.count():
            self.service_list.setCurrentRow(0)
        self.refresh_accounts()

    def _restore_selection(self, service_id: str | None) -> None:
        if not service_id:
            return
        for row in range(self.service_list.count()):
            item = self.service_list.item(row)
            if item.data(Qt.UserRole) == service_id:
                self.service_list.setCurrentItem(item)
                return

    def _filter_services(self, text: str) -> None:
        text = (text or "").strip().lower()
        for row in range(self.service_list.count()):
            item = self.service_list.item(row)
            item.setHidden(bool(text) and text not in item.text().lower())

    def current_service(self) -> Service | None:
        item = self.service_list.currentItem()
        if item is None:
            return None
        return self.manager.vault.service(item.data(Qt.UserRole))

    def _on_service_selected(self, *_args) -> None:
        self.refresh_accounts()

    # ------------------------------------------------------------------
    # Таблица учётных записей
    # ------------------------------------------------------------------
    def refresh_accounts(self) -> None:
        service = self.current_service()
        self.accounts_table.setRowCount(0)
        if service is None:
            self.accounts_label.setText("Выберите сервис слева")
            return
        self.accounts_label.setText(f"Учётные записи — {service.name}")

        for acc in service.accounts:
            row = self.accounts_table.rowCount()
            self.accounts_table.insertRow(row)
            title = QTableWidgetItem(acc.title)
            title.setData(Qt.UserRole, acc.id)
            self.accounts_table.setItem(row, 0, title)
            self.accounts_table.setItem(row, 1, QTableWidgetItem(acc.login))
            self.accounts_table.setItem(row, 2, QTableWidgetItem("•" * min(len(acc.password), 12) or "—"))
            self.accounts_table.setItem(row, 3, QTableWidgetItem(acc.comment))
            self.accounts_table.setItem(row, 4, QTableWidgetItem(to_date(acc.password_changed_at)))

    def current_account(self) -> Account | None:
        service = self.current_service()
        if service is None:
            return None
        row = self.accounts_table.currentRow()
        if row < 0:
            return None
        item = self.accounts_table.item(row, 0)
        if item is None:
            return None
        return service.account(item.data(Qt.UserRole))

    def _require_service(self) -> Service | None:
        service = self.current_service()
        if service is None:
            notify(self, "PassManager",
                   "Сначала создайте или выберите сервис.")
        return service

    # ------------------------------------------------------------------
    # Операции с сервисами
    # ------------------------------------------------------------------
    def add_service(self) -> None:
        dlg = ServiceDialog(parent=self)
        if dlg.exec():
            service = Service(name=dlg.value())
            self.manager.vault.services.append(service)
            self.manager.vault.services.sort(key=lambda s: s.name.lower())
            self._persist()
            self.refresh_services(select_id=service.id)
            self.set_status("Сервис добавлен.")

    def edit_service(self) -> None:
        service = self.current_service()
        if service is None:
            return
        dlg = ServiceDialog(service, parent=self)
        if dlg.exec():
            service.name = dlg.value()
            service.touch()
            self.manager.vault.services.sort(key=lambda s: s.name.lower())
            self._persist()
            self.refresh_services(select_id=service.id)
            self.set_status("Сервис переименован.")

    def delete_service(self) -> None:
        service = self.current_service()
        if service is None:
            return
        if not confirm(
            self, "Удаление сервиса",
            f"Переместить сервис «{service.name}» и все его учётные записи "
            f"({len(service.accounts)}) в корзину?",
        ):
            return
        self.manager.vault.trash_service(service)
        self._persist()
        self.refresh_services()
        self.set_status("Сервис перемещён в корзину.")

    # ------------------------------------------------------------------
    # Операции с учётными записями
    # ------------------------------------------------------------------
    def add_account(self) -> None:
        service = self._require_service()
        if service is None:
            return
        dlg = AccountDialog(service_name=service.name, parent=self)
        if dlg.exec():
            acc = Account(**dlg.result_data)
            service.accounts.append(acc)
            service.touch()
            self._persist()
            self.refresh_services(select_id=service.id)
            self.set_status("Учётная запись добавлена.")

    def edit_account(self) -> None:
        service = self.current_service()
        account = self.current_account()
        if service is None or account is None:
            return
        dlg = AccountDialog(account, service_name=service.name, parent=self)
        if dlg.exec():
            data = dlg.result_data
            # История фиксируется до изменений, чтобы сохранить прежнее
            # состояние записи (каждое изменение — отдельная запись истории).
            account.change_title(data["title"])
            account.change_login(data["login"])
            account.change_password(data["password"])
            account.change_comment(data["comment"])
            service.touch()
            self._persist()
            self.refresh_services(select_id=service.id)
            self.set_status("Учётная запись сохранена.")

    def delete_account(self) -> None:
        service = self.current_service()
        account = self.current_account()
        if service is None or account is None:
            return
        name = account.title or account.login
        if not confirm(
            self, "Удаление учётной записи",
            f"Переместить учётную запись «{name}» в корзину?",
        ):
            return
        self.manager.vault.trash_account(service, account)
        self._persist()
        self.refresh_services(select_id=service.id)
        self.set_status("Учётная запись перемещена в корзину.")

    # ------------------------------------------------------------------
    # Копирование
    # ------------------------------------------------------------------
    def copy_login(self) -> None:
        account = self.current_account()
        if account is None:
            return
        if not account.login:
            self.set_status("У учётной записи нет логина.")
            return
        copy_to_clipboard(account.login, owner=self)
        self.set_status("Логин скопирован. " + CLIPBOARD_HINT + ".")

    def copy_password(self) -> None:
        account = self.current_account()
        if account is None:
            return
        if not account.password:
            self.set_status("У учётной записи нет пароля.")
            return
        copy_to_clipboard(account.password, owner=self)
        self.set_status("Пароль скопирован. " + CLIPBOARD_HINT + ".")

    # ------------------------------------------------------------------
    # История
    # ------------------------------------------------------------------
    def show_history(self) -> None:
        account = self.current_account()
        if account is None:
            notify(self, "История", "Выберите учётную запись.")
            return
        HistoryDialog(account, parent=self).exec()

    # ------------------------------------------------------------------
    # Корзина
    # ------------------------------------------------------------------
    def open_trash(self) -> None:
        while True:
            items = list(self.manager.vault.trash)
            dlg = TrashDialog(items, parent=self)
            if not dlg.exec():
                break
            if dlg.action == "restore":
                self._trash_restore(dlg.selected_id)
            elif dlg.action == "delete":
                self._trash_delete(dlg.selected_id)
            elif dlg.action == "clear":
                if self._trash_clear():
                    break

    def _trash_restore(self, item_id: str | None) -> None:
        item = next((t for t in self.manager.vault.trash if t.id == item_id), None)
        if item is None:
            return
        self.manager.vault.restore(item)
        self._persist()
        self.refresh_services()
        self.set_status(f"Восстановлено: {item.name}")

    def _trash_delete(self, item_id: str | None) -> None:
        item = next((t for t in self.manager.vault.trash if t.id == item_id), None)
        if item is None:
            return
        if not confirm(
            self, "Удаление навсегда",
            f"Удалить «{item.name}» навсегда? Восстановить будет невозможно.",
        ):
            return
        self.manager.vault.purge(item)
        self._persist()
        self.set_status("Элемент удалён навсегда.")

    def _trash_clear(self) -> bool:
        if not self.manager.vault.trash:
            return True
        if not confirm(
            self, "Очистка корзины",
            "Удалить все элементы корзины навсегда?",
        ):
            return False
        count = self.manager.vault.clear_trash()
        self._persist()
        self.set_status(f"Корзина очищена ({count}).")
        return True

    # ------------------------------------------------------------------
    # Экспорт
    # ------------------------------------------------------------------
    def export_txt(self) -> None:
        if not self.manager.vault.services:
            notify(self, "Экспорт", "Нет сервисов для экспорта.")
            return
        try:
            path = write_export(self.manager.vault)
        except OSError as exc:
            notify(self, "Ошибка экспорта", f"Не удалось записать файл:\n{exc}",
                   QMessageBox.Critical)
            return
        reveal_in_file_manager(path)
        self.set_status(f"Данные экспортированы: {path}")
        notify(self, "Экспорт завершён",
               "Данные сохранены в файл:\n"
               f"{path}\n\n"
               "ВНИМАНИЕ: пароли в файле хранятся в открытом виде. "
               "Храните его в защищённом месте.")

    # ------------------------------------------------------------------
    # Настройки
    # ------------------------------------------------------------------
    def open_settings(self) -> None:
        dlg = SettingsDialog(
            self.manager.webdav_url,
            self.manager.config.get("webdav_login", ""),
            self.manager.server_password(),
            self.manager.config.get("autosync", True),
            parent=self,
        )
        dlg.test_btn.clicked.connect(lambda: self._test_connection(dlg))
        if dlg.exec():
            values = dlg.values()
            self.manager.update_server_settings(
                values["url"], values["login"], values["password"])
            self.manager.config["autosync"] = values["autosync"]
            storage.save_config(self.manager.config)
            self.set_status("Настройки сохранены.")

    def _test_connection(self, dlg: SettingsDialog) -> None:
        values = dlg.values()
        dlg.begin_check()
        # Без Qt-родителя: объект удерживается реестром в worker.py, пока
        # поток работает, поэтому закрытие окна его не удаляет.
        worker = CheckWorker(values["url"], values["login"], values["password"])
        self._check_worker = worker
        # Ссылка нужна диалогу, чтобы при закрытии отключить сигналы.
        dlg._check_worker = worker

        worker.log.connect(dlg.append_log)
        worker.finished_check.connect(
            lambda exists: dlg.end_check(
                True,
                "Подключение успешно, каталог доступен." if exists
                else "Подключение успешно, каталог будет создан при синхронизации."))
        worker.failed.connect(lambda msg: dlg.end_check(False, msg))

        def _cleanup() -> None:
            if self._check_worker is worker:
                self._check_worker = None
            worker.deleteLater()

        worker.finished.connect(_cleanup)
        worker.start()

    # ------------------------------------------------------------------
    # Синхронизация
    # ------------------------------------------------------------------
    def start_sync(self, manual: bool = False) -> None:
        if self._sync_worker is not None and self._sync_worker.isRunning():
            if manual:
                self.set_status("Синхронизация уже выполняется...")
            return
        self.set_status("Синхронизация...")
        self._sync_worker = SyncWorker(self.manager)
        self._sync_worker.finished_ok.connect(self._on_sync_done)
        self._sync_worker.start()

    def _schedule_sync(self) -> None:
        """Отложенная фоновая синхронизация после изменения данных."""
        if self.manager.autosync_enabled():
            QTimer.singleShot(300, lambda: self.start_sync(manual=False))

    def closeEvent(self, event) -> None:  # noqa: N802
        # Работающие фоновые задачи — демон-потоки, поэтому не мешают выходу.
        # Даём им короткий шанс завершиться, но не блокируем закрытие.
        for worker in (self._sync_worker, self._check_worker):
            if worker is not None and worker.is_running():
                worker.wait(1000)
        self.manager.save_local()
        super().closeEvent(event)

    def _on_sync_done(self, result: SyncResult) -> None:
        self.refresh_services()
        if result.remote_available:
            prefix = "✓ " if result.ok else "⚠ "
        else:
            prefix = "• "
        self.set_status(prefix + result.message)

    # ------------------------------------------------------------------
    # Статус
    # ------------------------------------------------------------------
    def set_status(self, text: str) -> None:
        self.statusBar().showMessage(text)

    def _persist(self) -> None:
        """Сохраняет локальную копию и, при необходимости, синхронизирует в фоне."""
        self.manager.save_local()
        self._schedule_sync()


def _install_russian_translation(app: QApplication) -> None:
    """Подключает русский перевод стандартных строк Qt (диалоги и т.п.)."""
    path = QLibraryInfo.path(QLibraryInfo.TranslationsPath)
    for name in ("qtbase_ru", "qt_ru"):
        translator = QTranslator(app)
        if translator.load(name, path):
            app.installTranslator(translator)
            app._ru_translator = translator  # держим ссылку, чтобы не собрался GC


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("PassManager")
    app.setStyle("Fusion")
    _install_russian_translation(app)
    # Тема применяется до открытия диалогов (в т.ч. ввода мастер-пароля),
    # иначе они выглядят в стандартном стиле Fusion.
    style.apply_theme(app, False)

    manager = Manager()

    if manager.has_local():
        dlg = MasterPasswordDialog(creating=False)
        while dlg.exec():
            try:
                manager.unlock(dlg.password)
                break
            except WrongPasswordError:
                notify(None, "Разблокировка",
                       "Неверный мастер-пароль. Попробуйте снова.",
                       QMessageBox.Critical)
                dlg = MasterPasswordDialog(creating=False)
            except CryptoError as exc:
                notify(None, "Ошибка", str(exc), QMessageBox.Critical)
                return 1
        else:
            return 0
    else:
        dlg = MasterPasswordDialog(creating=True)
        if not dlg.exec():
            return 0
        manager.create_new(dlg.password)

    manager.set_password(dlg.password)

    window = MainWindow(manager, app)
    window.show()
    return app.exec()
