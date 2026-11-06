from PySide6.QtGui import QColor, QPalette

from gui import system
from utils.helpers import apply_alpha_to_hex

PRIMARY_COLOR = '#ff1b1a1b'
SECONDARY_COLOR = '#ff292629'
TEXT_COLOR = '#ffcacdd5'
ACCENT_COLOR_1 = '#ff438bb9'
ACCENT_COLOR_2 = '#ff6aab73'
NOTIFY_NEW_COLOR = '#ff3d8fe0'
NOTIFY_DONE_COLOR = '#ff4cb85c'


def is_native_style():
    return system.manager.config.get('display.widget_style', 'Flat') == 'Native'


def get_palette():
    palette = QPalette()
    primary = QColor(PRIMARY_COLOR)
    secondary = QColor(SECONDARY_COLOR)
    text = QColor(TEXT_COLOR)
    accent = QColor(ACCENT_COLOR_1)
    for role, color in (
        (QPalette.Window, primary),
        (QPalette.Base, secondary),
        (QPalette.AlternateBase, primary),
        (QPalette.Button, secondary),
        (QPalette.ToolTipBase, secondary),
        (QPalette.WindowText, text),
        (QPalette.Text, text),
        (QPalette.ButtonText, text),
        (QPalette.ToolTipText, text),
        (QPalette.Highlight, accent),
        (QPalette.Link, accent),
    ):
        palette.setColor(role, color)
    palette.setColor(QPalette.PlaceholderText, QColor(apply_alpha_to_hex(TEXT_COLOR, 0.5)))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(apply_alpha_to_hex(TEXT_COLOR, 0.4)))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(apply_alpha_to_hex(TEXT_COLOR, 0.4)))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(apply_alpha_to_hex(TEXT_COLOR, 0.4)))
    return palette


def get_stylesheet():
    global PRIMARY_COLOR, SECONDARY_COLOR, TEXT_COLOR, ACCENT_COLOR_1, ACCENT_COLOR_2

    system_config = system.manager.config  # system.config.dict if system else {}

    PRIMARY_COLOR = system_config.get('display.primary_color', '#ff1b1a1b')
    SECONDARY_COLOR = system_config.get('display.secondary_color', '#ff292629')
    TEXT_COLOR = system_config.get('display.text_color', '#ffc4c4c4')
    TEXT_SIZE = system_config.get('display.text_size', 12)
    ACCENT_COLOR_1 = system_config.get('display.accent_color_1', '#ff438bb9')
    ACCENT_COLOR_2 = system_config.get('display.accent_color_2', '#ff6aab73')
    CORNER_RADIUS = system_config.get('display.corner_radius', 5)
    native = is_native_style()
    native_scrollbars = system_config.get('display.scrollbars', 'Thin') == 'Native'

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
    {'' if native else f'background-color: {PRIMARY_COLOR};'}
    {'' if native else f'border-radius: {CORNER_RADIUS}px;'}
    {'''border: 1px solid red;''' if is_dev_mode else ''}
}}
QWidget.track-control {{
    border: 1px solid {apply_alpha_to_hex(TEXT_COLOR, 0.3)};
}}
QWidget.central {{
    background-color: {PRIMARY_COLOR};
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
{'' if native else f'''QCheckBox::indicator:unchecked {{
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
}}'''}
QComboBox {{
    color: {TEXT_COLOR};
}}
QComboBox QAbstractItemView {{
    border: 0px;
    selection-background-color: lightgray; /* Background color for hovered/selected item */
    selection-color: {PRIMARY_COLOR}; /* Text color for hovered/selected item */
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
    {'' if native else f'background-color: {SECONDARY_COLOR};'}
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
QPushButton.splitter-flip {{
    background-color: {SECONDARY_COLOR};
    border: 1px solid {LIGHT_TEXT_COLOR};
    border-radius: 12px;
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
{'' if native else f'''QTabBar::tab {{
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
}}'''}
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
    {'' if native else f'background-color: {SECONDARY_COLOR};'}
    font-size: {TEXT_SIZE}px;
    color: {TEXT_COLOR};
    {'' if native else 'border-radius: 12px;'}
    padding-left: 5px;
}}
QTextEdit {{
    {'' if native else f'background-color: {SECONDARY_COLOR};'}
    font-size: {TEXT_SIZE}px;
    color: {TEXT_COLOR};
    {'' if native else 'border-radius: 12px;'}
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
QTreeWidget {{
    color: {TEXT_COLOR};
}}
QTreeWidget::item {{
    height: 25px;
    color: {TEXT_COLOR};
}}
QTreeWidget::item:selected {{
    background-color: {apply_alpha_to_hex(TEXT_COLOR, 0.2)};
}}
QTreeWidget#input_items::item {{
    height: 50px;
}}
{'' if native else f'''QHeaderView::section {{
    background-color: {PRIMARY_COLOR};
    color: {TEXT_COLOR};
    border: 0px;
}}'''}
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
{'' if native_scrollbars else f'''QScrollBar:vertical {{
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
}}'''}
QSplitter::handle:vertical {{
    border-top: 1px solid {LIGHT_TEXT_COLOR};   /* exact 1px line */
}}
QSplitter::handle:horizontal {{
    border-left: 1px solid {LIGHT_TEXT_COLOR};   /* exact 1px line */
}}QWidget#demoOverlay {{
    background: transparent;
    border-radius: 0px;
}}
QWidget#demoOverlayCard {{
    background-color: {SECONDARY_COLOR};
    border: 1px solid {apply_alpha_to_hex(TEXT_COLOR, 0.18)};
    border-radius: 12px;
}}
QLabel#demoOverlayTitle {{
    color: {TEXT_COLOR};
    font-size: 13pt;
    font-weight: bold;
    padding: 0px;
    background: transparent;
}}
QLabel#demoOverlaySegment {{
    color: {ACCENT_COLOR_1};
    font-size: 9pt;
    padding: 0px;
    background: transparent;
}}
QLabel#demoOverlayNarration {{
    color: {TEXT_COLOR};
    font-size: 10pt;
    padding: 0px;
    background: transparent;
}}
QPushButton#demoOverlayStop {{
    background-color: #ffb33a3a;
    color: #ffffffff;
    border: 0px;
    border-radius: 6px;
    padding: 4px 14px;
    font-size: 9pt;
}}
QPushButton#demoOverlayStop:hover {{
    background-color: #ffcf4646;
}}
QLabel#blockMenuName {{ padding: 4px; background-color: #00000000; }}
QPushButton#blockMenuDelete {{ background-color: #ff4444; color: white; border: none; border-radius: 10px; font-weight: bold; }}
QPushButton#blockMenuDelete:hover {{ background-color: #cc0000; }}
QPushButton.filter-button {{ padding: 5px; }}
QPushButton.align-left {{ text-align: left; }}
QLabel#notificationLabel {{ color: white; font-size: 11pt; }}
QLabel.dynamic_color[status="Loaded"] {{ color: #6aab73; }}
QLabel.dynamic_color[status="Baked"], QLabel.dynamic_color[status="Modified"] {{ color: #438BB9; }}
QLabel.dynamic_color[status="Unloaded"], QLabel.dynamic_color[status="Error"],
QLabel.dynamic_color[status="Externally Modified"] {{ color: #B94343; }}
QFileDialog#addonFileDialog {{ color: black; }}
QLabel#fileTreeBookmarksLabel {{ font-weight: bold; margin: 5px 0px; }}
QLabel#fileTreeComputerLabel {{ font-weight: bold; margin: 15px 0px 5px 0px; }}
QLabel#fileTreeRecentTitle {{ font-size: 11pt; padding: 8px 4px; }}
QPushButton#entityFieldLabel {{ background: transparent; border: none; text-align: left; padding: 0; }}
QFrame#comboFilterPopup {{ background-color: {PRIMARY_COLOR}; border: 1px solid {apply_alpha_to_hex(TEXT_COLOR, 0.3)}; }}
.text-field {{ border-radius: 6px; }}
.text-field[transparent="true"] {{ background-color: transparent; }}
#textExpandButton {{ background-color: transparent; }}
QPushButton.color-picker {{ background-color: white; border: 1px solid {apply_alpha_to_hex(TEXT_COLOR, 0.20)}; }}
QSlider.int-slider::groove:horizontal, QSlider.int-slider::groove:vertical {{
    border: 1px solid {apply_alpha_to_hex(TEXT_COLOR, 0.3)}; height: 8px; background: {apply_alpha_to_hex(TEXT_COLOR, 0.1)}; border-radius: 2px; }}
QSlider.int-slider::handle:horizontal, QSlider.int-slider::handle:vertical {{
    background: {apply_alpha_to_hex(TEXT_COLOR, 0.5)}; border: 1px solid {apply_alpha_to_hex(TEXT_COLOR, 0.6)}; width: 8px; border-radius: 2px; }}
QSlider.int-slider::handle:horizontal:hover, QSlider.int-slider::handle:vertical:hover {{
    background: {apply_alpha_to_hex(TEXT_COLOR, 0.7)}; border: 1px solid {apply_alpha_to_hex(TEXT_COLOR, 0.8)}; }}
QSlider.int-slider::sub-page:horizontal, QSlider.int-slider::sub-page:vertical {{ background: {apply_alpha_to_hex(ACCENT_COLOR_1, 0.6)}; border: none; }}
QSlider.int-slider[fill="false"]::sub-page:horizontal, QSlider.int-slider[fill="false"]::sub-page:vertical {{ background: transparent; }}
QSlider.int-slider::add-page:horizontal, QSlider.int-slider::add-page:vertical {{ background: none; border: none; }}
QLabel.slider-label {{ font-size: 10px; }}
#videoPreviewSurface {{ background-color: black; }}
QFrame.question-option {{ background-color: transparent; border-radius: 3px; }}
QFrame.question-option[focused="true"] {{ background-color: #2a3a3d; }}
QFrame.question-option QLabel {{ color: #9fb8b5; font-weight: 400; background: transparent; }}
QFrame.question-option[focused="true"] QLabel {{ color: #44d4c8; }}
QFrame.question-option[selected="true"] QLabel {{ font-weight: 600; }}
QFrame.question-option QLineEdit {{ background-color: #141c1e; color: #d1e8e5; border: 1px solid #2a3a3d; border-radius: 3px; padding: 2px 4px; }}
QLabel#claudePathLabel {{ color: gray; }}
#financeChart {{ border: none; }}
QLabel.run-status {{ color: #888; font-weight: bold; }}
QLabel.run-status[running="true"] {{ color: #4a4; }}
QLineEdit#workflowTitleLabel {{ color: {apply_alpha_to_hex(TEXT_COLOR, 0.90)}; background-color: transparent; }}
QLineEdit#workflowTitleLabel:hover {{ color: {TEXT_COLOR}; }}
#bubbleFadeOverlay {{
    background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:0, y2:0.9, stop:0 rgba(0, 0, 0, 0), stop:1 {PRIMARY_COLOR});
    border-radius: 10px; }}
QPushButton.send[joined="true"], QPushButton.send[joined="true"]:hover {{
    border-top-right-radius: 12px; border-bottom-right-radius: 12px; }}
QPushButton.send[joined="false"], QPushButton.send[joined="false"]:hover {{
    border-top-left-radius: 12px; border-bottom-left-radius: 12px; border-top-right-radius: 12px; border-bottom-right-radius: 12px; }}
QLabel#previewPollLabel {{ color: #aaa; padding: 8px; font-style: italic; }}
QLabel#calendarDayLabel {{ font-size: 10pt; font-weight: bold; }}
QTreeView#feedsTree::item {{ padding: 2px; }}
QLabel#feedStatusLabel {{ color: gray; font-style: italic; }}
QListWidget#feedItemsList {{ font-size: 12px; outline: none; }}
QListWidget#feedItemsList::item {{ padding: 8px; border-bottom: 1px solid #ddd; }}
QListWidget#feedItemsList::item:selected {{ background-color: #e3f2fd; color: black; }}
QListWidget#feedItemsList::item:hover {{ background-color: #f5f5f5; }}
QTextBrowser#feedItemViewer {{ font-size: 14px; padding: 10px; }}
QPushButton#videoStudioOpenButton {{
    background-color: {apply_alpha_to_hex(SECONDARY_COLOR, 0.8)}; color: {TEXT_COLOR};
    border: 1px solid {apply_alpha_to_hex(TEXT_COLOR, 0.4)}; border-radius: 4px; padding: 5px 10px; }}
QPushButton#videoStudioOpenButton:hover {{ background-color: {SECONDARY_COLOR}; }}
QLabel#videoStudioTimeLabel {{ color: {TEXT_COLOR}; background: {SECONDARY_COLOR}; padding: 5px; }}
QPushButton#imageStudioOpenButton {{
    background-color: rgba(50, 50, 50, 200); color: white; border: 1px solid #666; border-radius: 4px; padding: 5px 10px; }}
QPushButton#imageStudioOpenButton:hover {{ background-color: rgba(70, 70, 70, 220); }}
QSlider.slopify-slider::groove:horizontal {{ background: transparent; height: 4px; border: none; border-radius: 2px; }}
QSlider.slopify-slider::handle:horizontal {{ background: transparent; border: none; }}
QSlider.slopify-slider::sub-page:horizontal {{ background: {TEXT_COLOR}; border-radius: 2px; }}
QSlider.slopify-slider::add-page:horizontal {{ background: {apply_alpha_to_hex(TEXT_COLOR, 0.3)}; border-radius: 2px; }}
QSlider.slopify-slider[hovered="true"]::handle:horizontal {{
    background: {TEXT_COLOR}; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; }}
QSlider.slopify-slider[hovered="true"]::sub-page:horizontal {{ background: #1db954; }}
QLabel#slopifyLibraryHeader {{ font-size: 13px; font-weight: bold; padding: 4px 8px 4px 4px; }}
QListWidget#slopifyPlaylists {{ background: transparent; border: none; outline: none; }}
QListWidget#slopifyPlaylists::item {{ border-radius: 6px; padding: 2px 6px; min-height: 48px; }}
QListWidget#slopifyPlaylists::item:selected {{ background: {apply_alpha_to_hex(TEXT_COLOR, 0.12)}; }}
QListWidget#slopifyPlaylists::item:hover:!selected {{ background: {apply_alpha_to_hex(TEXT_COLOR, 0.06)}; }}
QLabel.slopify-dim {{ color: {apply_alpha_to_hex(TEXT_COLOR, 0.65)}; font-size: 12px; }}
QTableView#slopifyTracks, QTableView#slopifyTracks QHeaderView {{ background-color: {apply_alpha_to_hex(TEXT_COLOR, 0.03)}; }}
QLabel#newProjectTitle, QLabel#dialogTitle {{ font-size: 15pt; font-weight: 600; }}
QLabel#dialogDetail {{ color: {apply_alpha_to_hex(TEXT_COLOR, 0.5)}; font-size: 9pt; }}
QLabel#dialogError {{ color: #e5737a; }}
QPlainTextEdit#vcsDiff {{ font-family: monospace; }}
QLabel#githubCode {{ font-family: monospace; font-size: 22pt; font-weight: 600; letter-spacing: 4px; }}
QLabel.new-project-label, QLabel.dialog-label {{ color: {apply_alpha_to_hex(TEXT_COLOR, 0.75)}; font-weight: 600; }}
QLabel#newProjectLocation {{ color: {apply_alpha_to_hex(TEXT_COLOR, 0.5)}; font-size: 9pt; }}
QLabel#newProjectError {{ color: #e5737a; }}
QLabel#newProjectStatus {{ color: {apply_alpha_to_hex(TEXT_COLOR, 0.6)}; font-size: 9pt; }}
QDialog#newProjectDialog QLineEdit, QDialog#newTaskDialog QLineEdit,
QDialog#newTaskDialog QPlainTextEdit,
QDialog#githubPublishDialog QLineEdit, QDialog#addRemoteDialog QLineEdit,
QDialog#gitIdentityDialog QLineEdit {{
    background-color: {SECONDARY_COLOR};
    border: 1px solid {apply_alpha_to_hex(TEXT_COLOR, 0.12)};
    border-radius: 4px; padding: 6px 8px; }}
QDialog#newProjectDialog QLineEdit:focus, QDialog#newTaskDialog QLineEdit:focus,
QDialog#newTaskDialog QPlainTextEdit:focus,
QDialog#githubPublishDialog QLineEdit:focus, QDialog#addRemoteDialog QLineEdit:focus,
QDialog#gitIdentityDialog QLineEdit:focus {{ border-color: {ACCENT_COLOR_1}; }}
QDialog#newProjectDialog QComboBox {{
    background-color: {SECONDARY_COLOR};
    border: 1px solid {apply_alpha_to_hex(TEXT_COLOR, 0.12)};
    border-radius: 4px; padding: 5px 8px; }}
QDialog#newProjectDialog QComboBox:focus {{ border-color: {ACCENT_COLOR_1}; }}
QDialog#newProjectDialog QComboBox::drop-down {{ border: none; background: transparent; width: 22px; }}
QDialog#newProjectDialog QComboBox::down-arrow {{
    image: url(":/resources/icon-arrow-down.png"); width: 10px; height: 10px; }}
QPushButton.new-project-mode {{
    border: 1px solid {apply_alpha_to_hex(TEXT_COLOR, 0.12)};
    border-radius: 6px; padding: 10px 14px; text-align: left; }}
QPushButton.new-project-mode:checked {{
    border-color: {ACCENT_COLOR_1};
    background-color: {apply_alpha_to_hex(ACCENT_COLOR_1, 0.15)}; }}
QDialogButtonBox QPushButton, QPushButton.dialog-button {{
    border: 1px solid {apply_alpha_to_hex(TEXT_COLOR, 0.15)};
    border-radius: 4px; padding: 6px 18px; min-width: 60px; }}
QDialogButtonBox QPushButton:focus, QPushButton.dialog-button:focus {{
    background-color: {apply_alpha_to_hex(TEXT_COLOR, 0.1)}; }}
QDialogButtonBox QPushButton[primary="true"], QPushButton.dialog-button[primary="true"] {{
    background-color: {ACCENT_COLOR_1}; border-color: {ACCENT_COLOR_1}; color: white; }}
QDialogButtonBox QPushButton[primary="true"]:hover, QPushButton.dialog-button[primary="true"]:hover {{
    background-color: {apply_alpha_to_hex(ACCENT_COLOR_1, 0.85)}; }}
QDialogButtonBox QPushButton:disabled, QPushButton.dialog-button:disabled {{
    color: {apply_alpha_to_hex(TEXT_COLOR, 0.4)}; }}
QDialogButtonBox QPushButton[primary="true"]:disabled, QPushButton.dialog-button[primary="true"]:disabled {{
    background-color: {apply_alpha_to_hex(ACCENT_COLOR_1, 0.3)};
    border-color: transparent; }}
QProgressBar#newProjectProgress {{ background-color: {apply_alpha_to_hex(TEXT_COLOR, 0.08)}; border: none; border-radius: 2px; }}
QProgressBar#newProjectProgress::chunk {{ background-color: {ACCENT_COLOR_1}; border-radius: 2px; }}
"""
