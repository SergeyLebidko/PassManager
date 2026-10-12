"""Иконки для кнопок на основе SVG из набора Lucide.

SVG-файлы лежат в ``app/ui/assets/icons`` и используют
``stroke="currentColor"``. При отрисовке готовая маска перекрашивается
в нужный цвет (``CompositionMode_SourceIn``), поэтому одна и та же
иконка подходит и для светлой, и для тёмной темы, и для цветных кнопок.

Публичный интерфейс: :func:`make_icon`.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_ASSET_DIR = Path(__file__).resolve().parent / "assets" / "icons"

# Имя иконки -> файл ассета (обычно совпадают).
_FILES: dict[str, str] = {
    "add": "add.svg",
    "edit": "edit.svg",
    "trash": "trash.svg",
    "restore": "restore.svg",
    "clear": "clear.svg",
    "close": "x.svg",
    "person": "person.svg",
    "key": "key.svg",
    "clock": "clock.svg",
    "moon": "moon.svg",
    "sun": "sun.svg",
    "link": "link.svg",
    "save": "save.svg",
    "copy": "copy.svg",
    "eye": "eye.svg",
    "eye-off": "eye-off.svg",
    "plug": "plug.svg",
    "check": "check.svg",
}

# Кэши: отрендеренные иконки и загруженные рендереры.
_ICON_CACHE: dict[tuple[str, str, int], QIcon] = {}
_RENDERERS: dict[str, QSvgRenderer] = {}


def _renderer(name: str) -> QSvgRenderer | None:
    """Загружает (с кэшированием) рендерер SVG для иконки."""
    cached = _RENDERERS.get(name)
    if cached is not None:
        return cached

    filename = _FILES.get(name)
    if filename is None:
        return None
    path = _ASSET_DIR / filename
    if not path.exists():
        return None

    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        return None
    _RENDERERS[name] = renderer
    return renderer


def make_icon(name: str, color: str, size: int = 20) -> QIcon:
    """Возвращает иконку ``name`` указанного цвета (кэшируется).

    ``color`` — цвет линий иконки; ``size`` — сторона квадрата в пикселях.
    """
    key = (name, color, size)
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached

    renderer = _renderer(name)
    if renderer is None:
        return QIcon()

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, size, size))
    # Перекрашиваем непрозрачные пиксели в нужный цвет.
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), QColor(color))
    painter.end()

    icon = QIcon(pixmap)
    _ICON_CACHE[key] = icon
    return icon
