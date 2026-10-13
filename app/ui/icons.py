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
    "arrow-up": "arrow-up.svg",
    "arrow-down": "arrow-down.svg",
    "arrow-up-down": "arrow-up-down.svg",
    # Пул иконок для сервисов и учётных записей (см. ICON_POOL).
    "mail": "mail.svg",
    "at-sign": "at-sign.svg",
    "phone": "phone.svg",
    "send": "send.svg",
    "message-circle": "message-circle.svg",
    "globe": "globe.svg",
    "cloud": "cloud.svg",
    "server": "server.svg",
    "database": "database.svg",
    "hard-drive": "hard-drive.svg",
    "wifi": "wifi.svg",
    "smartphone": "smartphone.svg",
    "laptop": "laptop.svg",
    "monitor": "monitor.svg",
    "camera": "camera.svg",
    "music": "music.svg",
    "film": "film.svg",
    "gamepad-2": "gamepad-2.svg",
    "shopping-cart": "shopping-cart.svg",
    "shopping-bag": "shopping-bag.svg",
    "credit-card": "credit-card.svg",
    "wallet": "wallet.svg",
    "banknote": "banknote.svg",
    "coins": "coins.svg",
    "landmark": "landmark.svg",
    "briefcase": "briefcase.svg",
    "building": "building.svg",
    "house": "house.svg",
    "store": "store.svg",
    "factory": "factory.svg",
    "car": "car.svg",
    "plane": "plane.svg",
    "coffee": "coffee.svg",
    "book": "book.svg",
    "graduation-cap": "graduation-cap.svg",
    "heart": "heart.svg",
    "star": "star.svg",
    "shield": "shield.svg",
    "users": "users.svg",
    "code": "code.svg",
    "terminal": "terminal.svg",
    "cpu": "cpu.svg",
    "package": "package.svg",
    "gift": "gift.svg",
    "trophy": "trophy.svg",
    "palette": "palette.svg",
    "rocket": "rocket.svg",
    "tv": "tv.svg",
    "map-pin": "map-pin.svg",
}

# Иконки, доступные пользователю для сервисов и учётных записей.
# Порядок задаёт вид сетки выбора.
ICON_POOL: list[str] = [
    "mail", "at-sign", "phone", "send", "message-circle",
    "globe", "cloud", "server", "database", "hard-drive",
    "wifi", "smartphone", "laptop", "monitor", "camera",
    "music", "film", "gamepad-2", "shopping-cart", "shopping-bag",
    "credit-card", "wallet", "banknote", "coins", "landmark",
    "briefcase", "building", "house", "store", "factory",
    "car", "plane", "coffee", "book", "graduation-cap",
    "heart", "star", "shield", "users", "code",
    "terminal", "cpu", "package", "gift", "trophy",
    "palette", "rocket", "tv", "map-pin",
]

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
