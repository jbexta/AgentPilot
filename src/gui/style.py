from src.utils.helpers import apply_alpha_to_hex

PRIMARY_COLOR = '#151515'
SECONDARY_COLOR = '#323232'
TEXT_COLOR = '#c4c4c4'
PARAM_COLOR = '#c4c4c4'
STRUCTURE_COLOR = '#c4c4c4'


def get_stylesheet():
    global PRIMARY_COLOR, SECONDARY_COLOR, TEXT_COLOR, PARAM_COLOR, STRUCTURE_COLOR
    from src.system.base import manager
    # system = main.system

    system_config = manager.config.dict  # system.config.dict if system else {}

    PRIMARY_COLOR = system_config.get('display.primary_color', '#151515')
    SECONDARY_COLOR = system_config.get('display.secondary_color', '#323232')
    TEXT_COLOR = system_config.get('display.text_color', '#c4c4c4')
    TEXT_SIZE = system_config.get('display.text_size', 12)
    PARAM_COLOR = system_config.get('display.parameter_color', '#c4c4c4')
    STRUCTURE_COLOR = system_config.get('display.structure_color', '#c4c4c4')

    is_dev_mode = manager.config.dict.get('system.dev_mode', False)

    # {'''border: 1px solid red;''' if is_dev_mode else ''}
    # {'border: 1px solid red;' if is_dev_mode else ''}   border: 1px solid red;
    # {'''border: 1px solid red;''' if is_dev_mode else ''}
# QWidget.conf:hover {{
#     border: 1px solid blue;
# }}
    return f"""
QWidget {{
    background-color: {PRIMARY_COLOR};
    border-radius: 10px;
}}
QWidget.central {{
    border-radius: 14px;
    border-top-left-radius: 30px;
    border-bottom-right-radius: 0px;
}}
QWidget.edit-bar {{
    background-color: {SECONDARY_COLOR};
    /* border-radius: 4px; */
}}
QWidget.window {{
    border-radius: 10px;
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
    padding: 2px 20px 2px 20px;
    border: 1px solid transparent;
    spacing: 20px;
}}
QMenu::item:selected {{
    color: {TEXT_COLOR};
    border-color: {PRIMARY_COLOR};
    background: {SECONDARY_COLOR};
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
    color: {TEXT_COLOR};
    border-radius: 3px;
    outline: none;
}}
QPushButton.labelmenuitem {{
    background-color: none;
    color: {apply_alpha_to_hex(TEXT_COLOR, 0.50)};
    font-size: 15px;
    text-align: left;
    border-radius: 3px;
}}
QPushButton.labelmenuitem:hover {{
    background-color: none;
    color: {TEXT_COLOR};
    font-size: 15px;
    border-radius: 3px;
}}
QPushButton.labelmenuitem:checked {{
    background-color: none;
    color: {TEXT_COLOR};
    font-size: 19px;
    border-radius: 3px;
}}
QPushButton.labelmenuitem:checked:hover {{
    background-color: none;
    color: {TEXT_COLOR};
    font-size: 19px;
    border-radius: 3px;
}}
QPushButton.menuitem {{
    color: {TEXT_COLOR};
    border-radius: 3px;
}}
QPushButton#homebutton:checked {{
    background-color: none;
    color: {TEXT_COLOR};
}}
QPushButton#homebutton:checked:hover {{
    background-color: {apply_alpha_to_hex(TEXT_COLOR, 0.05)};
    color: {TEXT_COLOR};
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
QScrollBar {{
    width: 0px;
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
QTreeWidget#input_items::item {{
    height: 50px;
}}
QHeaderView::section {{
    background-color: {PRIMARY_COLOR};
    color: {TEXT_COLOR};
    border: 0px;
}}
"""


# QTreeWidget::branch:has-children:!has-siblings:closed,
# QTreeWidget::branch:closed:has-children:has-siblings {{
#     image: url(:/qt-project.org/styles/commonstyle/images/branch-closed.png);
# }}
#
# QTreeWidget::branch:open:has-children:!has-siblings,
# QTreeWidget::branch:open:has-children:has-siblings {{
#     image: url(:/qt-project.org/styles/commonstyle/images/branch-open.png);
# }}
#
# QTreeWidget::branch:has-children:!has-siblings:closed:hover,
# QTreeWidget::branch:closed:has-children:has-siblings:hover {{
#     image: url(:/qt-project.org/styles/commonstyle/images/branch-closed-on.png);
# }}
#
# QTreeWidget::branch:open:has-children:!has-siblings:hover,
# QTreeWidget::branch:open:has-children:has-siblings:hover {{
#     image: url(:/qt-project.org/styles/commonstyle/images/branch-open-on.png);
# }}
#
# QTreeWidget::branch:has-children:!has-siblings:closed,
# QTreeWidget::branch:closed:has-children:has-siblings {{
#     background: transparent;
#     color: {TEXT_COLOR};
# }}
#
# QTreeWidget::branch:open:has-children:!has-siblings,
# QTreeWidget::branch:open:has-children:has-siblings {{
#     background: transparent;
#     color: {TEXT_COLOR};
# }}