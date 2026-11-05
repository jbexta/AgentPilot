import json

from PySide6.QtCore import QTimer, Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import QMessageBox, QPushButton

from gui import system
from gui.gui_utils.helpers import clear_layout, find_main, safe_single_shot
from gui.gui_utils.layouts import CHBoxLayout
from gui.gui_utils.icon_button import IconButton
from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_joined import ConfigJoined
from gui.widgets.config_widget import ConfigWidget
from utils.helpers import convert_to_safe_case, set_module_type, display_message_box, display_message, get_text
from utils import sql

THEME_KEYS = (
    'primary_color',
    'secondary_color',
    'accent_color_1',
    'accent_color_2',
    'link_color',
    'text_color',
    'widget_style',
    'scrollbars',
    'corner_radius',
)
class ThemeTile(QPushButton):
    """The theme name above a miniature window drawn in its colors."""
    def __init__(self, parent, name, display_config):
        super().__init__(parent=parent)
        self.name = name
        self.colors = {key: QColor(value) for key, value in display_config.items()
                       if key.endswith('_color') or key.startswith('accent_color')}
        self.selected = False
        self.setFixedSize(150, 112)
        self.setCursor(Qt.PointingHandCursor)

    def set_selected(self, selected):
        self.selected = selected
        self.update()

    def faded(self, key, alpha):
        color = QColor(self.colors[key])
        color.setAlphaF(alpha)
        return color

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        rect = QRectF(self.rect()).adjusted(6, 4, -6, -6)

        name_rect = QRectF(rect.left(), rect.top(), rect.width(), 20)
        painter.setPen(self.palette().color(QPalette.ButtonText))
        name = self.fontMetrics().elidedText(
            self.name, Qt.ElideRight, int(name_rect.width()))
        painter.drawText(name_rect, Qt.AlignLeft | Qt.AlignVCenter, name)

        window = QRectF(rect.left(), name_rect.bottom() + 2,
                        rect.width(), rect.bottom() - name_rect.bottom() - 2)
        path = QPainterPath()
        path.addRoundedRect(window, 5, 5)
        painter.save()
        painter.setClipPath(path)
        painter.setPen(Qt.NoPen)
        painter.fillRect(window, self.colors['primary_color'])

        sidebar = QRectF(window.left(), window.top(), 20, window.height())
        painter.fillRect(sidebar, self.colors['secondary_color'])
        for i in range(4):
            icon = QRectF(sidebar.left() + 6, sidebar.top() + 7 + i * 13, 8, 8)
            if i == 0:
                painter.fillRect(icon.adjusted(-6, -3, 6, 3), self.faded('text_color', 0.08))
            painter.setBrush(self.colors['accent_color_1'] if i == 0
                             else self.faded('text_color', 0.5))
            painter.drawRoundedRect(icon, 2, 2)

        left = sidebar.right() + 8
        top = window.top() + 8
        lines = ((0.6, 'text_color', 0.9), (0.85, 'text_color', 0.5),
                 (0.7, 'text_color', 0.5), (0.4, 'link_color', 1))
        width = window.right() - 8 - left
        for i, (fraction, key, alpha) in enumerate(lines):
            painter.setBrush(self.faded(key, alpha))
            painter.drawRoundedRect(QRectF(left, top + i * 9, width * fraction, 4), 2, 2)

        field = QRectF(left, window.bottom() - 18, width - 22, 11)
        painter.setBrush(self.colors['secondary_color'])
        painter.drawRoundedRect(field, 3, 3)
        painter.setBrush(self.colors['accent_color_2'])
        painter.drawRoundedRect(QRectF(field.right() + 4, field.top(), 18, 11), 3, 3)
        painter.restore()

        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(self.faded('text_color', 0.2), 1))
        painter.drawPath(path)

        if self.selected:
            painter.setPen(QPen(self.palette().color(QPalette.Highlight), 2))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 5, 5)


@set_module_type('Pages')
class Page_Display_Settings(ConfigJoined):
    display_name = 'Display'
    page_type = 'settings'  # either 'settings', 'main', or 'any' ('any' means it can be pinned between main and settings)

    def __init__(self, parent):
        super().__init__(parent=parent)

        self.conf_namespace = 'display'
        self.propagate_config = True
        button_layout = CHBoxLayout()
        self.btn_delete_theme = IconButton(
            parent=self,
            icon_path=':/resources/icon-minus.png',
            tooltip='Delete theme',
            size=22,
        )
        self.btn_save_theme = IconButton(
            parent=self,
            icon_path=':/resources/icon-save.png',
            tooltip='Save current theme',
            size=22,
        )
        button_layout.addWidget(self.btn_delete_theme)
        button_layout.addWidget(self.btn_save_theme)
        button_layout.addStretch(1)
        self.layout.addLayout(button_layout)
        self.btn_save_theme.clicked.connect(self.save_theme)
        self.btn_delete_theme.clicked.connect(self.delete_theme)

        self.widgets = [
            self.Page_Display_Themes(parent=self),
            self.Page_Display_Fields(parent=self),
        ]
        self.add_stretch_to_end = True

    def save_theme(self):
        current_config = self.get_current_display_config()
        current_config_str = json.dumps(current_config, sort_keys=True)
        theme_exists = sql.get_scalar("""
            SELECT COUNT(*)
            FROM themes
            WHERE config = ?
        """, (current_config_str,))
        if theme_exists:
            display_message('Theme already exists', 'Error')
            return

        theme_name, ok = get_text(
            self,
            'Save Theme',
            'Enter a name for the theme:',
        )
        if not ok:
            return

        sql.execute("""
            INSERT INTO themes (name, config)
            VALUES (?, ?)
        """, (theme_name, current_config_str))
        self.load()

    def delete_theme(self):
        theme_name = self.widgets[0].selected
        if theme_name is None:
            return

        retval = display_message_box(
            icon=QMessageBox.Warning,
            text=f"Are you sure you want to delete the theme '{theme_name}'?",
            title="Delete Theme",
            buttons=QMessageBox.Yes | QMessageBox.No,
        )

        if retval != QMessageBox.Yes:
            return

        sql.execute("""
            DELETE FROM themes
            WHERE name = ?
        """, (theme_name,))
        self.load()

    def get_current_display_config(self):
        display_page = self.widgets[1]
        # Roles table is deprecated — bubble colours live on bubble module classes
        # and bubbles use a transparent background, so per-bubble theme colour
        # detection is no-longer applicable. Only display.* settings are returned.
        # roles_config_temp = sql.get_results("""
        #     SELECT name, config
        #     FROM roles
        #     """, return_type='dict'
        #                                     )
        # roles_config = {role_name: json.loads(config) for role_name, config in roles_config_temp.items()}

        current_config = {
            # 'assistant': {
            #     'bubble_bg_color': roles_config['assistant']['bubble_bg_color'],
            #     'bubble_text_color': roles_config['assistant']['bubble_text_color'],
            # },
            # 'code': {
            #     'bubble_bg_color': roles_config['code']['bubble_bg_color'],
            #     'bubble_text_color': roles_config['code']['bubble_text_color'],
            # },
            'display': {
                key: getattr(display_page, f'{key}_wgt').get_value()
                for key in THEME_KEYS
            },
            # 'user': {
            #     'bubble_bg_color': roles_config['user']['bubble_bg_color'],
            #     'bubble_text_color': roles_config['user']['bubble_text_color'],
            # },
        }
        return current_config

    class Page_Display_Themes(ConfigWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.propagate_config = False
            self.all_themes = {}
            self.tiles = []
            self.selected = None  # None when the display config matches no theme
            self.layout = CHBoxLayout(self)
            self.layout.setContentsMargins(20, 0, 0, 0)
            self.layout.setSpacing(8)

        def load(self):
            temp_themes = sql.get_results("""
                SELECT name, config
                FROM themes
            """, return_type='dict')
            self.all_themes = {theme_name: json.loads(config) for theme_name, config in temp_themes.items()}

            clear_layout(self.layout)
            self.tiles = []
            for theme_name in self.all_themes:
                tile = ThemeTile(self, theme_name, self.get_theme_display_config(theme_name))
                tile.clicked.connect(lambda _, name=theme_name: self.select_theme(name))
                self.layout.addWidget(tile)
                self.tiles.append(tile)
            self.layout.addStretch(1)

            safe_single_shot(50, self.setTheme)
            # self.setTheme()

        def get_theme_display_config(self, theme_name):
            display_fields = self.parent.widgets[1]
            defaults = {
                convert_to_safe_case(param['text'].lower()): param['default']
                for param in display_fields.schema
            }
            theme_config = {key: defaults[key] for key in THEME_KEYS}
            theme_config.update(self.all_themes[theme_name]['display'])
            return theme_config

        def setTheme(self):
            current_display_config = self.parent.get_current_display_config()['display']
            for theme_name in self.all_themes:
                if self.get_theme_display_config(theme_name) == current_display_config:
                    self.set_selected(theme_name)
                    return
            self.set_selected(None)

        def set_selected(self, theme_name):
            self.selected = theme_name
            for tile in self.tiles:
                tile.set_selected(tile.name == theme_name)

        def select_theme(self, theme_name):
            self.set_selected(theme_name)
            self.changeTheme()

        def changeTheme(self):
            theme_name = self.selected
            if theme_name is None:
                return

            patch_dicts = {
                'settings': {
                    f'display.{key}': value
                    for key, value in self.get_theme_display_config(theme_name).items()
                },
                # 'roles': {}
            }
            # patch settings table
            sql.execute("""
                UPDATE `settings` SET `value` = json_patch(value, ?) WHERE `field` = 'app_config'
            """, (json.dumps(patch_dicts['settings']),))

            # Roles table is deprecated — bubbles use a transparent background
            # and inherit the page colour, so theme primary_color already
            # effectively re-colours bubbles. Per-role patches are no-ops.
            #
            # # todo all roles dynamically
            # if 'user' in self.all_themes[theme_name]:
            #     patch_dicts['roles']['user'] = {
            #         'bubble_bg_color': self.all_themes[theme_name]['user']['bubble_bg_color'],
            #         'bubble_text_color': self.all_themes[theme_name]['user']['bubble_text_color'],
            #     }
            #     # patch user role
            #     sql.execute("""
            #         UPDATE `roles` SET `config` = json_patch(config, ?) WHERE `name` = 'user'
            #     """, (json.dumps(patch_dicts['roles']['user']),))
            # if 'assistant' in self.all_themes[theme_name]:
            #     patch_dicts['roles']['assistant'] = {
            #         'bubble_bg_color': self.all_themes[theme_name]['assistant']['bubble_bg_color'],
            #         'bubble_text_color': self.all_themes[theme_name]['assistant']['bubble_text_color'],
            #     }
            #     # patch assistant role
            #     sql.execute("""
            #         UPDATE `roles` SET `config` = json_patch(config, ?) WHERE `name` = 'assistant'
            #     """, (json.dumps(patch_dicts['roles']['assistant']),))
            # if 'code' in self.all_themes[theme_name]:
            #     patch_dicts['roles']['code'] = {
            #         'bubble_bg_color': self.all_themes[theme_name]['code']['bubble_bg_color'],
            #         'bubble_text_color': self.all_themes[theme_name]['code']['bubble_text_color'],
            #     }
            #     # patch code role
            #     sql.execute("""
            #         UPDATE `roles` SET `config` = json_patch(config, ?) WHERE `name` = 'code'
            #     """, (json.dumps(patch_dicts['roles']['code']),))

            page_settings = self.parent.parent
            # system.manager.load_manager('roles')
            system.manager.load_manager('config')

            app_config = system.manager.config
            page_settings.load_config(app_config)
            page_settings.load()
            main = find_main()
            main.apply_stylesheet()

    class Page_Display_Fields(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent

            self.auto_label_width = True
            self.margin_left = 20
            self.conf_namespace = 'display'
            self.schema = [
                {
                    'text': 'Primary color',
                    'type': 'color_picker',
                    'default': '#ffffff',
                },
                {
                    'text': 'Secondary color',
                    'type': 'color_picker',
                    'default': '#ffffff',
                },
                {
                    'text': 'Accent color 1',
                    'type': 'color_picker',
                    'default': '#438BB9',
                },
                {
                    'text': 'Accent color 2',
                    'type': 'color_picker',
                    'default': '#6aab73',
                },
                {
                    'text': 'Link color',
                    'type': 'color_picker',
                    'default': '#438BB9',
                },
                {
                    'text': 'Text color',
                    'type': 'color_picker',
                    'default': '#ffffff',
                },
                {
                    'text': 'Widget style',
                    'type': ('Flat', 'Native',),
                    'default': 'Flat',
                },
                {
                    'text': 'Scrollbars',
                    'type': ('Thin', 'Native',),
                    'default': 'Thin',
                },
                {
                    'text': 'Corner radius',
                    'type': int,
                    'minimum': 0,
                    'maximum': 24,
                    'step': 1,
                    'default': 5,
                },
                {
                    'text': 'Text font',
                    'type': 'font',
                    'default': 'Default',
                },
                {
                    'text': 'Text size',
                    'type': int,
                    'minimum': 6,
                    'maximum': 72,
                    'step': 1,
                    'default': 12,
                },
                {
                    'text': 'Collapse large bubbles',
                    'type': bool,
                    'default': True,
                },
                {
                    'text': 'Collapse ratio',
                    'type': float,
                    'minimum': 0.1,
                    'maximum': 1.5,
                    'step': 0.1,
                    'default': 0.5,
                },
                {
                    'text': 'Show bubble name',
                    'type': ('In Group', 'Always', 'Never',),
                    'default': 'In Group',
                },
                {
                    'text': 'Show bubble avatar',
                    'type': ('In Group', 'Always', 'Never',),
                    'default': 'In Group',
                },
                {
                    'text': 'Show waiting bar',
                    'type': ('In Group', 'Always', 'Never',),
                    'default': 'In Group',
                },
                {
                    'text': 'Bubble spacing',
                    'type': int,
                    'minimum': 0,
                    'maximum': 10,
                    'step': 1,
                    'default': 5,
                },
                {
                    'text': 'Window margin',
                    'type': int,
                    'minimum': 0,
                    'maximum': 69,
                    'step': 1,
                    'default': 6,
                },
                {
                    'text': 'Workflow view',
                    'type': ('Mini', 'Expanded',),
                    'default': 'Mini',
                },
            ]

        def update_config(self):
            super().update_config()
            if not hasattr(self, '_debounce_timer'):
                self._debounce_timer = QTimer(self)
                self._debounce_timer.setSingleShot(True)
                self._debounce_timer.setInterval(150)
                self._debounce_timer.timeout.connect(self._apply_display)
            self._debounce_timer.start()

        def _apply_display(self):
            main = find_main()
            main.apply_stylesheet()
            main.apply_margin()
            main.page_chat.message_collection.refresh_waiting_bar()
            self.load()  # reload theme tiles for custom
            self.parent.widgets[0].load()