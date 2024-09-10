from src.utils.helpers import apply_alpha_to_hex

PRIMARY_COLOR = '#151515'
SECONDARY_COLOR = '#323232'
TEXT_COLOR = '#c4c4c4'


def get_stylesheet(main):  # system=None):
    global PRIMARY_COLOR, SECONDARY_COLOR, TEXT_COLOR

    system = main.system

    border_radius = '14' if main.expanded else '0'

    system_config = system.config.dict if system else {}
    user_config = system.roles.get_role_config('user') if system else {}
    assistant_config = system.roles.get_role_config('assistant') if system else {}
    code_config = system.roles.get_role_config('code') if system else {}
    tool_config = system.roles.get_role_config('tool') if system else {}

    PRIMARY_COLOR = system_config.get('display.primary_color', '#151515')
    SECONDARY_COLOR = system_config.get('display.secondary_color', '#323232')
    TEXT_COLOR = system_config.get('display.text_color', '#c4c4c4')
    TEXT_SIZE = system_config.get('display.text_size', 12)

    # USER_BUBBLE_BG_COLOR = user_config.get('bubble_bg_color', '#3b3b3b')
    # USER_BUBBLE_TEXT_COLOR = user_config.get('bubble_text_color', '#d1d1d1')
    # ASSISTANT_BUBBLE_BG_COLOR = assistant_config.get('bubble_bg_color', '#29282b')
    # # ASSISTANT_BUBBLE_TEXT_COLOR = assistant_config.get('bubble_text_color', '#b2bbcf')
    # CODE_BUBBLE_BG_COLOR = code_config.get('bubble_bg_color', '#252427')
    # CODE_BUBBLE_TEXT_COLOR = code_config.get('bubble_text_color', '#999999')
    # TOOL_BUBBLE_BG_COLOR = tool_config.get('bubble_bg_color', '#252427')
    # # TOOL_BUBBLE_TEXT_COLOR = tool_config.get('bubble_text_color', '#d1d1d1')

    return f"""
QWidget {{
    background-color: {PRIMARY_COLOR};
    border-radius: 10px;
}}
QWidget.central {{
    border-radius: {border_radius}px;
    border-top-left-radius: 30px;
    border-bottom-right-radius: 0px;
}}
QWidget.window {{
    background-color: {PRIMARY_COLOR};
    border-radius: 10px;
    border-top-left-radius: 30px;
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
QLabel {{
    color: {TEXT_COLOR};
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
QHeaderView::section {{
    background-color: {PRIMARY_COLOR};
    color: {TEXT_COLOR};
    border: 0px;
}}
"""

    # QTextEdit.user {{
    #     background-color: {USER_BUBBLE_BG_COLOR};
    #     border-bottom-left-radius: 0px;
    # }}
    # QTextEdit.assistant {{
    #     background-color: {ASSISTANT_BUBBLE_BG_COLOR};
    #     border-bottom-left-radius: 0px;
    # }}
    # QTextEdit.tool {{
    #     background-color: {TOOL_BUBBLE_BG_COLOR};
    #     border-bottom-left-radius: 0px;
    # }}
    # QTextEdit.code {{
    #     background-color: {CODE_BUBBLE_BG_COLOR};
    #     color: {CODE_BUBBLE_TEXT_COLOR};
    # }}
    #
    # QPushButton.resend {{
    #     background-color: none;
    #     border-radius: 12px;
    # }}
    # QPushButton.resend:hover {{
    #     background-color: {apply_alpha_to_hex(TEXT_COLOR, 0.05)};
    #     border-radius: 12px;
    # }}
    # QPushButton.rerun {{
    #     background-color: {CODE_BUBBLE_BG_COLOR};
    #     border-radius: 12px;
    # }}


    # return f"""
    # QHBoxLayout {{
    #     border: 1px solid red;
    # }}
    # """

# QFileDialog.uniqueFileDialog QListView,
# QFileDialog.uniqueFileDialog QTreeView {{
#     background-color: #ffffff;  /* Replace with the desired background color */
# }}
# QFileDialog.uniqueFileDialog QListView::item,
# QFileDialog.uniqueFileDialog QTreeView::item {{
#     background-color: #ffffff;  /* Replace with the desired background color for item */
#     color: black;  /* Replace with the desired text color */
# }}
# QFileDialog.uniqueFileDialog QListView::item:selected,
# QFileDialog.uniqueFileDialog QTreeView::item:selected {{
#     background-color: #b0c4de;  /* Replace with the desired selection background color */
#     color: black;  /* Replace with the desired selection text color */
# }}