"""Современная тема оформления (QSS) для светлого и тёмного режимов."""

from __future__ import annotations

from pathlib import Path

ACCENT = "#2f6fed"
ACCENT_HOVER = "#3a7cff"
DANGER = "#d64545"
DANGER_HOVER = "#e35656"
SUCCESS = "#2e9e6b"

# Абсолютные пути к SVG-стрелке выпадающих списков (нужны в QSS через url()).
_ICONS_DIR = Path(__file__).resolve().parent / "assets" / "icons"
_CHEVRON_LIGHT = (_ICONS_DIR / "chevron-down.svg").as_posix()
_CHEVRON_DARK = (_ICONS_DIR / "chevron-down-dark.svg").as_posix()

LIGHT_QSS = f"""
* {{
    font-family: "Segoe UI", "Noto Sans", "Ubuntu", sans-serif;
    font-size: 14px;
}}
QWidget {{
    background: #f5f6f8;
    color: #1c1f23;
}}
QMainWindow, QDialog {{
    background: #f5f6f8;
}}
QLabel#titleLabel {{
    font-size: 20px;
    font-weight: 600;
}}
QLabel#subtitleLabel {{
    color: #6b7280;
}}
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox {{
    background: #ffffff;
    border: 1px solid #d7dae0;
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: {ACCENT};
    selection-color: #ffffff;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {{
    border: 1px solid {ACCENT};
}}
QComboBox {{
    padding-right: 30px;
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 26px;
    border: none;
    background: transparent;
}}
QComboBox::down-arrow {{
    image: url("{_CHEVRON_LIGHT}");
    width: 12px;
    height: 12px;
    margin-right: 9px;
}}
QComboBox QAbstractItemView {{
    background: transparent;
    border: none;
    padding: 6px;
    outline: none;
    selection-background-color: #e6edfd;
    selection-color: #12315f;
}}
QPushButton {{
    background: #ffffff;
    border: 1px solid #d7dae0;
    border-radius: 8px;
    padding: 7px 14px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: #eef1f6;
}}
QPushButton:pressed {{
    background: #e3e7ee;
}}
QPushButton[compact="true"] {{
    padding: 0;
}}
QPushButton#primary, QPushButton#danger {{
    background: #ffffff;
    border: 1px solid #d7dae0;
    color: #1c1f23;
}}
QPushButton#primary:hover {{
    background: {ACCENT};
    border-color: {ACCENT};
    color: #ffffff;
}}
QPushButton#primary:pressed {{
    background: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
    color: #ffffff;
}}
QPushButton#danger:hover {{
    background: {DANGER};
    border-color: {DANGER};
    color: #ffffff;
}}
QPushButton#danger:pressed {{
    background: {DANGER_HOVER};
    border-color: {DANGER_HOVER};
    color: #ffffff;
}}
QPushButton#quiet {{
    background: transparent;
    border: none;
    color: {ACCENT};
    padding: 4px 6px;
}}
QPushButton#quiet:hover {{
    background: #e6edfd;
    border-radius: 6px;
}}
QListWidget#iconGrid::item {{
    padding: 0px;
}}
QListWidget, QTreeWidget, QTableWidget {{
    background: #ffffff;
    border: 1px solid #e2e5ea;
    border-radius: 10px;
    alternate-background-color: #fafbfc;
    outline: none;
}}
QListWidget::item, QTreeWidget::item {{
    padding: 7px 8px;
    border-radius: 6px;
}}
QListWidget::item:selected, QTreeWidget::item:selected {{
    background: #e6edfd;
    color: #12315f;
}}
QHeaderView::section {{
    background: #eef1f6;
    border: none;
    border-right: 1px solid #ccd3dd;
    border-bottom: 1px solid #e2e5ea;
    padding: 8px;
    font-weight: 600;
}}
QHeaderView::section:last {{
    border-right: 1px solid #ccd3dd;
}}
QHeaderView::section:hover {{
    background: #e2e7ef;
}}
QTableWidget {{
    gridline-color: #eef1f6;
}}
QMenuBar {{
    background: #ffffff;
    border-bottom: 1px solid #e2e5ea;
}}
QMenuBar::item:selected {{
    background: #e6edfd;
    border-radius: 6px;
}}
QMenu {{
    background: #ffffff;
    border: 1px solid #d7dae0;
    padding: 6px;
}}
QMenu::item {{
    padding: 6px 26px 6px 26px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background: #e6edfd;
}}
QMenu::separator {{
    height: 1px;
    background: #e2e5ea;
    margin: 4px 8px;
}}
QToolBar {{
    background: #ffffff;
    border-bottom: 1px solid #e2e5ea;
    spacing: 6px;
    padding: 6px;
}}
QStatusBar {{
    background: #ffffff;
    border-top: 1px solid #e2e5ea;
    color: #6b7280;
}}
QGroupBox {{
    border: 1px solid #e2e5ea;
    border-radius: 10px;
    margin-top: 12px;
    padding: 10px;
    background: #ffffff;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: #6b7280;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #c7ccd4;
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: #aab1bb;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #c7ccd4;
    border-radius: 5px;
    min-width: 30px;
}}
QCheckBox {{
    spacing: 8px;
}}
QTabWidget::pane {{
    border: 1px solid #e2e5ea;
    border-radius: 10px;
    background: #ffffff;
}}
QTabBar::tab {{
    background: transparent;
    padding: 8px 14px;
    border-radius: 8px;
    margin-right: 4px;
}}
QTabBar::tab:selected {{
    background: #e6edfd;
    color: #12315f;
}}
"""

DARK_QSS = f"""
* {{
    font-family: "Segoe UI", "Noto Sans", "Ubuntu", sans-serif;
    font-size: 14px;
}}
QWidget {{
    background: #1e2127;
    color: #e6e8ec;
}}
QMainWindow, QDialog {{
    background: #1e2127;
}}
QLabel#titleLabel {{
    font-size: 20px;
    font-weight: 600;
}}
QLabel#subtitleLabel {{
    color: #9aa2ad;
}}
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox {{
    background: #262a31;
    border: 1px solid #363b44;
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: {ACCENT};
    selection-color: #ffffff;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {{
    border: 1px solid {ACCENT};
}}
QComboBox {{
    padding-right: 30px;
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 26px;
    border: none;
    background: transparent;
}}
QComboBox::down-arrow {{
    image: url("{_CHEVRON_DARK}");
    width: 12px;
    height: 12px;
    margin-right: 9px;
}}
QComboBox QAbstractItemView {{
    background: transparent;
    border: none;
    padding: 6px;
    outline: none;
    selection-background-color: #33415e;
    selection-color: #eaf0ff;
}}
QPushButton {{
    background: #2b3038;
    border: 1px solid #363b44;
    border-radius: 8px;
    padding: 7px 14px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: #343a44;
}}
QPushButton:pressed {{
    background: #3d444f;
}}
QPushButton[compact="true"] {{
    padding: 0;
}}
QPushButton#primary, QPushButton#danger {{
    background: #2b3038;
    border: 1px solid #363b44;
    color: #e6e8ec;
}}
QPushButton#primary:hover {{
    background: {ACCENT};
    border-color: {ACCENT};
    color: #ffffff;
}}
QPushButton#primary:pressed {{
    background: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
    color: #ffffff;
}}
QPushButton#danger:hover {{
    background: {DANGER};
    border-color: {DANGER};
    color: #ffffff;
}}
QPushButton#danger:pressed {{
    background: {DANGER_HOVER};
    border-color: {DANGER_HOVER};
    color: #ffffff;
}}
QPushButton#quiet {{
    background: transparent;
    border: none;
    color: #7ea6ff;
    padding: 4px 6px;
}}
QPushButton#quiet:hover {{
    background: #2b3038;
    border-radius: 6px;
}}
QListWidget#iconGrid::item {{
    padding: 0px;
}}
QListWidget, QTreeWidget, QTableWidget {{
    background: #262a31;
    border: 1px solid #363b44;
    border-radius: 10px;
    alternate-background-color: #2a2f37;
    outline: none;
}}
QListWidget::item, QTreeWidget::item {{
    padding: 7px 8px;
    border-radius: 6px;
}}
QListWidget::item:selected, QTreeWidget::item:selected {{
    background: #33415e;
    color: #eaf0ff;
}}
QHeaderView::section {{
    background: #2b3038;
    border: none;
    border-right: 1px solid #454c57;
    border-bottom: 1px solid #363b44;
    padding: 8px;
    font-weight: 600;
}}
QHeaderView::section:last {{
    border-right: 1px solid #454c57;
}}
QHeaderView::section:hover {{
    background: #333944;
}}
QMenuBar {{
    background: #262a31;
    border-bottom: 1px solid #363b44;
}}
QMenuBar::item:selected {{
    background: #33415e;
    border-radius: 6px;
}}
QMenu {{
    background: #262a31;
    border: 1px solid #363b44;
    padding: 6px;
    color: #e6e8ec;
}}
QMenu::item {{
    padding: 6px 26px 6px 26px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background: #33415e;
}}
QMenu::separator {{
    height: 1px;
    background: #363b44;
    margin: 4px 8px;
}}
QToolBar {{
    background: #262a31;
    border-bottom: 1px solid #363b44;
    spacing: 6px;
    padding: 6px;
}}
QStatusBar {{
    background: #262a31;
    border-top: 1px solid #363b44;
    color: #9aa2ad;
}}
QGroupBox {{
    border: 1px solid #363b44;
    border-radius: 10px;
    margin-top: 12px;
    padding: 10px;
    background: #262a31;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: #9aa2ad;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #464d58;
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: #5a636f;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
}}
QCheckBox {{
    spacing: 8px;
}}
QTabWidget::pane {{
    border: 1px solid #363b44;
    border-radius: 10px;
    background: #262a31;
}}
QTabBar::tab {{
    background: transparent;
    padding: 8px 14px;
    border-radius: 8px;
    margin-right: 4px;
}}
QTabBar::tab:selected {{
    background: #33415e;
    color: #eaf0ff;
}}
"""


def stylesheet(dark: bool) -> str:
    return DARK_QSS if dark else LIGHT_QSS


def apply_theme(app, dark: bool) -> None:
    """Применяет тему ко всему приложению.

    Нужна, чтобы диалоги, открываемые до создания главного окна
    (например, ввод мастер-пароля), уже имели единый стиль.
    """
    app.setStyleSheet(stylesheet(dark))
    set_dark(dark)


# Текущая тема: используется, чтобы иконки в диалогах подбирали цвет.
_current_dark = False


def set_dark(dark: bool) -> None:
    global _current_dark
    _current_dark = bool(dark)


def is_dark() -> bool:
    return _current_dark


def icon_color() -> str:
    """Цвет иконок для текущей темы."""
    return "#e6e9ee" if _current_dark else "#1c1f23"


def highlight_color() -> str:
    """Фон подсветки найденных совпадений при поиске."""
    return "#5a4a1a" if _current_dark else "#fff2b8"


def highlight_text_color() -> str:
    """Цвет текста в подсвеченных совпадениях."""
    return "#ffe9a8" if _current_dark else "#5a4700"


def icon_hover_color() -> str:
    """Фон ячейки иконки при наведении (в сетке выбора иконок)."""
    return "#343a44" if _current_dark else "#eef1f6"


def accent_color() -> str:
    """Акцентный цвет (линия вставки при перетаскивании)."""
    return ACCENT


def combo_popup_qss() -> str:
    """Стиль всплывающего окна выпадающего списка.

    Задаётся напрямую контейнеру попапа (см. ``RoundedComboBox``): глобальный
    QSS не доходит до отдельного окна списка, а рамку со скруглением нужно
    нарисовать именно там — иначе получается «рамка в рамке» без скругления.
    """
    if _current_dark:
        return ("#comboPopup{background:#262a31;border:1px solid #363b44;"
                "border-radius:10px;}")
    return ("#comboPopup{background:#ffffff;border:1px solid #d7dae0;"
            "border-radius:10px;}")
