"""Небольшие вспомогательные виджеты интерфейса."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QPushButton,
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


class RoundedComboBox(QComboBox):
    """Выпадающий список со скруглённым всплывающим окном.

    Глобальный QSS не применяется к всплывающему окну списка — оно является
    отдельным top-level окном. Поэтому рамку со скруглением задаём напрямую
    контейнеру попапа при его показе. Фон делаем прозрачным, чтобы
    ``border-radius`` реально «отрезал» углы.
    """

    def _style_popup(self) -> None:
        container = self.view().window()
        if container is None:
            return
        container.setObjectName("comboPopup")
        container.setAttribute(Qt.WA_TranslucentBackground, True)
        qss = style.combo_popup_qss()
        container.setStyleSheet(qss)
        self.view().setStyleSheet("background: transparent;")

    def showPopup(self) -> None:  # noqa: N802 (Qt-стиль)
        # Стиль можно задать и до показа, и после — делаем оба раза,
        # т.к. отдельное окно попапа создаётся лениво и может переоформиться.
        self._style_popup()
        super().showPopup()
        self._style_popup()
