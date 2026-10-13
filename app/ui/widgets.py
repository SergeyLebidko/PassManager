"""Небольшие вспомогательные виджеты интерфейса."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListWidget,
    QPushButton,
    QTableWidget,
)

from . import style
from .icons import make_icon


class IconColorButton(QPushButton):
    """Кнопка-иконка, которая «окрашивается» только при наведении.

    В обычном состоянии иконка рисуется цветом темы (нейтрально).
    При наведении (или нажатии) — белым цветом, т.к. фон кнопки
    становится синим/красным (см. стили ``QPushButton#primary`` и
    ``QPushButton#danger``).
    """

    def __init__(self, icon_name: str, tooltip: str = "",
                 obj_name: str = "", accent: bool = False,
                 icon_size: int = 20, compact: bool = True) -> None:
        super().__init__()
        self._icon_name = icon_name
        self._accent = accent          # цветная роль (primary/danger)
        self._hovered = False
        self.setIconSize(QSize(icon_size, icon_size))
        if compact:
            self.setFixedSize(36, 32)
            self.setProperty("compact", "true")
        if tooltip:
            self.setToolTip(tooltip)
        if obj_name:
            self.setObjectName(obj_name)
        self.setAttribute(Qt.WA_Hover, True)
        self._apply_icon()

    # ---- цвет иконки -------------------------------------------------
    def _icon_color(self) -> str:
        if self._accent and (self._hovered or self.isDown()):
            return "#ffffff"
        return style.icon_color()

    def _apply_icon(self) -> None:
        self.setIcon(make_icon(self._icon_name, self._icon_color()))

    def refresh_icon(self) -> None:
        """Перекрашивает иконку под текущую тему/состояние."""
        self._apply_icon()

    def set_icon_name(self, icon_name: str) -> None:
        """Меняет саму иконку (например, для кнопки смены темы)."""
        self._icon_name = icon_name
        self._apply_icon()

    # ---- события -----------------------------------------------------
    def enterEvent(self, event) -> None:  # noqa: N802 (Qt-стиль)
        self._hovered = True
        self._apply_icon()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt-стиль)
        self._hovered = False
        self._apply_icon()
        super().leaveEvent(event)

    def event(self, event) -> bool:
        # Обрабатываем нажатие/отпускание, чтобы иконка была белой,
        # пока кнопка удерживается (в т.ч. при нажатии с клавиатуры).
        handled = super().event(event)
        if event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
            self._apply_icon()
        return handled


class _ReorderMixin:
    """Общая логика перетаскивания строк внутри виджета.

    Перетаскивание реализовано вручную (``dropEvent``), а не средствами
    ``InternalMove``: так дроп всегда вставляет строку **между** другими,
    а не «поверх» записи, и перенос идёт в пределах одного виджета.

    Наследники реализуют :meth:`_row_ids` (идентификаторы строк в текущем
    порядке), :meth:`_rows_y` (вертикальные позиции строк) и
    :meth:`_reorder_to` (физическое перемещение строки). Результат отдаётся
    сигналом :attr:`rowReorderRequested`.
    """

    rowReorderRequested = Signal(list)

    def _setup_reorder(self) -> None:
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self._drag_rows: list[int] = []
        self._drop_row = -1
        self._order_before: list[str] = []

    # ---- данные о строках (переопределяется) -------------------------
    def _row_ids(self) -> list[str]:  # pragma: no cover - переопределяется
        raise NotImplementedError

    def _row_count(self) -> int:  # pragma: no cover - переопределяется
        raise NotImplementedError

    def _rows_y(self) -> list[float]:  # pragma: no cover - переопределяется
        raise NotImplementedError

    def _reorder_to(self, source: int, target: int) -> None:  # pragma: no cover
        raise NotImplementedError

    # ---- перетаскивание ----------------------------------------------
    def startDrag(self, supported_actions) -> None:  # noqa: N802
        self._drag_rows = sorted({index.row() for index in self.selectedIndexes()})
        self._drop_row = -1
        self._order_before = self._row_ids()
        # Перетаскивать нечего — не начинаем.
        if not self._drag_rows or len(self._drag_rows) >= self._row_count():
            self._drag_rows = []
            return
        super().startDrag(supported_actions)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.source() is self:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.source() is not self:
            event.ignore()
            return
        row = self._drop_position(event)
        if row != self._drop_row:
            self._drop_row = row
            self.viewport().update()
        event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._drop_row = -1
        self.viewport().update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        if event.source() is not self or not self._drag_rows:
            event.ignore()
            return
        action = event.dropAction()
        source = self._drag_rows[0]
        # chosen — индекс вставки в исходном списке (0..n).
        chosen = self._drop_position(event)
        # В списке без вынутой строки индекс сдвигается на 1, если она была выше.
        target = chosen - 1 if source < chosen else chosen
        self._drag_rows = []
        self._drop_row = -1
        self._reorder_to(source, target)
        # Свой перенос уже выполнен: не даём Qt двигать строки повторно.
        event.setDropAction(Qt.IgnoreAction)
        event.accept()
        self._after_drop(action)

    def _after_drop(self, action) -> None:
        self.viewport().update()
        # Порядок не изменился — ничего не сообщаем.
        if self._row_ids() == self._order_before:
            return
        self.rowReorderRequested.emit(self._row_ids())

    def _drop_position(self, event) -> int:
        """Индекс вставки (0..n): перед строкой, чей центр ниже курсора."""
        y = event.position().y()
        for index, center_y in enumerate(self._rows_y()):
            if y < center_y:
                return index
        return self._row_count()


class ReorderListWidget(_ReorderMixin, QListWidget):
    """Список с перетаскиванием строк (порядок отдаётся наружу сигналом)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setDragDropOverwriteMode(False)
        self._setup_reorder()

    def _row_count(self) -> int:
        return self.count()

    def _row_ids(self) -> list[str]:
        return [self.item(row).data(Qt.UserRole) for row in range(self.count())]

    def _rows_y(self) -> list[float]:
        return [float(self.visualItemRect(self.item(row)).center().y())
                for row in range(self.count())]

    def _reorder_to(self, source: int, target: int) -> None:
        item = self.item(source)
        if item is None:
            return
        self.blockSignals(True)
        self.takeItem(source)
        self.insertItem(target, item)
        self.blockSignals(False)


class ReorderTableWidget(_ReorderMixin, QTableWidget):
    """Таблица с перетаскиванием строк по вертикали (порядок — наружу)."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Без этого Qt при перетаскивании заменяет содержимое строк,
        # а не вставляет саму строку.
        self.setDragDropOverwriteMode(False)
        self._setup_reorder()

    def _row_count(self) -> int:
        return self.rowCount()

    def _row_ids(self) -> list[str]:
        ids: list[str] = []
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item is not None:
                ids.append(item.data(Qt.UserRole))
        return ids

    def _rows_y(self) -> list[float]:
        return [float(self.rowViewportPosition(row) + self.rowHeight(row) / 2)
                for row in range(self.rowCount())]

    def _reorder_to(self, source: int, target: int) -> None:
        """Перемещает строку ``source`` в позицию ``target`` (после извлечения)."""
        if source == target:
            return
        self.blockSignals(True)
        items = [self.takeItem(source, column)
                 for column in range(self.columnCount())]
        self.removeRow(source)
        self.insertRow(target)
        for column, item in enumerate(items):
            if item is not None:
                self.setItem(target, column, item)
        self.blockSignals(False)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self._drop_row >= 0:
            self._draw_drop_indicator(self._drop_row)

    def _draw_drop_indicator(self, row: int) -> None:
        """Рисует линию вставки между строками."""
        from PySide6.QtGui import QColor, QPainter, QPen

        lines = self._rows_y()
        if row >= len(lines):
            y = self.viewport().height() - 1
        else:
            y = lines[row] - self.rowHeight(row) / 2
        painter = QPainter(self.viewport())
        pen = QPen(QColor(style.accent_color()), 2)
        painter.setPen(pen)
        painter.drawLine(0, int(y), self.viewport().width(), int(y))
        painter.end()


