"""Программно рисуемые иконки для кнопок (без внешних файлов).

Иконки рисуются с помощью ``QPainter``, поэтому автоматически
подстраиваются под размер и цвет текущей темы.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

_CACHE: dict[tuple[str, str, int], QIcon] = {}


def _pen(color: str, size: int, width_ratio: float = 0.085) -> QPen:
    pen = QPen(QColor(color))
    pen.setWidthF(max(1.6, size * width_ratio))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def _draw(name: str, p: QPainter, s: int) -> None:
    """Отрисовка фигуры по имени в квадрате ``s`` на ``s``."""
    def pt(x: float, y: float) -> tuple[float, float]:
        return x * s, y * s

    if name == "add":
        p.drawLine(*pt(0.5, 0.22), *pt(0.5, 0.78))
        p.drawLine(*pt(0.22, 0.5), *pt(0.78, 0.5))

    elif name == "edit":
        path = QPainterPath()
        path.moveTo(*pt(0.16, 0.84))
        path.lineTo(*pt(0.22, 0.60))
        path.lineTo(*pt(0.64, 0.18))
        path.lineTo(*pt(0.82, 0.36))
        path.lineTo(*pt(0.40, 0.78))
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(*pt(0.57, 0.25), *pt(0.75, 0.43))

    elif name == "trash":
        p.drawLine(*pt(0.16, 0.28), *pt(0.84, 0.28))
        p.drawLine(*pt(0.38, 0.28), *pt(0.38, 0.18))
        p.drawLine(*pt(0.38, 0.18), *pt(0.62, 0.18))
        p.drawLine(*pt(0.62, 0.18), *pt(0.62, 0.28))
        body = QPainterPath()
        body.moveTo(*pt(0.26, 0.34))
        body.lineTo(*pt(0.30, 0.84))
        body.lineTo(*pt(0.70, 0.84))
        body.lineTo(*pt(0.74, 0.34))
        p.drawPath(body)
        p.drawLine(*pt(0.42, 0.44), *pt(0.44, 0.74))
        p.drawLine(*pt(0.58, 0.44), *pt(0.56, 0.74))

    elif name == "copy":
        back = QPainterPath()
        back.moveTo(*pt(0.36, 0.44))
        back.lineTo(*pt(0.36, 0.18))
        back.lineTo(*pt(0.82, 0.18))
        back.lineTo(*pt(0.82, 0.64))
        back.lineTo(*pt(0.60, 0.64))
        p.drawPath(back)
        front = QPainterPath()
        front.addRoundedRect(QRectF(0.18 * s, 0.38 * s, 0.44 * s, 0.44 * s),
                             0.09 * s, 0.09 * s)
        p.drawPath(front)

    elif name == "person":
        p.drawEllipse(QRectF(0.34 * s, 0.16 * s, 0.32 * s, 0.32 * s))
        shoulders = QPainterPath()
        shoulders.arcMoveTo(QRectF(0.18 * s, 0.56 * s, 0.64 * s, 0.52 * s), 0)
        shoulders.arcTo(QRectF(0.18 * s, 0.56 * s, 0.64 * s, 0.52 * s), 0, 180)
        p.drawPath(shoulders)

    elif name == "key":
        p.drawEllipse(QRectF(0.14 * s, 0.36 * s, 0.30 * s, 0.30 * s))
        p.drawLine(*pt(0.44, 0.51), *pt(0.86, 0.51))
        p.drawLine(*pt(0.68, 0.51), *pt(0.68, 0.66))
        p.drawLine(*pt(0.79, 0.51), *pt(0.79, 0.63))

    elif name == "clock":
        p.drawEllipse(QRectF(0.18 * s, 0.18 * s, 0.64 * s, 0.64 * s))
        p.drawLine(*pt(0.50, 0.50), *pt(0.50, 0.30))
        p.drawLine(*pt(0.50, 0.50), *pt(0.66, 0.58))

    elif name == "search":
        p.drawEllipse(QRectF(0.18 * s, 0.18 * s, 0.44 * s, 0.44 * s))
        p.drawLine(*pt(0.58, 0.58), *pt(0.82, 0.82))

    elif name == "moon":
        color = p.pen().color()
        full = QPainterPath()
        full.addEllipse(QRectF(0.20 * s, 0.18 * s, 0.62 * s, 0.62 * s))
        cut = QPainterPath()
        cut.addEllipse(QRectF(0.46 * s, 0.08 * s, 0.60 * s, 0.60 * s))
        crescent = full.subtracted(cut)
        p.setPen(Qt.NoPen)
        p.fillPath(crescent, color)

    elif name == "sun":
        p.drawEllipse(QRectF(0.36 * s, 0.36 * s, 0.28 * s, 0.28 * s))
        for angle in range(0, 360, 45):
            p.save()
            p.translate(0.5 * s, 0.5 * s)
            p.rotate(angle)
            p.drawLine(0.30 * s, 0, 0.42 * s, 0)
            p.restore()


def make_icon(name: str, color: str, size: int = 20) -> QIcon:
    """Возвращает иконку ``name`` указанного цвета (кэшируется)."""
    key = (name, color, size)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(_pen(color, size))
    painter.setBrush(Qt.NoBrush)
    _draw(name, painter, size)
    painter.end()

    icon = QIcon(pixmap)
    _CACHE[key] = icon
    return icon
