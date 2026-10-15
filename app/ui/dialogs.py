"""Диалоговые окна PassManager."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..models import Account, HistoryEntry, Service, to_iso
from . import style
from .icons import ICON_POOL, make_cell_icon, make_icon


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
        # Не растягиваемся по высоте: иначе в QFormLayout поле «уезжает»
        # вниз от своей подписи при увеличении окна.
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
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


class CommentEdit(QPlainTextEdit):
    """Многострочный комментарий.

    По умолчанию компактный, но при увеличении размера диалога забирает
    свободное место — так подписи полей остаются на месте.
    """

    _DEFAULT_HEIGHT = 90

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt-стиль)
        base = super().sizeHint()
        return QSize(base.width(), self._DEFAULT_HEIGHT)


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
# Смена мастер-пароля
# --------------------------------------------------------------------------

class ChangeMasterPasswordDialog(QDialog):
    """Смена мастер-пароля: текущий, новый и повтор.

    ``password_check`` — функция ``(str) -> bool``, которой проверяется
    текущий мастер-пароль. Под-диалог открывается из «Настроек».
    """

    def __init__(self, password_check, parent=None) -> None:
        super().__init__(parent)
        self.password_check = password_check
        self.new_password = ""
        self.setWindowTitle("Смена мастер-пароля")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        title = QLabel("Смена мастер-пароля")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        hint = QLabel(
            "Мастер-пароль защищает все данные. Смените его и на остальных "
            "устройствах — иначе они не смогут прочитать синхронизированную "
            "копию."
        )
        hint.setObjectName("subtitleLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        self.current = QLineEdit()
        self.current.setEchoMode(QLineEdit.Password)
        self.new1 = QLineEdit()
        self.new1.setEchoMode(QLineEdit.Password)
        self.new2 = QLineEdit()
        self.new2.setEchoMode(QLineEdit.Password)
        form.addRow("Текущий пароль:", self.current)
        form.addRow("Новый пароль:", self.new1)
        form.addRow("Повторите новый:", self.new2)
        layout.addLayout(form)

        self.error = QLabel("")
        self.error.setStyleSheet("color:#d64545;")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Сменить")
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        set_box_icons(buttons, {
            QDialogButtonBox.Ok: "check",
            QDialogButtonBox.Cancel: "close",
        })
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        QTimer.singleShot(50, self.current.setFocus)

    def _accept(self) -> None:
        current = self.current.text()
        new = self.new1.text()
        if not current:
            self.error.setText("Введите текущий мастер-пароль.")
            return
        if not self.password_check or not self.password_check(current):
            self.error.setText("Неверный текущий мастер-пароль.")
            return
        if len(new) < 6:
            self.error.setText("Новый мастер-пароль должен быть не короче 6 символов.")
            return
        if new != self.new2.text():
            self.error.setText("Новые пароли не совпадают.")
            return
        if new == current:
            self.error.setText("Новый пароль совпадает с текущим.")
            return
        self.new_password = new
        self.accept()


class AdoptRemotePasswordDialog(QDialog):
    """Запрос нового мастер-пароля удалённой копии для слияния данных.

    Показывается, когда серверная копия зашифрована другим мастер-паролем:
    пользователь вводит пароль, которым открывается сервер, после чего это
    устройство объединяет данные и переходит на тот же пароль.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.password = ""
        self.setWindowTitle("Синхронизация")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        title = QLabel("Нужен новый мастер-пароль")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        hint = QLabel(
            "Удалённая копия зашифрована другим мастер-паролем — видимо, "
            "пароль сменили на другом устройстве. Введите новый мастер-пароль: "
            "это устройство прочитает серверные данные, объединит их со своими "
            "и перейдёт на тот же пароль."
        )
        hint.setObjectName("subtitleLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        self.field = QLineEdit()
        self.field.setEchoMode(QLineEdit.Password)
        form.addRow("Новый мастер-пароль:", self.field)
        layout.addLayout(form)

        self.error = QLabel("")
        self.error.setStyleSheet("color:#d64545;")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Синхронизировать")
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        set_box_icons(buttons, {
            QDialogButtonBox.Ok: "check",
            QDialogButtonBox.Cancel: "close",
        })
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        QTimer.singleShot(50, self.field.setFocus)

    def _accept(self) -> None:
        if not self.field.text():
            self.error.setText("Введите мастер-пароль.")
            return
        self.password = self.field.text()
        self.accept()


# --------------------------------------------------------------------------
# Выбор иконки
# --------------------------------------------------------------------------

class _IconGrid(QListWidget):
    """Сетка иконок, которая перестраивается при изменении размера.

    ``QListWidget`` в режиме ``IconMode`` сам перекладывает строки под
    доступную ширину (``ResizeMode.Adjust``), поэтому при растягивании
    окна иконки не «прилипают» к прежней сетке. Иконки рендерятся во всю
    ячейку (см. :func:`app.ui.icons.make_cell_icon`) — так глиф оказывается
    по центру, а подсветка выделения остаётся квадратной.
    """

    CELL = 48
    GLYPH = 24
    MARGIN = 14

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setWrapping(True)
        self.setUniformItemSizes(True)
        self.setSpacing(0)
        self.setIconSize(QSize(self.CELL, self.CELL))
        self.setGridSize(QSize(self.CELL, self.CELL))
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.setEditTriggers(QListWidget.NoEditTriggers)
        # Зазор со всех сторон: задаём через viewport (QSS-``padding`` ломает
        # расчёт числа колонок в ``IconMode``, из-за чего справа оставалась
        # пустая полоса шириной в колонку).
        self.setViewportMargins(self.MARGIN, self.MARGIN,
                                self.MARGIN, self.MARGIN)


class IconPickerDialog(QDialog):
    """Сетка иконок из пула для выбора иконки сервиса/учётной записи.

    Выбор применяется сразу по клику (отдельного «ОК» нет). Пункт
    «Без иконки» очищает ранее установленную иконку.
    """

    def __init__(self, current: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Выбор иконки")
        self.resize(680, 480)
        self.selected = current or ""

        layout = QVBoxLayout(self)
        title = QLabel("Выберите иконку")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        self._list = _IconGrid()
        self._list.setObjectName("iconGrid")
        color = style.icon_color()
        for name in ICON_POOL:
            icon = make_cell_icon(name, color, self._list.CELL,
                                  self._list.GLYPH)
            item = QListWidgetItem(icon, "")
            item.setData(Qt.UserRole, name)
            item.setToolTip(name)
            item.setSizeHint(QSize(self._list.CELL, self._list.CELL))
            self._list.addItem(item)
            if name == self.selected:
                self._list.setCurrentItem(item)
        self._list.itemClicked.connect(
            lambda item: self._choose(item.data(Qt.UserRole)))
        layout.addWidget(self._list, 1)

        buttons = QDialogButtonBox()
        none_btn = buttons.addButton("Без иконки", QDialogButtonBox.ResetRole)
        none_btn.clicked.connect(lambda: self._choose(""))
        cancel = buttons.addButton("Отмена", QDialogButtonBox.RejectRole)
        cancel.clicked.connect(self.reject)
        layout.addWidget(buttons)

    def _choose(self, name: str) -> None:
        self.selected = name
        self.accept()


class IconPickerButton(QPushButton):
    """Кнопка-превью иконки; по клику открывает :class:`IconPickerDialog`."""

    def __init__(self, icon_name: str = "", parent=None) -> None:
        super().__init__(parent)
        self._icon_name = icon_name or ""
        self.setFixedSize(40, 32)
        self.setIconSize(QSize(20, 20))
        self.setToolTip("Выбрать иконку")
        self.clicked.connect(self._choose)
        self._refresh()

    def icon_name(self) -> str:
        return self._icon_name

    def set_icon_name(self, name: str) -> None:
        self._icon_name = name or ""
        self._refresh()

    def _refresh(self) -> None:
        if self._icon_name:
            self.setIcon(make_icon(self._icon_name, style.icon_color()))
            self.setText("")
        else:
            self.setIcon(QIcon())
            self.setText("—")

    def _choose(self) -> None:
        dlg = IconPickerDialog(self._icon_name, parent=self)
        if dlg.exec():
            self.set_icon_name(dlg.selected)


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
        self.name.setPlaceholderText("Например: Почта, Банки, Игры...")
        self.icon_btn = IconPickerButton(service.icon if service else "")
        form.addRow("Название:", self.name)
        form.addRow("Иконка:", self.icon_btn)
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

    def icon_value(self) -> str:
        return self.icon_btn.icon_name()


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
        self.title.setPlaceholderText("Краткое название")
        self.login = CopyableField(account.login if account else "", masked=False)
        self.password = CopyableField(account.password if account else "", masked=True)
        self.comment = CommentEdit(account.comment if account else "")
        self.comment.setMinimumHeight(80)
        self.comment.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.icon_btn = IconPickerButton(account.icon if account else "")

        form.addRow("Иконка:", self.icon_btn)
        form.addRow("Название: *", self.title)
        form.addRow("Логин: *", self.login)
        form.addRow("Пароль: *", self.password)
        form.addRow("Комментарий:", self.comment)
        layout.addLayout(form)

        hint = QLabel("* — обязательные поля. " + CLIPBOARD_HINT)
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
        missing = []
        if not self.title.text().strip():
            missing.append("название")
        if not self.login.text().strip():
            missing.append("логин")
        if not self.password.text():
            missing.append("пароль")
        if missing:
            notify(self, "Проверка",
                   "Заполните обязательные поля: " + ", ".join(missing) + ".",
                   QMessageBox.Warning)
            return
        self.result_data = {
            "title": self.title.text().strip(),
            "login": self.login.text().strip(),
            "password": self.password.text(),
            "comment": self.comment.toPlainText().strip(),
            "icon": self.icon_btn.icon_name(),
        }
        self.accept()


# --------------------------------------------------------------------------
# История
# --------------------------------------------------------------------------

class HistoryDialog(QDialog):
    def __init__(self, account: Account, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"История — {account.title or account.login}")
        self.resize(920, 460)
        self._account = account
        self._entries: list[HistoryEntry] = list(account.history)
        self._reveal = False
        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Изменено", "Название", "Логин", "Пароль", "Дата смены",
             "Комментарий"])
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
        header.resizeSection(0, 100)   # Изменено
        header.resizeSection(1, 160)   # Название
        header.resizeSection(2, 180)   # Логин
        header.resizeSection(3, 120)   # Пароль
        header.resizeSection(4, 140)   # Дата смены
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

        labels = {"login": "Логин", "password": "Пароль",
                  "title": "Название", "comment": "Комментарий",
                  "move": "Перемещение"}
        kind = QTableWidgetItem(labels.get(entry.kind, "Пароль"))
        kind.setData(Qt.UserRole, entry)
        self.table.setItem(row, 0, kind)

        self.table.setItem(row, 1, QTableWidgetItem(entry.title))
        self.table.setItem(row, 2, QTableWidgetItem(entry.login))
        pw_item = QTableWidgetItem(self._mask(entry.password))
        pw_item.setData(Qt.UserRole, entry.password)
        self.table.setItem(row, 3, pw_item)
        self.table.setItem(row, 4, QTableWidgetItem(to_iso(entry.changed_at)))
        self.table.setItem(row, 5, QTableWidgetItem(entry.comment))

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
            item = self.table.item(row, 3)
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
    def __init__(self, url: str, login: str, password: str,
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
        form.addRow("Адрес каталога:", self.url)
        form.addRow("Логин сервера:", self.login)
        form.addRow("Пароль сервера:", self.password)
        layout.addLayout(form)

        hint = QLabel(
            "Адрес можно указывать как davs:// или https://. "
            "Пароль сервера хранится в зашифрованном виде.\n"
            + CLIPBOARD_HINT + "."
        )
        hint.setObjectName("subtitleLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # --- блок смены мастер-пароля ---
        layout.addSpacing(4)
        mp_title = QLabel("Мастер-пароль")
        mp_title.setObjectName("titleLabel")
        layout.addWidget(mp_title)
        mp_hint = QLabel(
            "Мастер-пароль шифрует хранилище и пароль сервера. Меняйте его "
            "на каждом устройстве."
        )
        mp_hint.setObjectName("subtitleLabel")
        mp_hint.setWordWrap(True)
        layout.addWidget(mp_hint)

        mp_row = QHBoxLayout()
        self.change_password_btn = text_icon_button(
            "key", "Сменить мастер-пароль…")
        mp_row.addWidget(self.change_password_btn, 0, Qt.AlignVCenter)
        mp_row.addStretch(1)
        layout.addLayout(mp_row)

        # Всё лишнее вертикальное место уходит сюда, поэтому при растягивании
        # окна блоки (в т.ч. «Мастер-пароль») не разъезжаются: содержимое
        # держится сверху, а кнопки — снизу.
        layout.addStretch(1)

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

    def append_log(self, text: str) -> None:
        self.log_view.appendPlainText(text)
        self.log_view.ensureCursorVisible()

    def end_check(self, ok: bool, message: str) -> None:
        self.progress.hide()
        self.test_btn.setEnabled(True)
        self.status.setText(("✓ " if ok else "✗ ") + message)
        self.status.setStyleSheet("color:#2e9e6b;" if ok else "color:#d64545;")

    def values(self) -> dict:
        return {
            "url": self.url.text().strip(),
            "login": self.login.text().strip(),
            "password": self.password.text(),
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

