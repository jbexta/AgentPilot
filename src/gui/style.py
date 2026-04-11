from PySide6.QtGui import QColor

from gui import system
from utils.helpers import apply_alpha_to_hex

PRIMARY_COLOR = '#ff1b1a1b'
SECONDARY_COLOR = '#ff292629'
TEXT_COLOR = '#ffcacdd5'
ACCENT_COLOR_1 = '#ff438bb9'
ACCENT_COLOR_2 = '#ff6aab73'


def get_stylesheet():
    global PRIMARY_COLOR, SECONDARY_COLOR, TEXT_COLOR, ACCENT_COLOR_1, ACCENT_COLOR_2

    system_config = system.manager.config  # system.config.dict if system else {}

    PRIMARY_COLOR = system_config.get('display.primary_color', '#ff1b1a1b')
    SECONDARY_COLOR = system_config.get('display.secondary_color', '#ff292629')
    TEXT_COLOR = system_config.get('display.text_color', '#ffc4c4c4')
    TEXT_SIZE = system_config.get('display.text_size', 12)
    ACCENT_COLOR_1 = system_config.get('display.accent_color_1', '#ff438bb9')
    ACCENT_COLOR_2 = system_config.get('display.accent_color_2', '#ff6aab73')

    # Protect against similar text and background colors by checking RGB distance
    primary = QColor(PRIMARY_COLOR)
    text = QColor(TEXT_COLOR)

    # Calculate Euclidean distance between colors in RGB space
    r_diff = abs(primary.red() - text.red())
    g_diff = abs(primary.green() - text.green())
    b_diff = abs(primary.blue() - text.blue())
    color_distance = (r_diff ** 2 + g_diff ** 2 + b_diff ** 2) ** 0.5

    if color_distance < 20:  # Threshold for color similarity
        TEXT_COLOR = '#ffffff' if primary.lightness() < 128 else '#000000'
    
    LIGHT_TEXT_COLOR = apply_alpha_to_hex(TEXT_COLOR, 0.2)
    SUPER_LIGHT_TEXT_COLOR = apply_alpha_to_hex(TEXT_COLOR, 0.08)

    is_dev_mode = False  # system.manager.config.get('system.dev_mode', False)

    # {'''border: 1px solid red;''' if is_dev_mode else ''}
    # {'border: 1px solid red;' if is_dev_mode else ''}   border: 1px solid red;
    # {'''border: 1px solid red;''' if is_dev_mode else ''}
# QWidget.conf:hover {{
#     border: 1px solid blue;
# }}

    # QPushButton#homebutton:checked {{
    #     background-color: none;
    #     color: {TEXT_COLOR};
    # }}
    # QPushButton#homebutton:checked:hover {{
    #     background-color: {apply_alpha_to_hex(TEXT_COLOR, 0.05)};
    #     color: {TEXT_COLOR};
    # }}

    return f"""
QWidget {{
    background-color: {PRIMARY_COLOR};
    border-radius: 5px;
    {'''border: 1px solid red;''' if is_dev_mode else ''}
}}
QWidget.track-control {{
    border: 1px solid {apply_alpha_to_hex(TEXT_COLOR, 0.3)};
}}
QWidget.central {{
    border-top-left-radius: 24px;
    border-bottom-left-radius: 10px;
    border-bottom-right-radius: 0px;
}}
QWidget.edit-bar {{
    background-color: {SECONDARY_COLOR};
    /* border-radius: 4px; */
}}
QCheckBox {{
    color: {TEXT_COLOR};
}}
QCheckBox::indicator:unchecked {{
    border: 1px solid #2b2b2b;
    background: #ffffff;
}}
QCheckBox::indicator:checked {{
    border: 1px solid #2b2b2b;
    background: #ffffff url(":/resources/icon-tick.svg") no-repeat center center;
}}
QCheckBox::indicator:unchecked:disabled {{
    border: 1px solid #2b2b2b;
    background: #a2a2a2;
}}
QCheckBox::indicator:checked:disabled {{
    border: 1px solid #2b2b2b;
    background: #a2a2a2;
}}
QComboBox {{
    color: {TEXT_COLOR};
}}
QComboBox QAbstractItemView {{
    border: 0px;
    selection-background-color: lightgray; /* Background color for hovered/selected item */
    background-color: {SECONDARY_COLOR}; /* Background color for dropdown */
    color: {TEXT_COLOR};
}}
QDoubleSpinBox {{
    color: {TEXT_COLOR};
}}
QGraphicsView {{
    border: 1px solid {apply_alpha_to_hex(TEXT_COLOR, 0.39)};
}}
QLabel {{
    color: {TEXT_COLOR};
    padding-right: 10px;
}}
QLabel.dynamic_color {{
    padding-right: 10px;
    font-size: 10pt;
    background: transparent;
}}
QLabel.bubble-name-label {{
    color: {apply_alpha_to_hex(TEXT_COLOR, 0.60)};
    padding-right: 10px;
}}
QLineEdit {{
    background-color: {SECONDARY_COLOR};
    color: {TEXT_COLOR};
    padding-left: 5px;
}}
QLineEdit:disabled {{
    color: #4d4d4d;
}}
QListWidget::item {{
    color: {TEXT_COLOR};
}}
QMenu {{
    background-color: {SECONDARY_COLOR};
}}
QMenu::item {{
    color: {TEXT_COLOR};
    padding: 2px 10px 2px 10px;
    border: 1px solid transparent;
    spacing: 10px;
}}
QMenu::item:selected {{
    color: {TEXT_COLOR};
    border-color: {PRIMARY_COLOR};
    background: {SECONDARY_COLOR};
}}
QMenu::item:disabled {{
    color: {apply_alpha_to_hex(TEXT_COLOR, 0.5)};
    padding-left: 10px;
}}
QMenu::separator {{
     height: 2px;
     margin: 2px 5px 2px 4px;
}}
QMenu::indicator {{
     width: 20px;
     height: 13px;
}}
QPushButton.send {{
    background-color: {SECONDARY_COLOR};
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
    border-top-left-radius: 0px;
    border-bottom-left-radius: 0px;
    color: {TEXT_COLOR};
}}
QPushButton.send:hover {{
    background-color: {apply_alpha_to_hex(TEXT_COLOR, 0.05)};
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
    border-top-left-radius: 0px;
    border-bottom-left-radius: 0px;
    color: {TEXT_COLOR};
}}
QPushButton:hover {{
    background-color: {apply_alpha_to_hex(TEXT_COLOR, 0.05)};
}}
QPushButton {{
    background-color: {apply_alpha_to_hex(TEXT_COLOR, 0.0)};
    color: {TEXT_COLOR};
    border-radius: 3px;
    outline: none;
}}
QPushButton:checked {{
    background-color: {apply_alpha_to_hex(TEXT_COLOR, 0.05)};
    border-radius: 3px;
}}
QPushButton:checked:hover {{
    background-color: {apply_alpha_to_hex(TEXT_COLOR, 0.05)};
    border-radius: 3px;
}}
QPushButton.branch-buttons {{
    background-color: none;
    border-radius: 3px;
}}
QPushButton.branch-buttons.hover {{
    background-color: {apply_alpha_to_hex(TEXT_COLOR, 0.05)};
    border-radius: 3px;
}}
QSpinBox {{
    color: {TEXT_COLOR};
}}
QTabBar::tab {{
    background: {PRIMARY_COLOR};
    border: 1px solid {SECONDARY_COLOR};
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    padding: 5px;
    min-width: 50px;
    color: {TEXT_COLOR};
}}
QTabBar::tab:selected, QTabBar::tab:hover {{
    background: {SECONDARY_COLOR};
}}
QTabBar::tab:selected {{
    border-bottom-color: transparent;
}}
QTabWidget::pane {{
    border: 0px;
    top: -1px;
}}
QToolBar {{
    spacing: 0px;
    border: none;
}}
QToolButton {{
    background-color: transparent;
    border: none;
    border-radius: 3px;
    padding: 4px;
    margin: 0px;
    color: {TEXT_COLOR};
}}
QToolButton:hover {{
    background-color: {apply_alpha_to_hex(TEXT_COLOR, 0.05)};
}}
QToolButton:pressed {{
    background-color: {apply_alpha_to_hex(TEXT_COLOR, 0.1)};
}}
QToolButton:checked {{
    background-color: {apply_alpha_to_hex(TEXT_COLOR, 0.05)};
}}
QToolButton:checked:hover {{
    background-color: {apply_alpha_to_hex(TEXT_COLOR, 0.1)};
}}
QMenuBar {{
    spacing: 0px;
    border: none;
}}
QMenuBar::item {{
    color: {TEXT_COLOR};
    padding: 2px 20px 2px 20px;
    border: 1px solid transparent;
    spacing: 20px;
}}
QMenuBar::item:selected {{
    color: {TEXT_COLOR};
    border-color: {PRIMARY_COLOR};
    background: {SECONDARY_COLOR};
}}
QMenuBar::separator {{
     height: 2px;
     margin: 2px 5px 2px 4px;
}}
QPlainTextEdit {{
    background-color: {SECONDARY_COLOR};
    font-size: {TEXT_SIZE}px;
    color: {TEXT_COLOR};
    border-radius: 12px;
    padding-left: 5px;
}}
QTextEdit {{
    background-color: {SECONDARY_COLOR};
    font-size: {TEXT_SIZE}px;
    color: {TEXT_COLOR};
    border-radius: 12px;
    padding-left: 5px;
}}
QTextEdit a {{
    color: #007bff;
    text-decoration: none;
}}
QTextEdit.msgbox {{
    background-color: {SECONDARY_COLOR};
    border-radius: 12px;
    border-top-right-radius: 0px;
    border-bottom-right-radius: 0px;
    font-size: {TEXT_SIZE}px;
}}
QTreeWidget::item {{
    height: 25px;
}}
QTreeWidget::item:selected {{
    background-color: {apply_alpha_to_hex(TEXT_COLOR, 0.2)};
}}
QTreeWidget#input_items::item {{
    height: 50px;
}}
QHeaderView::section {{
    background-color: {PRIMARY_COLOR};
    color: {TEXT_COLOR};
    border: 0px;
}}
QTableView {{
    gridline-color: #3a3a3a;
    background-color: transparent;
    alternate-background-color: transparent;
    selection-background-color: {LIGHT_TEXT_COLOR};
    color: {TEXT_COLOR};
}}
QTableView::item {{
    padding: 4px;
    border: none;
}}
QTableView::item:selected {{
    background-color: {LIGHT_TEXT_COLOR};
}}
QTreeView, QListView, QTableView {{
    color: {TEXT_COLOR};
}}
QScrollBar:vertical {{
    width: 6px;
    background: transparent;
}}
QScrollBar::handle:vertical {{
    background: rgba(255, 255, 255, 0.15);
    min-height: 20px;
    border-radius: 3px;
}}
QScrollBar::handle:vertical:hover {{
    background: rgba(255, 255, 255, 0.25);
}}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    height: 0px;
    background: transparent;
}}
QScrollBar:horizontal {{
    height: 6px;
    background: transparent;
}}
QScrollBar::handle:horizontal {{
    background: rgba(255, 255, 255, 0.15);
    min-width: 20px;
    border-radius: 3px;
}}
QScrollBar::handle:horizontal:hover {{
    background: rgba(255, 255, 255, 0.25);
}}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {{
    width: 0px;
    background: transparent;
}}
QSplitter::handle:vertical {{
    border-top: 1px solid {LIGHT_TEXT_COLOR};   /* exact 1px line */
}}
QSplitter::handle:horizontal {{
    border-left: 1px solid {LIGHT_TEXT_COLOR};   /* exact 1px line */
}}
"""
