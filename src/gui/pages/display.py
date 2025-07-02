import json

from PySide6.QtWidgets import QMessageBox, QInputDialog

from gui.util import CHBoxLayout, IconButton, safe_single_shot
from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_joined import ConfigJoined
from utils.helpers import block_signals, display_message_box, display_message
from utils import sql


class Page_Display_Settings(ConfigJoined):
    display_name = 'Display'
    page_type = 'settings'  # either 'settings', 'main', or 'any' ('any' means it can be pinned between main and settings)

    def __init__(self, parent):
        super().__init__(parent=parent)

        self.conf_namespace = 'display'
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
            display_message(self, 'Theme already exists', 'Error')
            return

        theme_name, ok = QInputDialog.getText(
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
        theme_name = self.widgets[0].theme.currentText()
        if theme_name == 'Custom':
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
        roles_config_temp = sql.get_results("""
            SELECT name, config
            FROM roles
            """, return_type='dict'
                                            )
        roles_config = {role_name: json.loads(config) for role_name, config in roles_config_temp.items()}

        current_config = {
            'assistant': {
                'bubble_bg_color': roles_config['assistant']['bubble_bg_color'],
                'bubble_text_color': roles_config['assistant']['bubble_text_color'],
            },
            'code': {
                'bubble_bg_color': roles_config['code']['bubble_bg_color'],
                'bubble_text_color': roles_config['code']['bubble_text_color'],
            },
            'display': {
                'primary_color': display_page.primary_color.get_value(),
                'secondary_color': display_page.secondary_color.get_value(),
                'text_color': display_page.text_color.get_value(),
            },
            'user': {
                'bubble_bg_color': roles_config['user']['bubble_bg_color'],
                'bubble_text_color': roles_config['user']['bubble_text_color'],
            },
        }
        return current_config

    class Page_Display_Themes(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.label_width = 185
            self.margin_left = 20
            self.propagate = False
            self.all_themes = {}
            self.schema = [
                {
                    'text': 'Theme',
                    'type': ('Dark',),
                    'width': 100,
                    'default': 'Dark',
                },
            ]

        def load(self):
            temp_themes = sql.get_results("""
                SELECT name, config
                FROM themes
            """, return_type='dict')
            self.all_themes = {theme_name: json.loads(config) for theme_name, config in temp_themes.items()}

            # load items into ComboBox
            with block_signals(self.theme):
                self.theme.clear()
                self.theme.addItems(['Custom'])
                self.theme.addItems(self.all_themes.keys())

            safe_single_shot(50, self.setTheme)
            # self.setTheme()

        def setTheme(self):
            current_display_config = self.parent.get_current_display_config()
            for theme_name in self.all_themes:
                if self.all_themes[theme_name] == current_display_config:
                    # set self.theme (A ComboBox) to the current theme item, NOT setCurrentText
                    with block_signals(self.theme):
                        indx = self.theme.findText(theme_name)
                        self.theme.setCurrentIndex(indx)
                    return
            self.theme.setCurrentIndex(0)

        def after_init(self):
            super().after_init()

            try:
                self.theme.currentIndexChanged.connect(self.changeTheme)
                pass
            except Exception as e:
                pass

        def changeTheme(self):
            theme_name = self.theme.currentText()
            if theme_name == 'Custom':
                return

            patch_dicts = {
                'settings': {
                    'display.primary_color': self.all_themes[theme_name]['display']['primary_color'],
                    'display.secondary_color': self.all_themes[theme_name]['display']['secondary_color'],
                    'display.text_color': self.all_themes[theme_name]['display']['text_color'],
                },
                'roles': {}
            }
            # patch settings table
            sql.execute("""
                UPDATE `settings` SET `value` = json_patch(value, ?) WHERE `field` = 'app_config'
            """, (json.dumps(patch_dicts['settings']),))

            # todo all roles dynamically
            if 'user' in self.all_themes[theme_name]:
                patch_dicts['roles']['user'] = {
                    'bubble_bg_color': self.all_themes[theme_name]['user']['bubble_bg_color'],
                    'bubble_text_color': self.all_themes[theme_name]['user']['bubble_text_color'],
                }
                # patch user role
                sql.execute("""
                    UPDATE `roles` SET `config` = json_patch(config, ?) WHERE `name` = 'user'
                """, (json.dumps(patch_dicts['roles']['user']),))
            if 'assistant' in self.all_themes[theme_name]:
                patch_dicts['roles']['assistant'] = {
                    'bubble_bg_color': self.all_themes[theme_name]['assistant']['bubble_bg_color'],
                    'bubble_text_color': self.all_themes[theme_name]['assistant']['bubble_text_color'],
                }
                # patch assistant role
                sql.execute("""
                    UPDATE `roles` SET `config` = json_patch(config, ?) WHERE `name` = 'assistant'
                """, (json.dumps(patch_dicts['roles']['assistant']),))
            if 'code' in self.all_themes[theme_name]:
                patch_dicts['roles']['code'] = {
                    'bubble_bg_color': self.all_themes[theme_name]['code']['bubble_bg_color'],
                    'bubble_text_color': self.all_themes[theme_name]['code']['bubble_text_color'],
                }
                # patch code role
                sql.execute("""
                    UPDATE `roles` SET `config` = json_patch(config, ?) WHERE `name` = 'code'
                """, (json.dumps(patch_dicts['roles']['code']),))

            page_settings = self.parent.parent
            from system import manager
            manager.load_manager('roles')
            manager.load_manager('config')

            app_config = manager.config
            page_settings.load_config(app_config)
            page_settings.load()
            page_settings.main.apply_stylesheet()

    class Page_Display_Fields(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent

            self.label_width = 185
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
                    'text': 'Text color',
                    'type': 'color_picker',
                    'default': '#ffffff',
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
                {
                    'text': 'Parameter color',
                    'type': 'color_picker',
                    'default': '#438BB9',
                },
                {
                    'text': 'Structure color',
                    'type': 'color_picker',
                    'default': '#6aab73',
                },
            ]

        def update_config(self):
            super().update_config()
            main = self.parent.parent.main
            main.apply_stylesheet()
            main.apply_margin()
            main.page_chat.message_collection.refresh_waiting_bar()
            self.load()  # reload theme combobox for custom
            self.parent.widgets[0].load()
