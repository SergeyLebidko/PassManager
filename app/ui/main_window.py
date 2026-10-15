"""Главное окно PassManager."""

from __future__ import annotations

import sys

from PySide6.QtCore import QLibraryInfo, QSize, QTimer, Qt, QTranslator
from PySide6.QtGui import QAction, QBrush, QColor, QKeySequence
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
from ..models import Account, Service, to_iso
from ..reveal import reveal_in_file_manager
from .. import order as order_mod
from .. import search as search_mod
from . import style
from .icons import make_icon
from .widgets import IconColorButton
from .dialogs import (
    AccountDialog,
    AdoptRemotePasswordDialog,
    ChangeMasterPasswordDialog,
    HistoryDialog,
    MasterPasswordDialog,
    ServiceDialog,
    SettingsDialog,
    CLIPBOARD_HINT,
    confirm,
    copy_to_clipboard,
    notify,
)
from .worker import (
    AdoptRemoteWorker,
    ChangePasswordWorker,
    CheckWorker,
    SyncWorker,
)


class MainWindow(QMainWindow):
    def __init__(self, manager: Manager, app: QApplication) -> None:
        super().__init__()
        self.manager = manager
        self.app = app
        self.dark = False
        self._sync_worker: SyncWorker | None = None
        self._check_worker: CheckWorker | None = None
        self._change_worker: ChangePasswordWorker | None = None
        self._adopt_worker: AdoptRemoteWorker | None = None
        # Запрос нового пароля удалённой копии: показываем один раз за запуск
        # при автоматической синхронизации (при ручной — всегда).
        self._adopt_prompted = False
        self._adopt_dialog_open = False
        # Была ли последняя синхронизация ручной (нужно для запроса пароля).
        self._sync_manual = False
        # Новый пароль, ожидающий подтверждения перезаписи серверной копии.
        self._pending_change_password = ""
        # Текущее состояние сортировки (в памяти окна, не синхронизируется).
        # По умолчанию — по алфавиту А→Я.
        self._service_sort_desc = False
        self._account_sort_field = "title"
        self._account_sort_desc = False

        self.setWindowTitle("PassManager")
        self.resize(1040, 640)
        self._build_toolbar()
        self._build_ui()
        self.setStatusBar(QStatusBar())
        self._apply_theme()
        self.refresh_services()
        self._update_service_sort_button()
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
        search.setPlaceholderText("Поиск по сервисам, логинам, комментариям...")
        search.textChanged.connect(self._filter_services)
        self.search = search
        left_layout.addWidget(search)

        self.service_list = QListWidget()
        self.service_list.setIconSize(QSize(18, 18))
        self.service_list.currentItemChanged.connect(self._on_service_selected)
        self.service_list.itemDoubleClicked.connect(lambda _i: self.edit_service())
        left_layout.addWidget(self.service_list, 1)

        svc_buttons = QHBoxLayout()
        svc_buttons.setSpacing(6)
        add_service = self._icon_button("add", "Добавить сервис", "primary")
        add_service.clicked.connect(self.add_service)
        edit_service = self._icon_button("edit", "Изменить сервис")
        edit_service.clicked.connect(self.edit_service)
        del_service = self._icon_button("trash", "Удалить сервис",
                                        "danger")
        del_service.clicked.connect(self.delete_service)
        self.tv_sort_btn = self._icon_button("arrow-up-down",
                                             "Сортировать по алфавиту")
        self.tv_sort_btn.clicked.connect(self.sort_services)
        svc_buttons.addWidget(add_service)
        svc_buttons.addWidget(edit_service)
        svc_buttons.addWidget(del_service)
        svc_buttons.addStretch(1)
        svc_buttons.addWidget(self.tv_sort_btn)
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
            ["Название", "Логин", "Пароль", "Пароль изменён", "Комментарий"])
        self.accounts_table.verticalHeader().setVisible(False)
        self.accounts_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.accounts_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.accounts_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.accounts_table.setAlternatingRowColors(True)
        self.accounts_table.setIconSize(QSize(18, 18))
        self.accounts_table.doubleClicked.connect(lambda _i: self.edit_account())
        header_view = self.accounts_table.horizontalHeader()
        header_view.setSectionResizeMode(QHeaderView.Interactive)
        header_view.setStretchLastSection(True)
        header_view.setMinimumSectionSize(60)
        header_view.setSectionsMovable(True)
        header_view.setSectionsClickable(True)
        header_view.sectionClicked.connect(self._on_header_clicked)
        self.accounts_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        header_view.resizeSection(0, 180)
        header_view.resizeSection(1, 180)
        header_view.resizeSection(2, 120)
        header_view.resizeSection(3, 140)
        header_view.resizeSection(4, 220)
        right_layout.addWidget(self.accounts_table, 1)

        acc_buttons = QHBoxLayout()
        acc_buttons.setSpacing(6)
        add_acc = self._icon_button("add", "Добавить учётную запись",
                                    "primary")
        add_acc.clicked.connect(self.add_account)
        edit_acc = self._icon_button("edit", "Изменить учётную запись")
        edit_acc.clicked.connect(self.edit_account)
        del_acc = self._icon_button("trash", "Удалить учётную запись",
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
        # Пересчитываем подсветку поиска и иконки под новые цвета темы.
        self.refresh_services(select_id=self._selected_service_id())
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
        color = style.icon_color()
        for svc in order_mod.sort_services(list(self.manager.vault.services),
                                           self._service_sort_desc):
            count = len(svc.accounts)
            it = QListWidgetItem(f"{svc.name}  ({count})")
            it.setData(Qt.UserRole, svc.id)
            if svc.icon:
                it.setIcon(make_icon(svc.icon, color))
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
            if item.data(Qt.UserRole) == service_id and not item.isHidden():
                self.service_list.setCurrentItem(item)
                return

    def _filter_services(self, text: str) -> None:
        """Скрывает несовпавшие сервисы и подсвечивает найденное."""
        query = search_mod.normalize(text)
        for row in range(self.service_list.count()):
            item = self.service_list.item(row)
            service = self.manager.vault.service(item.data(Qt.UserRole))
            if service is None or not query:
                item.setHidden(False)
                self._set_service_highlight(item, False)
                continue
            matched = search_mod.service_matches(service, query)
            item.setHidden(not matched)
            # Подсвечиваем сервис при любом совпадении — и по имени,
            # и по полям входящих в него учётных записей.
            self._set_service_highlight(item, matched)

        # Если текущий сервис скрыт запросом, выбираем первый видимый.
        current = self.service_list.currentItem()
        if current is not None and current.isHidden():
            self._select_first_visible()
        self.refresh_accounts()

    def _set_service_highlight(self, item: QListWidgetItem, matched: bool) -> None:
        """Подсвечивает элемент списка сервисов при совпадении с запросом."""
        font = item.font()
        font.setBold(matched)
        item.setFont(font)
        if matched:
            item.setBackground(QBrush(QColor(style.highlight_color())))
            item.setForeground(QBrush(QColor(style.highlight_text_color())))
        else:
            item.setBackground(QBrush(Qt.NoBrush))
            item.setForeground(QBrush(Qt.NoBrush))

    def _select_first_visible(self) -> None:
        for row in range(self.service_list.count()):
            item = self.service_list.item(row)
            if not item.isHidden():
                self.service_list.setCurrentItem(item)
                return

    def current_service(self) -> Service | None:
        item = self.service_list.currentItem()
        if item is None:
            return None
        return self.manager.vault.service(item.data(Qt.UserRole))

    def _on_service_selected(self, *_args) -> None:
        # Сортировка записей не привязана к сервису: при переключении
        # сохраняем выбранное поле и направление.
        self.refresh_accounts()

    # ------------------------------------------------------------------
    # Таблица учётных записей
    # ------------------------------------------------------------------
    def refresh_accounts(self, select_id: str | None = None) -> None:
        service = self.current_service()
        self.accounts_table.setRowCount(0)
        if service is None:
            self.accounts_label.setText("Выберите сервис слева")
            self._update_sort_headers()
            return
        self.accounts_label.setText(f"Учётные записи — {service.name}")

        query = search_mod.normalize(self.search.text()
                                     if hasattr(self, "search") else "")
        # Если совпадений в сервисе нет вовсе (например, сервис совпал
        # только по имени), показываем все его записи.
        service_matched_by_name = bool(
            query and search_mod.service_name_matches(service, query))
        accounts = order_mod.sort_accounts(list(service.accounts),
                                           self._account_sort_field,
                                           self._account_sort_desc)
        for acc in accounts:
            fields = search_mod.matching_fields(acc, query) if query else set()
            # Прячем записи без совпадений, кроме случая, когда сервис
            # целиком совпал по имени.
            if query and not fields and not service_matched_by_name:
                continue
            row = self.accounts_table.rowCount()
            self.accounts_table.insertRow(row)
            title = QTableWidgetItem(acc.title)
            title.setData(Qt.UserRole, acc.id)
            if acc.icon:
                title.setIcon(make_icon(acc.icon, style.icon_color()))
            self.accounts_table.setItem(row, 0, title)
            self.accounts_table.setItem(row, 1, QTableWidgetItem(acc.login))
            self.accounts_table.setItem(row, 2, QTableWidgetItem("•" * min(len(acc.password), 12) or "—"))
            self.accounts_table.setItem(row, 3, QTableWidgetItem(to_iso(acc.password_changed_at)))
            self.accounts_table.setItem(row, 4, QTableWidgetItem(acc.comment))
            self._highlight_account_row(row, acc, query)
        self._restore_account_selection(select_id)
        self._update_sort_headers()

    def _restore_account_selection(self, account_id: str | None) -> None:
        if not account_id:
            return
        for row in range(self.accounts_table.rowCount()):
            item = self.accounts_table.item(row, 0)
            if item is not None and item.data(Qt.UserRole) == account_id:
                self.accounts_table.setCurrentCell(row, 0)
                return

    def _highlight_account_row(self, row: int, acc: Account, query: str) -> None:
        """Подсвечивает совпавшие с запросом поля учётной записи."""
        fields = search_mod.matching_fields(acc, query)
        if not fields:
            return
        color = QBrush(QColor(style.highlight_color()))
        text = QBrush(QColor(style.highlight_text_color()))
        columns = {"title": 0, "login": 1, "comment": 4}
        for field, column in columns.items():
            if field not in fields:
                continue
            item = self.accounts_table.item(row, column)
            if item is None:
                continue
            item.setBackground(color)
            item.setForeground(text)
            font = item.font()
            font.setBold(True)
            item.setFont(font)

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

    def _require_account(self) -> Account | None:
        account = self.current_account()
        if account is None:
            notify(self, "PassManager", "Выберите учётную запись.")
        return account

    # ------------------------------------------------------------------
    # Операции с сервисами
    # ------------------------------------------------------------------
    def add_service(self) -> None:
        dlg = ServiceDialog(parent=self)
        if dlg.exec():
            service = Service(name=dlg.value(), icon=dlg.icon_value())
            self.manager.vault.add_service(service)
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
            service.icon = dlg.icon_value()
            service.touch()
            self._persist()
            self.refresh_services(select_id=service.id)
            self.set_status("Сервис сохранён.")

    def delete_service(self) -> None:
        service = self.current_service()
        if service is None:
            return
        if not confirm(
            self, "Удаление сервиса",
            f"Удалить сервис «{service.name}» и все его учётные записи "
            f"({len(service.accounts)})? Действие необратимо.",
        ):
            return
        self.manager.vault.delete_service(service)
        self._persist()
        self.refresh_services()
        self.set_status("Сервис удалён.")

    # ------------------------------------------------------------------
    # Операции с учётными записями
    # ------------------------------------------------------------------
    def add_account(self) -> None:
        service = self._require_service()
        if service is None:
            return
        dlg = AccountDialog(service_name=service.name, parent=self)
        if dlg.exec():
            data = dlg.result_data
            acc = Account(title=data["title"], login=data["login"],
                          password=data["password"], comment=data["comment"],
                          icon=data.get("icon", ""))
            service.add_account(acc)
            service.touch()
            self._persist()
            self.refresh_services(select_id=service.id)
            self.refresh_accounts(select_id=acc.id)
            self.set_status("Учётная запись добавлена.")

    def edit_account(self) -> None:
        account = self._require_account()
        if account is None:
            return
        service = self.current_service()
        dlg = AccountDialog(account, service_name=service.name, parent=self)
        if dlg.exec():
            data = dlg.result_data
            # История фиксируется до изменений, чтобы сохранить прежнее
            # состояние записи (каждое изменение — отдельная запись истории).
            account.change_title(data["title"])
            account.change_login(data["login"])
            account.change_password(data["password"])
            account.change_comment(data["comment"])
            # Иконка — не поле журнала, но её изменение синхронизируется,
            # поэтому просто обновляем и поднимаем modified_at.
            new_icon = data.get("icon", "")
            if new_icon != account.icon:
                account.icon = new_icon
                account.touch()
            service.touch()
            self._persist()
            self.refresh_services(select_id=service.id)
            self.refresh_accounts(select_id=account.id)
            self.set_status("Учётная запись сохранена.")

    def delete_account(self) -> None:
        account = self._require_account()
        if account is None:
            return
        service = self.current_service()
        name = account.title or account.login
        if not confirm(
            self, "Удаление учётной записи",
            f"Удалить учётную запись «{name}»? Действие необратимо.",
        ):
            return
        self.manager.vault.delete_account(service, account)
        self._persist()
        self.refresh_services(select_id=service.id)
        self.set_status("Учётная запись удалена.")

    # ------------------------------------------------------------------
    # Сортировка
    # ------------------------------------------------------------------
    def sort_services(self) -> None:
        """Сортирует сервисы по алфавиту, переключая направление.

        Порядок — только отображение: в данных он не хранится и не
        синхронизируется.
        """
        self._service_sort_desc = not self._service_sort_desc
        self.refresh_services(select_id=self._selected_service_id())
        self._update_service_sort_button()
        self.set_status("Сервисы отсортированы "
                        + ("по убыванию." if self._service_sort_desc
                           else "по возрастанию."))

    def _update_service_sort_button(self) -> None:
        icon = "arrow-up" if self._service_sort_desc else "arrow-down"
        self.tv_sort_btn.set_icon_name(icon)
        direction = "Я→А" if self._service_sort_desc else "А→Я"
        self.tv_sort_btn.setToolTip(f"Сортировать по алфавиту ({direction})")

    def _selected_service_id(self) -> str | None:
        service = self.current_service()
        return service.id if service is not None else None

    # Столбец таблицы -> поле сортировки (Пароль не сортируется).
    _ACCOUNT_SORT_COLUMNS = {
        0: "title",
        1: "login",
        3: "password_changed_at",
        4: "comment",
    }

    def _on_header_clicked(self, column: int) -> None:
        """Сортирует записи по клику на заголовок столбца."""
        field = self._ACCOUNT_SORT_COLUMNS.get(column)
        if field is None:
            return  # столбец «Пароль» не сортируется
        service = self.current_service()
        if service is None:
            return
        # Повторный клик по тому же столбцу меняет направление.
        descending = (not self._account_sort_desc
                      if field == self._account_sort_field else False)
        self.sort_accounts(field, descending)

    def sort_accounts(self, field: str, descending: bool = False) -> None:
        service = self._require_service()
        if service is None:
            return
        self._account_sort_field = field
        self._account_sort_desc = descending
        current = self.current_account()
        self.refresh_accounts(select_id=current.id if current else None)
        direction = "по убыванию" if descending else "по возрастанию"
        self.set_status("Записи отсортированы по полю «"
                        + order_mod.ACCOUNT_SORT_LABELS[field]
                        + "» " + direction + ".")

    def _update_sort_headers(self) -> None:
        """Показывает направление сортировки прямо в заголовках столбцов."""
        labels = ["Название", "Логин", "Пароль", "Пароль изменён", "Комментарий"]
        for column, label in enumerate(labels):
            marker = ""
            if (self._account_sort_field is not None
                    and self._ACCOUNT_SORT_COLUMNS.get(column)
                    == self._account_sort_field):
                marker = " ↑" if self._account_sort_desc else " ↓"
            item = self.accounts_table.horizontalHeaderItem(column)
            if item is not None:
                item.setText(label + marker)

    # ------------------------------------------------------------------
    # Копирование
    # ------------------------------------------------------------------
    def copy_login(self) -> None:
        account = self._require_account()
        if account is None:
            return
        if not account.login:
            self.set_status("У учётной записи нет логина.")
            return
        copy_to_clipboard(account.login, owner=self)
        self.set_status("Логин скопирован. " + CLIPBOARD_HINT + ".")

    def copy_password(self) -> None:
        account = self._require_account()
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
        account = self._require_account()
        if account is None:
            return
        HistoryDialog(account, parent=self).exec()

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
            parent=self,
        )
        dlg.test_btn.clicked.connect(lambda: self._test_connection(dlg))
        dlg.change_password_btn.clicked.connect(
            lambda: self.change_master_password(dlg))
        if dlg.exec():
            values = dlg.values()
            self.manager.update_server_settings(
                values["url"], values["login"], values["password"])
            storage.save_config(self.manager.config)
            # Как только адрес сервера задан — сразу проверяем креды и
            # обмениваемся копиями (кнопка «Проверить подключение» данные не
            # трогает).
            if self.manager.webdav_url.strip():
                self.set_status("Настройки сохранены. Синхронизация...")
                self.start_sync(manual=True)
            else:
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
    # Смена мастер-пароля
    # ------------------------------------------------------------------
    def change_master_password(self, parent=None) -> None:
        """Открывает под-диалог и запускает фоновую смену мастер-пароля."""
        ui_parent = parent or self
        if self._change_worker is not None and self._change_worker.is_running():
            notify(ui_parent, "PassManager",
                   "Смена мастер-пароля уже выполняется.")
            return
        if self._sync_worker is not None and self._sync_worker.isRunning():
            notify(ui_parent, "PassManager",
                   "Дождитесь окончания синхронизации и попробуйте снова.")
            return
        dlg = ChangeMasterPasswordDialog(self.manager.check_password,
                                         parent=ui_parent)
        if not dlg.exec():
            return
        self.set_status("Смена мастер-пароля и синхронизация...")
        self._pending_change_password = dlg.new_password
        self._change_worker = ChangePasswordWorker(
            self.manager, dlg.new_password)
        self._change_worker.finished_ok.connect(self._on_change_done)
        self._change_worker.start()

    def _on_change_done(self, result: SyncResult) -> None:
        self.refresh_services()
        # «Настройки» могут быть ещё открыты — показываем окно поверх активного
        # модального диалога, а если его нет — поверх главного окна.
        parent = QApplication.activeModalWidget() or self
        # Серверная копия зашифрована третьим паролем и не открывается новым:
        # спрашиваем разрешение на перезапись, прежде чем потерять серверные
        # данные.
        if result.needs_overwrite:
            if confirm(parent, "Смена мастер-пароля",
                       "Удалённая копия зашифрована другим мастер-паролем и не "
                       "открывается новым. Продолжить с перезаписью серверной "
                       "копии? Изменения с сервера могут быть потеряны."):
                password = self._pending_change_password
                self.set_status("Смена мастер-пароля и синхронизация...")
                self._change_worker = ChangePasswordWorker(
                    self.manager, password, allow_overwrite=True)
                self._change_worker.finished_ok.connect(self._on_change_done)
                self._change_worker.start()
            else:
                notify(parent, "Смена мастер-пароля",
                       "Смена пароля отменена: серверная копия не тронута.")
                self.set_status("Смена мастер-пароля отменена.")
            return
        if result.remote_available:
            notify(parent, "Мастер-пароль изменён", result.message)
            self.set_status("✓ " + result.message)
        else:
            notify(parent, "Мастер-пароль изменён",
                   result.message, QMessageBox.Warning)
            self.set_status("• " + result.message)

    # ------------------------------------------------------------------
    # Слияние с серверной копией под другим мастер-паролем
    # ------------------------------------------------------------------
    def _offer_adopt_remote(self) -> None:
        """Просит новый мастер-пароль и сливает серверные данные с локальными."""
        if self._adopt_dialog_open:
            return
        for worker in (self._adopt_worker, self._change_worker):
            if worker is not None and worker.is_running():
                return
        self._adopt_prompted = True
        self._adopt_dialog_open = True
        parent = QApplication.activeModalWidget() or self
        try:
            dlg = AdoptRemotePasswordDialog(parent=parent)
            if not dlg.exec():
                self.set_status(
                    "• Синхронизация приостановлена: удалённая копия "
                    "зашифрована другим мастер-паролем.")
                return
            password = dlg.password
        finally:
            self._adopt_dialog_open = False
        self.set_status("Синхронизация и объединение данных...")
        self._adopt_worker = AdoptRemoteWorker(self.manager, password)
        self._adopt_worker.finished_ok.connect(self._on_adopt_done)
        self._adopt_worker.start()

    def _on_adopt_done(self, result: SyncResult) -> None:
        self.refresh_services()
        parent = QApplication.activeModalWidget() or self
        if result.ok:
            notify(parent, "Синхронизация", result.message)
            self.set_status("✓ " + result.message)
        else:
            notify(parent, "Синхронизация", result.message, QMessageBox.Warning)
            self.set_status("• " + result.message)
            # Неверный пароль — разрешаем повторить запрос при следующей
            # автоматической синхронизации.
            if result.password_mismatch:
                self._adopt_prompted = False

    # ------------------------------------------------------------------
    # Синхронизация
    # ------------------------------------------------------------------
    def start_sync(self, manual: bool = False) -> None:
        if self._change_worker is not None and self._change_worker.is_running():
            if manual:
                self.set_status("Смена мастер-пароля уже выполняется...")
            return
        if self._adopt_worker is not None and self._adopt_worker.is_running():
            if manual:
                self.set_status("Слияние с серверной копией уже выполняется...")
            return
        if self._sync_worker is not None and self._sync_worker.isRunning():
            if manual:
                self.set_status("Синхронизация уже выполняется...")
            return
        self._sync_manual = manual
        self.set_status("Синхронизация...")
        self._sync_worker = SyncWorker(self.manager)
        self._sync_worker.finished_ok.connect(self._on_sync_done)
        self._sync_worker.start()

    def _schedule_sync(self) -> None:
        """Отложенная фоновая синхронизация после изменения данных."""
        QTimer.singleShot(300, lambda: self.start_sync(manual=False))

    def closeEvent(self, event) -> None:  # noqa: N802
        # Работающие фоновые задачи — демон-потоки, поэтому не мешают выходу.
        # Даём им короткий шанс завершиться, но не блокируем закрытие.
        for worker in (self._sync_worker, self._check_worker,
                       self._change_worker, self._adopt_worker):
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
        # Серверная копия под другим мастер-паролем: предлагаем ввести его и
        # слить данные. При автоматической синхронизации — один раз за запуск,
        # при ручной — каждый раз.
        if result.password_mismatch and (self._sync_manual
                                         or not self._adopt_prompted):
            self._offer_adopt_remote()

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
