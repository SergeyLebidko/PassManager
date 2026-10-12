"""Диалоговые окна PassManager."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..models import Account, HistoryEntry, Service, TrashItem, to_iso
from . import style
from .icons import make_icon


# --------------------------------------------------------------------------
# Общие помощники
# --------------------------------------------------------------------------

AUTOCLEAR_SECONDS = 30

CLIPBOARD_HINT = (
    "Копирование — буфер обмена очищается автоматически "
    f"через {AUTOCLEAR_SECONDS} секунд"
)


def confirm(parent, title: str, text: str) -> bool:
    """Диалог подтверждения с русскими кнопками «Да»/«Нет»."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Question)
    box.setWindowTitle(title)
    box.setText(text)
    yes = box.addButton("Да", QMessageBox.YesRole)
    box.addButton("Нет", QMessageBox.NoRole)
    box.setDefaultButton(yes)
    box.exec()
    return box.clickedButton() is yes


def notify(parent, title: str, text: str, icon=QMessageBox.Information) -> None:
    """Информационное окно с русской кнопкой «ОК»."""
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    ok = box.addButton("ОК", QMessageBox.AcceptRole)
    box.setDefaultButton(ok)
    box.exec()


def icon_button(icon_name: str, tooltip: str,
                obj_name: str = "", color: str = ""):
    """Компактная кнопка-иконка с всплывающей подсказкой.

    Для цветных ролей (``primary``/``danger``) иконка белеет только при
    наведении; в покое — нейтрального цвета темы. Явный ``color``
    используется для иконок на постоянно цветном фоне.
    """
    from .widgets import IconColorButton

    accent = obj_name in ("primary", "danger")
    btn = IconColorButton(icon_name, tooltip, obj_name, accent=accent)
    if color:
        btn.setIcon(make_icon(icon_name, color))
    return btn


def text_icon_button(icon_name: str, text: str,
                     obj_name: str = "", color: str = "",
                     icon_size: int = 16) -> QPushButton:
    """Кнопка с иконкой и текстом (текст сохраняется)."""
    btn = QPushButton(text)
    btn.setIconSize(QSize(icon_size, icon_size))
    btn.setIcon(make_icon(icon_name, color or style.icon_color()))
    btn.setProperty("iconName", icon_name)
    if obj_name:
        btn.setObjectName(obj_name)
    return btn


def set_box_icons(box: "QDialogButtonBox",
                  mapping: dict) -> None:
    """Проставляет иконки стандартным кнопкам ``QDialogButtonBox``.

    ``mapping`` — словарь ``{QDialogButtonBox.StandardButton: имя_иконки}``.
    Все затронутые кнопки получают иконки одного размера и одинаковую
    ширину — чтобы вид был единым во всех диалогах.
    """
    touched = []
    for standard, icon_name in mapping.items():
        button = box.button(standard)
        if button is None:
            continue
        button.setIcon(make_icon(icon_name, style.icon_color()))
        button.setIconSize(QSize(16, 16))
        button.setProperty("iconName", icon_name)
        touched.append(button)
    equalize_button_widths(*touched)


def equalize_button_widths(*buttons: QPushButton) -> None:
    """Выравнивает ширину кнопок по самой широкой.

    Удобно для пар «Отмена»/«Сохранить», чтобы они выглядели единообразно.
    """
    buttons = [b for b in buttons if b is not None]
    if not buttons:
        return
    width = 0
    for btn in buttons:
        btn.ensurePolished()
        width = max(width, btn.sizeHint().width())
    for btn in buttons:
        btn.setFixedWidth(width)


def copy_to_clipboard(text: str, owner: QWidget | None = None) -> None:
    """Копирует текст и через AUTOCLEAR_SECONDS очищает буфер обмена.

    ``owner`` - виджет, к которому привязывается таймер (чтобы он жил,
    пока открыт диалог). Если не задан, используется главное окно.
    """
    clipboard = QGuiApplication.clipboard()
    clipboard.setText(text)

    target = owner
    if target is None:
        from PySide6.QtWidgets import QApplication

        target = QApplication.activeWindow()
    if target is None:
        return

    timer = getattr(target, "_clipboard_timer", None)
    if timer is None:
        timer = QTimer(target)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: QGuiApplication.clipboard().clear())
        setattr(target, "_clipboard_timer", timer)
    timer.start(AUTOCLEAR_SECONDS * 1000)


class CopyableField(QWidget):
    """Поле с кнопкой копирования.

    ``masked=True`` - пароль: текст скрыт, есть кнопки «Показать» и «Копировать».
    ``masked=False`` - обычное поле (например, логин): есть только «Копировать».
    """

    def __init__(self, text: str = "", masked: bool = True, parent=None) -> None:
        super().__init__(parent)
        self.masked = masked
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.edit = QLineEdit(text)
        if masked:
            self.edit.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.edit, 1)

        if masked:
            self.toggle = text_icon_button("eye", "Показать", "quiet")
            self.toggle.setCheckable(True)
            self.toggle.setFixedWidth(104)
            self.toggle.toggled.connect(self._toggle)
            layout.addWidget(self.toggle)

        self.copy = text_icon_button("copy", "Копировать", "quiet")
        self.copy.clicked.connect(self._copy)
        layout.addWidget(self.copy)

    def _copy(self) -> None:
        copy_to_clipboard(self.edit.text(), owner=self)

    def _toggle(self, shown: bool) -> None:
        self.edit.setEchoMode(QLineEdit.Normal if shown else QLineEdit.Password)
        self.toggle.setText("Скрыть" if shown else "Показать")
        self.toggle.setIcon(make_icon("eye-off" if shown else "eye",
                                      style.icon_color()))

    def text(self) -> str:
        return self.edit.text()

    def setText(self, value: str) -> None:
        self.edit.setText(value)


# --------------------------------------------------------------------------
# Мастер-пароль
# --------------------------------------------------------------------------

class MasterPasswordDialog(QDialog):
    """Ввод мастер-пароля: создание нового или разблокировка."""

    def __init__(self, creating: bool, parent=None) -> None:
        super().__init__(parent)
        self.creating = creating
        self.password = ""
        self.setWindowTitle("Новое хранилище" if creating else "Разблокировка")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        title = QLabel("Придумайте мастер-пароль" if creating else "Введите мастер-пароль")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        hint = QLabel(
            "Мастер-пароль защищает все данные. Если вы его забудете, "
            "восстановить пароли будет невозможно."
            if creating else
            "Введите мастер-пароль для доступа к хранилищу."
        )
        hint.setObjectName("subtitleLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        self.pw1 = QLineEdit()
        self.pw1.setEchoMode(QLineEdit.Password)
        form.addRow("Пароль:", self.pw1)
        self.pw2 = QLineEdit()
        self.pw2.setEchoMode(QLineEdit.Password)
        if creating:
            form.addRow("Повторите:", self.pw2)
        layout.addLayout(form)

        self.error = QLabel("")
        self.error.setStyleSheet("color:#d64545;")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Создать" if creating else "Открыть")
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        set_box_icons(buttons, {
            QDialogButtonBox.Ok: "check",
            QDialogButtonBox.Cancel: "close",
        })
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        QTimer.singleShot(50, self.pw1.setFocus)

    def _accept(self) -> None:
        pw = self.pw1.text()
        if not pw:
            self.error.setText("Пароль не может быть пустым.")
            return
        if self.creating:
            if len(pw) < 6:
                self.error.setText("Мастер-пароль должен быть не короче 6 символов.")
                return
            if pw != self.pw2.text():
                self.error.setText("Пароли не совпадают.")
                return
        self.password = pw
        self.accept()


# --------------------------------------------------------------------------
# Сервис
# --------------------------------------------------------------------------

class ServiceDialog(QDialog):
    def __init__(self, service: Service | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Сервис")
        self.setMinimumWidth(380)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(service.name if service else "")
        self.name.setPlaceholderText("Например: Gmail, Банк, Steam")
        form.addRow("Название:", self.name)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Сохранить")
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        set_box_icons(buttons, {
            QDialogButtonBox.Ok: "save",
            QDialogButtonBox.Cancel: "close",
        })
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        if not self.name.text().strip():
            notify(self, "Проверка", "Введите название сервиса.",
                   QMessageBox.Warning)
            return
        self.accept()

    def value(self) -> str:
        return self.name.text().strip()


# --------------------------------------------------------------------------
# Учётная запись
# --------------------------------------------------------------------------

class AccountDialog(QDialog):
    """Создание и редактирование учётной записи."""

    def __init__(self, account: Account | None = None, service_name: str = "",
                 parent=None) -> None:
        super().__init__(parent)
        self.account = account
        self.is_new = account is None
        self.setWindowTitle(("Новая учётная запись" if self.is_new
                             else "Редактирование учётной записи")
                            + (f" — {service_name}" if service_name else ""))
        self.setMinimumWidth(520)
        self.result_data: dict[str, str] = {}

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.title = QLineEdit(account.title if account else "")
        self.title.setPlaceholderText("Краткое название (необязательно)")
        self.login = CopyableField(account.login if account else "", masked=False)
        self.password = CopyableField(account.password if account else "", masked=True)
        self.comment = QPlainTextEdit(account.comment if account else "")
        self.comment.setFixedHeight(80)

        form.addRow("Название:", self.title)
        form.addRow("Логин:", self.login)
        form.addRow("Пароль:", self.password)
        form.addRow("Комментарий:", self.comment)
        layout.addLayout(form)

        hint = QLabel(CLIPBOARD_HINT)
        hint.setObjectName("subtitleLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        if not self.is_new:
            info = QLabel(
                f"Создана: {to_iso(account.created_at)}   •   "
                f"Логин изменён: {to_iso(account.login_changed_at)}   •   "
                f"Пароль изменён: {to_iso(account.password_changed_at)}"
            )
            info.setObjectName("subtitleLabel")
            info.setWordWrap(True)
            layout.addWidget(info)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Сохранить")
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        set_box_icons(buttons, {
            QDialogButtonBox.Ok: "save",
            QDialogButtonBox.Cancel: "close",
        })
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        if not self.login.text().strip() and not self.title.text().strip():
            notify(self, "Проверка",
                   "Укажите хотя бы название или логин.", QMessageBox.Warning)
            return
        self.result_data = {
            "title": self.title.text().strip(),
            "login": self.login.text().strip(),
            "password": self.password.text(),
            "comment": self.comment.toPlainText().strip(),
        }
        self.accept()


# --------------------------------------------------------------------------
# История
# --------------------------------------------------------------------------

class HistoryDialog(QDialog):
    def __init__(self, account: Account, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"История — {account.title or account.login}")
        self.resize(820, 460)
        self._account = account
        self._entries: list[HistoryEntry] = list(account.history)
        self._reveal = False
        layout = QVBoxLayout(self)

        current = QLabel(
            f"Логин изменён: {to_iso(account.login_changed_at)}   •   "
            f"Пароль изменён: {to_iso(account.password_changed_at)}"
        )
        current.setObjectName("subtitleLabel")
        current.setWordWrap(True)
        layout.addWidget(current)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Изменено", "Логин", "Пароль", "Дата смены", "Комментарий"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        header.setMinimumSectionSize(60)
        header.setSectionsMovable(True)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        header.resizeSection(0, 100)
        header.resizeSection(1, 190)
        header.resizeSection(2, 140)
        header.resizeSection(3, 150)
        self.table.currentCellChanged.connect(lambda *_: self._update_buttons())

        for entry in self._entries:
            self._add(entry)
        layout.addWidget(self.table)

        controls = QHBoxLayout()
        self.reveal_btn = text_icon_button("eye", "Показать пароли", "quiet")
        self.reveal_btn.setCheckable(True)
        self.reveal_btn.toggled.connect(self._toggle_reveal)
        controls.addWidget(self.reveal_btn)

        self.copy_login_btn = text_icon_button("person", "Копировать логин")
        self.copy_login_btn.clicked.connect(self._copy_login)
        self.copy_password_btn = text_icon_button("key", "Копировать пароль")
        self.copy_password_btn.clicked.connect(self._copy_password)
        controls.addStretch(1)
        controls.addWidget(self.copy_login_btn)
        controls.addWidget(self.copy_password_btn)
        layout.addLayout(controls)

        hint = QLabel("Каждая строка — предыдущее состояние записи. " + CLIPBOARD_HINT + ".")
        hint.setObjectName("subtitleLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("Закрыть")
        set_box_icons(buttons, {QDialogButtonBox.Close: "close"})
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        self._update_buttons()

    def _add(self, entry: HistoryEntry) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)

        kind = QTableWidgetItem("Логин" if entry.kind == "login" else "Пароль")
        kind.setData(Qt.UserRole, entry)
        self.table.setItem(row, 0, kind)

        self.table.setItem(row, 1, QTableWidgetItem(entry.login))
        pw_item = QTableWidgetItem(self._mask(entry.password))
        pw_item.setData(Qt.UserRole, entry.password)
        self.table.setItem(row, 2, pw_item)
        self.table.setItem(row, 3, QTableWidgetItem(to_iso(entry.changed_at)))
        self.table.setItem(row, 4, QTableWidgetItem(entry.comment))

    def _mask(self, password: str) -> str:
        if self._reveal:
            return password if password else "—"
        return "•" * min(len(password), 12) or "—"

    def _toggle_reveal(self, shown: bool) -> None:
        self._reveal = shown
        self.reveal_btn.setText("Скрыть пароли" if shown else "Показать пароли")
        self.reveal_btn.setIcon(make_icon("eye-off" if shown else "eye",
                                          style.icon_color()))
        for row, entry in enumerate(self._entries):
            item = self.table.item(row, 2)
            if item is not None:
                item.setText(self._mask(entry.password))

    def _selected(self) -> HistoryEntry | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.UserRole) if item is not None else None

    def _update_buttons(self) -> None:
        entry = self._selected()
        has_login = bool(entry and entry.login)
        has_password = bool(entry and entry.password)
        self.copy_login_btn.setEnabled(has_login)
        self.copy_password_btn.setEnabled(has_password)

    def _copy_login(self) -> None:
        entry = self._selected()
        if entry and entry.login:
            copy_to_clipboard(entry.login, owner=self)

    def _copy_password(self) -> None:
        entry = self._selected()
        if entry and entry.password:
            copy_to_clipboard(entry.password, owner=self)


# --------------------------------------------------------------------------
# Настройки
# --------------------------------------------------------------------------

class SettingsDialog(QDialog):
    def __init__(self, url: str, login: str, password: str, autosync: bool,
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        title = QLabel("Синхронизация с WebDAV")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.url = QLineEdit(url)
        self.url.setPlaceholderText("https://server/webdav/PassManager")
        self.login = QLineEdit(login)
        self.password = CopyableField(password, masked=True)
        self.autosync = QCheckBox("Автоматически синхронизировать при сохранении")
        self.autosync.setChecked(autosync)
        form.addRow("Адрес каталога:", self.url)
        form.addRow("Логин сервера:", self.login)
        form.addRow("Пароль сервера:", self.password)
        form.addRow("", self.autosync)
        layout.addLayout(form)

        hint = QLabel(
            "Адрес можно указывать как davs:// или https://. "
            "Пароль сервера хранится в зашифрованном виде.\n"
            + CLIPBOARD_HINT + "."
        )
        hint.setObjectName("subtitleLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # --- блок проверки подключения ---
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # режим «бегущей полосы» (спиннер)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.progress.hide()
        layout.addWidget(self.progress)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(120)
        self.log_view.setPlaceholderText("Здесь появится журнал проверки подключения.")
        font = self.log_view.font()
        font.setFamily("monospace")
        self.log_view.setFont(font)
        self.log_view.hide()
        layout.addWidget(self.log_view)

        layout.addSpacing(4)

        # Кнопка проверки и кнопки «Отмена»/«Сохранить» — в одной строке.
        bottom_row = QHBoxLayout()
        self.test_btn = text_icon_button("plug", "Проверить подключение")
        bottom_row.addWidget(self.test_btn, 0, Qt.AlignVCenter)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Сохранить")
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        set_box_icons(buttons, {
            QDialogButtonBox.Ok: "save",
            QDialogButtonBox.Cancel: "close",
        })
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        bottom_row.addStretch(1)
        bottom_row.addWidget(buttons, 0, Qt.AlignVCenter)
        layout.addLayout(bottom_row)

    # ---- проверка подключения ---------------------------------------
    def begin_check(self) -> None:
        self.test_btn.setEnabled(False)
        self.status.setText("Проверка подключения...")
        self.status.setStyleSheet("")
        self.log_view.clear()
        self.log_view.show()
        self.progress.show()
        self._fit_to_content()

    def _fit_to_content(self) -> None:
        """Пересчитывает размер окна, чтобы лог и кнопки не перекрывались."""
        self.layout().activate()
        self.adjustSize()

    def append_log(self, text: str) -> None:
        self.log_view.appendPlainText(text)
        self.log_view.ensureCursorVisible()

    def end_check(self, ok: bool, message: str) -> None:
        self.progress.hide()
        self.test_btn.setEnabled(True)
        self.status.setText(("✓ " if ok else "✗ ") + message)
        self.status.setStyleSheet("color:#2e9e6b;" if ok else "color:#d64545;")
        self._fit_to_content()

    def values(self) -> dict:
        return {
            "url": self.url.text().strip(),
            "login": self.login.text().strip(),
            "password": self.password.text(),
            "autosync": self.autosync.isChecked(),
        }

    def stop_check_worker(self) -> None:
        """Готовит диалог к закрытию: отключает сигналы потока проверки.

        Поток принадлежит главному окну, поэтому здесь мы не удаляем его,
        а лишь отвязываем от виджетов диалога, чтобы после закрытия сигналы
        не обращались к уже удалённым объектам.
        """
        worker = getattr(self, "_check_worker", None)
        if worker is None:
            return
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                worker.log.disconnect(self.append_log)
            except (RuntimeError, TypeError):
                pass
            for sig in (worker.finished_check, worker.failed):
                try:
                    sig.disconnect()
                except (RuntimeError, TypeError):
                    pass
        try:
            worker.wait(5000)
        except RuntimeError:
            pass
        self._check_worker = None

    def accept(self) -> None:  # noqa: D102
        self.stop_check_worker()
        super().accept()

    def reject(self) -> None:  # noqa: D102
        self.stop_check_worker()
        super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.stop_check_worker()
        super().closeEvent(event)


# --------------------------------------------------------------------------
# Корзина
# --------------------------------------------------------------------------

class TrashDialog(QDialog):
    def __init__(self, items: list[TrashItem], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Корзина")
        self.resize(680, 460)
        self.items = items
        self.action: str | None = None
        self.selected_id: str | None = None

        layout = QVBoxLayout(self)
        title = QLabel("Корзина")
        title.setObjectName("titleLabel")
        layout.addWidget(title)
        hint = QLabel("Удалённые сервисы и учётные записи хранятся здесь без ограничения по времени.")
        hint.setObjectName("subtitleLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Тип", "Название", "Удалено"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(60)
        header.setSectionsMovable(True)
        header.resizeSection(0, 150)
        header.resizeSection(1, 300)
        self.table.setColumnWidth(2, 180)

        for item in items:
            kind = "Сервис" if item.kind == "service" else "Учётная запись"
            row = self.table.rowCount()
            self.table.insertRow(row)
            kind_item = QTableWidgetItem(kind)
            kind_item.setData(Qt.UserRole, item.id)
            self.table.setItem(row, 0, kind_item)
            self.table.setItem(row, 1, QTableWidgetItem(item.name))
            self.table.setItem(row, 2, QTableWidgetItem(to_iso(item.deleted_at)))
        self.table.doubleClicked.connect(lambda _i: self._select("restore"))
        layout.addWidget(self.table)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.restore_btn = icon_button(
            "restore", "Восстановить выбранный элемент", "primary")
        self.delete_btn = icon_button(
            "trash", "Удалить выбранный элемент навсегда", "danger")
        self.clear_btn = icon_button(
            "clear", "Очистить корзину полностью", "danger")
        row.addWidget(self.restore_btn)
        row.addWidget(self.delete_btn)
        row.addStretch(1)
        row.addWidget(self.clear_btn)
        layout.addLayout(row)

        self.restore_btn.clicked.connect(lambda: self._select("restore"))
        self.delete_btn.clicked.connect(lambda: self._select("delete"))
        self.clear_btn.clicked.connect(lambda: self._select("clear"))

    def _select(self, action: str) -> None:
        if action in ("restore", "delete"):
            row = self.table.currentRow()
            if row < 0:
                notify(self, "Корзина", "Выберите элемент.")
                return
            item = self.table.item(row, 0)
            self.selected_id = item.data(Qt.UserRole) if item is not None else None
        if action == "clear" and not self.items:
            notify(self, "Корзина", "Корзина уже пуста.")
            return
        self.action = action
        self.accept()
