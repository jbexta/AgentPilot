
import json
import os

from PySide6.QtCore import QRunnable
from PySide6.QtGui import Qt
from PySide6.QtWidgets import *

from src.gui.config import ConfigPages, ConfigFields, ConfigDBTree, ConfigTabs, \
    ConfigJoined, ConfigJsonTree, get_widget_value, CHBoxLayout, ConfigWidget, \
    ConfigPlugin, ConfigExtTree
from src.gui.pages.blocks import Page_Block_Settings
from src.gui.pages.tools import Page_Tool_Settings
# from src.plugins.matrix.modules.settings_plugin import Page_Settings_Matrix
from src.plugins.openinterpreter.src import interpreter
from src.system.plugins import get_plugin_class
# from interpreter import interpreter
from src.utils import sql
from src.gui.widgets import ContentPage, IconButton, PythonHighlighter, find_main_widget, \
    BreadcrumbWidget  # , CustomTabBar
from src.utils.helpers import display_messagebox, block_signals, block_pin_mode, convert_model_json_to_obj

# from src.plugins.crewai.modules.settings_plugin import Page_Settings_CrewAI
from src.plugins.openaiassistant.modules.settings_plugin import Page_Settings_OAI

from src.gui.pages.models import Page_Models_Settings
from src.utils.reset import reset_application


class Page_Settings(ConfigPages):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.main = parent
        self.icon_path = ":/resources/icon-settings.png"

        self.try_add_breadcrumb_widget()  # root_title='Settings')
        # self.breadcrumb_widget = BreadcrumbWidget(parent=self)  #, node_title='Settings')
        self.breadcrumb_text = 'Settings'
        # self.layout.addWidget(self.breadcrumb_widget)
        self.include_in_breadcrumbs = True

        # ContentPageTitle = ContentPage(main=self.main, title='Settings')
        # self.layout.addWidget(ContentPageTitle)

        self.pages = {
            'System': self.Page_System_Settings(self),
            'Display': self.Page_Display_Settings(self),
            # 'Defaults': self.Page_Default_Settings(self),
            'Models': Page_Models_Settings(self),
            'Blocks': Page_Block_Settings(self),
            'Roles': self.Page_Role_Settings(self),
            'Tools': Page_Tool_Settings(self),
            'Files': self.Page_Files_Settings(self),
            'Envs': self.Page_Environments_Settings(self),
            'Sets': self.Page_Sets_Settings(self),
            'VecDB': self.Page_VecDB_Settings(self),
            'Spaces': self.Page_Workspace_Settings(self),
            'Plugins': self.Page_Plugin_Settings(self),
            # 'Schedule': self.Page_Schedule_Settings(self),
            # 'Matrix': self.Page_Matrix_Settings(self),
            # 'Sandbox': self.Page_Role_Settings(self),
            # "Vector DB": self.Page_Role_Settings(self),
        }
        self.pinnable_pages = ['Blocks', 'Tools']
        self.is_pin_transmitter=True

    def save_config(self):
        """Saves the config to database when modified"""
        json_config = json.dumps(self.get_config())
        sql.execute("UPDATE `settings` SET `value` = ? WHERE `field` = 'app_config'", (json_config,))
        self.main.system.config.load()
        system_config = self.main.system.config.dict
        self.load_config(system_config)

    class Page_System_Settings(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.main = parent.main
            self.label_width = 125
            self.margin_left = 20
            self.conf_namespace = 'system'
            self.schema = [
                {
                    'text': 'Language',
                    'type': 'LanguageComboBox',
                    'default': 'en',
                },
                {
                    'text': 'Dev mode',
                    'type': bool,
                    'default': False,
                },
                {
                    'text': 'Telemetry',
                    'type': bool,
                    'default': True,
                },
                {
                    'text': 'Always on top',
                    'type': bool,
                    'default': True,
                },
                {
                    'text': 'Auto-run code',
                    'type': int,
                    'minimum': 0,
                    'maximum': 30,
                    'step': 1,
                    'default': 5,
                    'label_width': 145,
                    'has_toggle': True,
                },                {
                    'text': 'Auto-complete',
                    'type': bool,
                    'width': 40,
                    'tooltip': 'This is not an AI completion, it''s a statistical approach to quickly add commonly used phrases',
                    'default': True,
                },
                {
                    'text': 'Voice input method',
                    'type': ('None',),
                    'default': 'None',
                },
                {
                    'text': 'Default chat model',
                    'type': 'ModelComboBox',
                    'default': 'mistral/mistral-large-latest',
                },
                {
                    'text': 'Auto title',
                    'type': bool,
                    'width': 40,
                    'default': True,
                    'row_key': 0,
                },
                {
                    'text': 'Auto-title model',
                    'label_position': None,
                    'type': 'ModelComboBox',
                    'default': 'mistral/mistral-large-latest',
                    'row_key': 0,
                },
                {
                    'text': 'Auto-title prompt',
                    'type': str,
                    'default': 'Generate a brief and concise title for a chat that begins with the following message:\n\n{user_msg}',
                    'num_lines': 5,
                    'label_position': 'top',
                    'stretch_x': True,
                },
            ]

        def after_init(self):  # !! #
            self.dev_mode.stateChanged.connect(lambda state: self.toggle_dev_mode(state))
            self.always_on_top.stateChanged.connect(self.main.toggle_always_on_top)

            # add a button 'Reset database'
            self.reset_app_btn = QPushButton('Reset Application')
            self.reset_app_btn.clicked.connect(reset_application)
            self.layout.addWidget(self.reset_app_btn)

        def toggle_dev_mode(self, state=None):
            # pass
            if state is None and hasattr(self, 'dev_mode'):
                state = self.dev_mode.isChecked()

            self.main.page_chat.top_bar.btn_info.setVisible(state)
            self.main.page_settings.pages['System'].reset_app_btn.setVisible(state)

            # get all instances of ConfigWidget

            for config_pages in self.main.findChildren(ConfigPages):
                for page_name, page in config_pages.pages.items():
                    page_is_dev_mode = getattr(page, 'IS_DEV_MODE', False)
                    if not page_is_dev_mode:
                        continue
                    config_pages.settings_sidebar.page_buttons[page_name].setVisible(state)

    class Page_Display_Settings(ConfigJoined):
        def __init__(self, parent):
            super().__init__(parent=parent)

            self.conf_namespace = 'display'
            button_layout = CHBoxLayout()
            self.btn_delete_theme = IconButton(
                parent=self,
                icon_path=':/resources/icon-minus.png',
                tooltip='Delete theme',
                size=18,
            )
            self.btn_save_theme = IconButton(
                parent=self,
                icon_path=':/resources/icon-save.png',
                tooltip='Save current theme',
                size=18,
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

        def save_theme(self):
            current_config = self.get_current_display_config()
            current_config_str = json.dumps(current_config, sort_keys=True)
            theme_exists = sql.get_scalar("""
                SELECT COUNT(*)
                FROM themes
                WHERE config = ?
            """, (current_config_str,))
            if theme_exists:
                display_messagebox(
                    icon=QMessageBox.Warning,
                    text='Theme already exists',
                    title='Error',
                )
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

            retval = display_messagebox(
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
                    'primary_color': get_widget_value(display_page.primary_color),
                    'secondary_color': get_widget_value(display_page.secondary_color),
                    'text_color': get_widget_value(display_page.text_color),
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
                self.theme.currentIndexChanged.connect(self.changeTheme)

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

                system = self.parent.parent.main.system
                system.config.load()
                system.roles.load()
                self.parent.parent.main.apply_stylesheet()

                page_settings = self.parent.parent
                app_config = system.config.dict
                page_settings.load_config(app_config)
                page_settings.load()


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
                        'type': 'ColorPickerWidget',
                        'default': '#ffffff',
                    },
                    {
                        'text': 'Secondary color',
                        'type': 'ColorPickerWidget',
                        'default': '#ffffff',
                    },
                    {
                        'text': 'Text color',
                        'type': 'ColorPickerWidget',
                        'default': '#ffffff',
                    },
                    {
                        'text': 'Text font',
                        'type': 'FontComboBox',
                        'default': 'Default',
                    },
                    {
                        'text': 'Text size',
                        'type': int,
                        'minimum': 6,
                        'maximum': 72,
                        'default': 12,
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
                        'text': 'Bubble avatar position',
                        'type': ('Top', 'Middle',),
                        'default': 'Top',
                    },
                    {
                        'text': 'Bubble spacing',
                        'type': int,
                        'minimum': 0,
                        'maximum': 10,
                        'default': 5,
                    },
                    {
                        'text': 'Window margin',
                        'type': int,
                        'minimum': 0,
                        'maximum': 69,
                        'default': 6,
                    },
                    {
                        'text': 'Pin blocks',
                        'type': bool,
                        'visible': False,
                        'default': True,
                    },
                    {
                        'text': 'Pin tools',
                        'type': bool,
                        'visible': False,
                        'default': True,
                    },
                ]

            def load(self):
                super().load()
                self.parent.widgets[0].load()  # load theme
                main = find_main_widget(self)
                main.apply_margin()

            def update_config(self):
                super().update_config()
                main = self.parent.parent.main
                main.system.config.load()
                main.apply_stylesheet()
                main.page_chat.message_collection.refresh_waiting_bar()
                self.load()  # reload theme combobox for custom

    class Page_Role_Settings(ConfigDBTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                db_table='roles',
                propagate=False,
                query="""
                    SELECT
                        name,
                        id
                    FROM roles""",
                schema=[
                    {
                        'text': 'Roles',
                        'key': 'name',
                        'type': str,
                        'stretch': True,
                    },
                    {
                        'text': 'id',
                        'key': 'id',
                        'type': int,
                        'visible': False,
                    },
                ],
                add_item_prompt=('Add Role', 'Enter a name for the role:'),
                del_item_prompt=('Delete Role', 'Are you sure you want to delete this role?'),
                readonly=False,
                layout_type=QHBoxLayout,
                config_widget=self.Role_Config_Widget(parent=self),
                tree_header_hidden=True,
                tree_width=150,
                tree_height=665,
            )

        def on_edited(self):
            self.parent.main.system.roles.load()
            self.parent.main.apply_stylesheet()

        class Role_Config_Widget(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.label_width = 175
                self.schema = [
                    {
                        'text': 'Bubble bg color',
                        'type': 'ColorPickerWidget',
                        'default': '#3b3b3b',
                    },
                    {
                        'text': 'Bubble text color',
                        'type': 'ColorPickerWidget',
                        'default': '#c4c4c4',
                    },
                    {
                        'text': 'Bubble image size',
                        'type': int,
                        'minimum': 3,
                        'maximum': 100,
                        'default': 25,
                    },
                    # {
                    #     'text': 'Append to',
                    #     'type': 'RoleComboBox',
                    #     'default': 'None'
                    # },
                    # {
                    #     'text': 'Visibility type',
                    #     'type': ('Global', 'Local',),
                    #     'default': 'Global',
                    # },
                    # {
                    #     'text': 'Bubble class',
                    #     'type': str,
                    #     'width': 350,
                    #     'num_lines': 15,
                    #     'label_position': 'top',
                    #     'highlighter': PythonHighlighter,
                    #     'default': '',
                    # },
                ]

    class Page_Files_Settings(ConfigTabs):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.IS_DEV_MODE = True
            self.main = find_main_widget(self)
            self.pages = {
                'Filesystem': self.Page_Filesystem(parent=self),
                'Extensions': self.Page_Extensions(parent=self),
                # 'Folders': self.Page_Folders(parent=self),
            }

        class Page_Filesystem(ConfigDBTree):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    db_table='files',
                    propagate=False,
                    query="""
                        SELECT
                            name,
                            id,
                            folder_id
                        FROM files""",
                    schema=[
                        {
                            'text': 'Files',
                            'key': 'file',
                            'type': str,
                            'label_position': None,
                            'stretch': True,
                        },
                        {
                            'text': 'id',
                            'key': 'id',
                            'type': int,
                            'visible': False,
                        },
                    ],
                    add_item_prompt=('NA', 'NA'),
                    del_item_prompt=('NA', 'NA'),
                    tree_header_hidden=True,
                    readonly=True,
                    layout_type=QHBoxLayout,
                    config_widget=self.File_Config_Widget(parent=self),
                    folder_key='filesystem',
                    tree_width=350,
                    folders_groupable=True,
                )

            # def load(self, select_id=None, append=False):
            #     if not self.query:
            #         return
            #
            #     print("Loading directories...")   # DEBUG
            #
            #     folder_query = """
            #         SELECT
            #             id,
            #             name,
            #             parent_id,
            #             type,
            #             ordr
            #         FROM folders
            #         WHERE `type` = ?
            #         ORDER BY ordr
            #     """
            #
            #     folders_data = sql.get_results(query=folder_query, params=(self.folder_key,))
            #     print("folders_data:", folders_data) # DEBUG
            #     folders_dict = self._build_nested_dict(folders_data)
            #     print("folders_dict:", folders_dict) # DEBUG
            #     data = sql.get_results(query=self.query, params=self.query_params)
            #     print("data:", data) # DEBUG
            #
            #     data = self._merge_folders(folders_dict, data)
            #
            #     print("merged data:", data) # DEBUG
            #
            #     self.tree.load(
            #         data=data,
            #         append=append,
            #         folders_data=folders_data,
            #         select_id=select_id,
            #         folder_key=self.folder_key,
            #         init_select=self.init_select,
            #         readonly=self.readonly,
            #         schema=self.schema
            #     )

            def add_item(self, column_vals=None, icon=None):
                with block_pin_mode():
                    file_dialog = QFileDialog()
                    file_dialog.setFileMode(QFileDialog.ExistingFile)
                    file_dialog.setOption(QFileDialog.ShowDirsOnly, False)
                    file_dialog.setFileMode(QFileDialog.Directory)
                    path, _ = file_dialog.getOpenFileName(None, "Choose Files", "", options=file_dialog.Options())

                if path:
                    self.add_path(path)

            # def delete_item(self):
            #     item = self.tree.currentItem()
            #     if not item:
            #         return None
            #     tag = item.data(0, Qt.UserRole)
            #     if tag == 'folder':
            #         return
            #     super().delete_item()

            def add_ext_folder(self):
                with block_pin_mode():
                    file_dialog = QFileDialog()
                    file_dialog.setFileMode(QFileDialog.Directory)
                    file_dialog.setOption(QFileDialog.ShowDirsOnly, True)
                    path = file_dialog.getExistingDirectory(self, "Choose Directory", "")
                    if path:
                        self.add_path(path)

            def add_path(self, path):
                base_directory = os.path.dirname(path)
                directories = []
                while base_directory:
                    directories.append(os.path.basename(base_directory))
                    next_directory = os.path.dirname(base_directory)
                    base_directory = next_directory if next_directory != base_directory else None

                directories = reversed(directories)
                parent_id = None
                for directory in directories:
                    parent_id = super().add_folder(directory, parent_id)

                name = os.path.basename(path)
                config = json.dumps({'path': path, })
                sql.execute(f"INSERT INTO `files` (`name`, `folder_id`) VALUES (?, ?)", (name, parent_id,))
                last_insert_id = sql.get_scalar("SELECT seq FROM sqlite_sequence WHERE name=?", (self.db_table,))
                self.load(select_id=last_insert_id)
                return True

            def dragEnterEvent(self, event):
                # Check if the event contains file paths to accept it
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()

            def dragMoveEvent(self, event):
                # Check if the event contains file paths to accept it
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()

            def dropEvent(self, event):
                # Get the list of URLs from the event
                urls = event.mimeData().urls()

                # Extract local paths from the URLs
                paths = [url.toLocalFile() for url in urls]

                for path in paths:
                    self.add_path(path)

                event.acceptProposedAction()

            class File_Config_Widget(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.label_width = 175
                    self.schema = []

        class Page_Extensions(ConfigDBTree):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    db_table='file_exts',
                    propagate=False,
                    query="""
                        SELECT
                            name,
                            id,
                            folder_id
                        FROM file_exts
                        ORDER BY name""",
                    schema=[
                        {
                            'text': 'Name',
                            'key': 'name',
                            'type': str,
                            'stretch': True,
                        },
                        {
                            'text': 'id',
                            'key': 'id',
                            'type': int,
                            'visible': False,
                        },
                    ],
                    add_item_prompt=('Add extension', "Enter the file extension without the '.' prefix"),
                    del_item_prompt=('Delete extension', 'Are you sure you want to delete this extension?'),
                    readonly=False,
                    folder_key='file_exts',
                    layout_type=QHBoxLayout,
                    config_widget=self.Extensions_Config_Widget(parent=self),
                    tree_width=150,
                )

            def on_edited(self):
                self.parent.main.system.files.load()

            class Extensions_Config_Widget(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.schema = [
                        {
                            'text': 'Default attachment method',
                            'type': ('Add path to message','Add contents to message','Encode base64',),
                            'default': 'Add path to message',
                            # 'width': 385,
                        },
                    ]

    class Page_VecDB_Settings(ConfigDBTree):
        def __init__(self, parent):
            self.IS_DEV_MODE = True
            super().__init__(
                parent=parent,
                db_table='vectordbs',
                propagate=False,
                query="""
                    SELECT
                        name,
                        id,
                        folder_id
                    FROM vectordbs""",
                schema=[
                    {
                        'text': 'Name',
                        'key': 'name',
                        'type': str,
                        'stretch': True,
                    },
                    {
                        'text': 'id',
                        'key': 'id',
                        'type': int,
                        'visible': False,
                    },
                ],
                add_item_prompt=('Add VecDB', 'Enter a name for the vector db:'),
                del_item_prompt=('Delete VecDB', 'Are you sure you want to delete this vector db?'),
                readonly=False,
                layout_type=QHBoxLayout,
                folder_key='vectordbs',
                config_widget=self.VectorDBConfig(parent=self),
                tree_width=150,
            )

        def on_edited(self):
            self.parent.main.system.vectordbs.load()

        class VectorDBConfig(ConfigPlugin):
            def __init__(self, parent):
                super().__init__(
                    parent,
                    plugin_type='VectorDBSettings',
                    plugin_json_key='vec_db_provider',
                    plugin_label_text='VectorDB provider',
                    none_text='LanceDB'
                )
                self.default_class = self.LanceDB_VecDBConfig

            class LanceDB_VecDBConfig(ConfigTabs):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.pages = {
                        'Config': self.Page_VecDB_Config(parent=self),
                        # 'Test run': self.Page_Run(parent=self),
                    }

                class Page_VecDB_Config(ConfigJoined):
                    def __init__(self, parent):
                        super().__init__(parent=parent, layout_type=QHBoxLayout)
                        self.widgets = [
                            # self.Tool_Info_Widget(parent=self),
                            self.Env_Vars_Widget(parent=self),
                        ]

                    # class
                    class Env_Vars_Widget(ConfigJsonTree):
                        def __init__(self, parent):
                            super().__init__(parent=parent,
                                             add_item_prompt=('NA', 'NA'),
                                             del_item_prompt=('NA', 'NA'))
                            self.parent = parent
                            self.conf_namespace = 'env_vars'
                            self.schema = [
                                {
                                    'text': 'Variable',
                                    'type': str,
                                    'width': 120,
                                    'default': 'Variable name',
                                },
                                {
                                    'text': 'Value',
                                    'type': str,
                                    'stretch': True,
                                    'default': '',
                                },
                            ]

    class Page_Environments_Settings(ConfigDBTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                db_table='sandboxes',
                propagate=False,
                query="""
                    SELECT
                        name,
                        id,
                        folder_id
                    FROM sandboxes""",
                schema=[
                    {
                        'text': 'Name',
                        'key': 'name',
                        'type': str,
                        'stretch': True,
                    },
                    {
                        'text': 'id',
                        'key': 'id',
                        'type': int,
                        'visible': False,
                    },
                ],
                add_item_prompt=('Add Environment', 'Enter a name for the environment:'),
                del_item_prompt=('Delete Environment', 'Are you sure you want to delete this environment?'),
                readonly=False,
                layout_type=QHBoxLayout,
                folder_key='sandboxes',
                config_widget=self.SandboxConfig(parent=self),
                tree_width=160,
            )

        def on_edited(self):
            self.parent.main.system.environments.load()

        class SandboxConfig(ConfigPlugin):
            def __init__(self, parent):
                super().__init__(
                    parent,
                    plugin_type='SandboxSettings',
                    plugin_json_key='sandbox_type',  # todo - rename
                    plugin_label_text='Environment Type',
                    none_text='Local'
                )
                self.default_class = self.Local_SandboxConfig

            class Local_SandboxConfig(ConfigTabs):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.pages = {
                        'Venv': self.Page_Venv(parent=self),
                        'Env vars': self.Page_Env_Vars(parent=self),
                    }

                class Page_Venv(ConfigJoined):
                    def __init__(self, parent):
                        super().__init__(parent=parent, layout_type=QVBoxLayout)
                        self.widgets = [
                            self.Page_Venv_Config(parent=self),
                            self.Page_Packages(parent=self),
                        ]

                    class Page_Venv_Config(ConfigFields):
                        def __init__(self, parent):
                            super().__init__(parent=parent)
                            self.schema = [
                                {
                                    'text': 'Venv',
                                    'type': 'VenvComboBox',
                                    'width': 350,
                                    'label_position': None,
                                    'default': 'default',
                                },
                            ]

                        def update_config(self):
                            super().update_config()
                            self.reload_venv()

                        def reload_venv(self):
                            self.parent.widgets[1].load()

                    class Page_Packages(ConfigJoined):
                        def __init__(self, parent):
                            super().__init__(parent=parent, layout_type=QHBoxLayout)
                            self.widgets = [
                                self.Installed_Libraries(parent=self),
                                self.Pypi_Libraries(parent=self),
                            ]
                            self.setFixedHeight(450)

                        class Installed_Libraries(ConfigExtTree):
                            def __init__(self, parent):
                                super().__init__(
                                    parent=parent,
                                    conf_namespace='installed_packages',
                                    schema=[
                                        {
                                            'text': 'Installed packages',
                                            'key': 'name',
                                            'type': str,
                                            'width': 150,
                                        },
                                        {
                                            'text': '',
                                            'key': 'version',
                                            'type': str,
                                            'width': 25,
                                        },
                                    ],
                                    add_item_prompt=('NA', 'NA'),
                                    del_item_prompt=('Uninstall Package', 'Are you sure you want to uninstall this package?'),
                                    tree_width=150,
                                    tree_height=450,
                                )

                            class LoadRunnable(QRunnable):
                                def __init__(self, parent):
                                    super().__init__()
                                    self.parent = parent
                                    # self.main = find_main_widget(self)
                                    self.page_chat = parent.main.page_chat

                                def run(self):
                                    import sys
                                    from src.system.base import manager
                                    try:
                                        venv_name = self.parent.parent.config.get('venv', 'default')
                                        if venv_name == 'default':
                                            packages = sorted(set([module.split('.')[0] for module in sys.modules.keys()]))
                                            rows = [[package, ''] for package in packages]
                                        else:
                                            packages = manager.venvs.venvs[venv_name].list_packages()
                                            rows = packages

                                        self.parent.fetched_rows_signal.emit(rows)
                                    except Exception as e:
                                        self.page_chat.main.error_occurred.emit(str(e))

                            def add_item(self):
                                pypi_visible = self.parent.widgets[1].isVisible()
                                self.parent.widgets[1].setVisible(not pypi_visible)

                        class Pypi_Libraries(ConfigDBTree):
                            def __init__(self, parent):
                                super().__init__(
                                    parent=parent,
                                    db_table='pypi_packages',
                                    propagate=False,
                                    query="""
                                        SELECT
                                            name,
                                            folder_id
                                        FROM pypi_packages
                                        LIMIT 1000""",
                                    schema=[
                                        {
                                            'text': 'Browse PyPI',
                                            'key': 'name',
                                            'type': str,
                                            'width': 150,
                                        },
                                    ],
                                    tree_width=150,
                                    tree_height=450,
                                    layout_type=QHBoxLayout,
                                    folder_key='pypi_packages',
                                    searchable=True,
                                )
                                self.btn_sync = IconButton(
                                    parent=self.tree_buttons,
                                    icon_path=':/resources/icon-refresh.png',
                                    tooltip='Update package list',
                                    size=18,
                                )
                                self.btn_sync.clicked.connect(self.sync_pypi_packages)
                                self.tree_buttons.add_button(self.btn_sync, 'btn_sync')
                                self.hide()

                            def on_item_selected(self):
                                pass

                            def filter_rows(self):
                                if not self.show_tree_buttons:
                                    return

                                search_query = self.tree_buttons.search_box.text().lower()
                                if not self.tree_buttons.search_box.isVisible():
                                    search_query = ''

                                if search_query == '':
                                    self.query = """
                                        SELECT
                                            name,
                                            folder_id
                                        FROM pypi_packages
                                        LIMIT 1000
                                    """
                                else:
                                    self.query = f"""
                                        SELECT
                                            name,
                                            folder_id
                                        FROM pypi_packages
                                        WHERE name LIKE '%{search_query}%'
                                        LIMIT 1000
                                    """
                                self.load()

                            def sync_pypi_packages(self):
                                import requests
                                import re

                                url = 'https://pypi.org/simple/'
                                response = requests.get(url, stream=True)

                                items = []
                                batch_size = 10000

                                pattern = re.compile(r'<a[^>]*>(.*?)</a>')
                                previous_overlap = ''
                                for chunk in response.iter_content(chunk_size=10240):
                                    if chunk:
                                        chunk_str = chunk.decode('utf-8')
                                        chunk = previous_overlap + chunk_str
                                        previous_overlap = chunk_str[-100:]

                                        matches = pattern.findall(chunk)
                                        for match in matches:
                                            item_name = match.strip()
                                            if item_name:
                                                items.append(item_name)

                                    if len(items) >= batch_size:
                                        # generate the query directly without using params
                                        query = 'INSERT OR IGNORE INTO pypi_packages (name) VALUES ' + ', '.join(
                                            [f"('{item}')" for item in items])
                                        sql.execute(query)
                                        items = []

                                # Insert any remaining items
                                if items:
                                    query = 'INSERT OR IGNORE INTO pypi_packages (name) VALUES ' + ', '.join(
                                        [f"('{item}')" for item in items])
                                    sql.execute(query)

                                print('Scraping and storing items completed.')
                                self.load()

                class Page_Env_Vars(ConfigJsonTree):
                        def __init__(self, parent):
                            super().__init__(parent=parent,
                                             add_item_prompt=('NA', 'NA'),
                                             del_item_prompt=('NA', 'NA'))
                            self.parent = parent
                            # self.setFixedWidth(250)
                            self.conf_namespace = 'env_vars'
                            self.schema = [
                                {
                                    'text': 'Env Var',
                                    'type': str,
                                    'width': 120,
                                    'default': 'Variable name',
                                },
                                {
                                    'text': 'Value',
                                    'type': str,
                                    'width': 120,
                                    'stretch': True,
                                    'default': '',
                                },
                            ]

    class Page_Logs_Settings(ConfigDBTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                db_table='logs',
                propagate=False,
                query="""
                    SELECT
                        name,
                        id,
                        folder_id
                    FROM logs""",
                schema=[
                    {
                        'text': 'Name',
                        'key': 'name',
                        'type': str,
                        'stretch': True,
                    },
                    {
                        'text': 'id',
                        'key': 'id',
                        'type': int,
                        'visible': False,
                    },
                ],
                add_item_prompt=None,
                del_item_prompt=('Delete Log', 'Are you sure you want to delete this log?'),
                readonly=True,
                layout_type=QVBoxLayout,
                folder_key='logs',
                config_widget=self.LogConfig(parent=self),
                # tree_width=150,
            )

        def on_edited(self):
            self.parent.main.system.logs.load()

        class LogConfig(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.schema = [
                    {
                        'text': 'Log type',
                        'type': ('File', 'Database', 'API',),
                        'default': 'File',
                    },
                    {
                        'text': 'Log path',
                        'type': str,
                        'default': '',
                    },
                    {
                        'text': 'Log level',
                        'type': ('Debug', 'Info', 'Warning', 'Error', 'Critical',),
                        'default': 'Info',
                    },
                    {
                        'text': 'Log format',
                        'type': str,
                        'default': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    },
                ]

    class Page_Workspace_Settings(ConfigDBTree):
        def __init__(self, parent):
            self.IS_DEV_MODE = True
            super().__init__(
                parent=parent,
                db_table='workspaces',
                propagate=False,
                query="""
                    SELECT
                        name,
                        id,
                        folder_id
                    FROM workspaces""",
                schema=[
                    {
                        'text': 'Workspaces',
                        'key': 'name',
                        'type': str,
                        'stretch': True,
                    },
                    {
                        'text': 'id',
                        'key': 'id',
                        'type': int,
                        'visible': False,
                    },
                ],
                add_item_prompt=('Add Workspace', 'Enter a name for the workspace:'),
                del_item_prompt=('Delete Workspace', 'Are you sure you want to delete this workspace?'),
                readonly=False,
                layout_type=QHBoxLayout,
                folder_key='workspaces',
                config_widget=self.WorkspaceConfig(parent=self),
                tree_width=150,
            )

        def on_edited(self):
            self.parent.main.system.workspaces.load()

        class WorkspaceConfig(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.schema = [
                    {
                        'text': 'Environment',
                        'type': 'EnvironmentComboBox',
                        'default': 'Local',
                    },
                ]

    class Page_Plugin_Settings(ConfigTabs):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.conf_namespace = 'plugins'

            self.pages = {
                # 'GPT Pilot': self.Page_Test(parent=self),
                # 'CrewAI': Page_Settings_CrewAI(parent=self),
                # 'Matrix': Page_Settings_Matrix(parent=self),
                'OAI': Page_Settings_OAI(parent=self),
                # 'Test Pypi': self.Page_Pypi_Packages(parent=self),
            }

    class Page_Sets_Settings(ConfigDBTree):
        def __init__(self, parent):
            self.IS_DEV_MODE = True
            super().__init__(
                parent=self,
                db_table='contexts',
                query="""
                    SELECT
                        c.name,
                        c.id,
                        CASE
                            WHEN json_extract(c.config, '$.members') IS NOT NULL THEN
                                CASE
                                    WHEN json_array_length(json_extract(c.config, '$.members')) > 2 THEN
                                        json_array_length(json_extract(c.config, '$.members')) || ' members'
                                    WHEN json_array_length(json_extract(c.config, '$.members')) = 2 THEN
                                        COALESCE(json_extract(json_extract(c.config, '$.members'), '$[1].config."info.name"'), 'Assistant')
                                    WHEN json_extract(json_extract(c.config, '$.members'), '$[1].config._TYPE') = 'agent' THEN
                                        json_extract(json_extract(c.config, '$.members'), '$[1].config."info.name"')
                                    ELSE
                                        json_array_length(json_extract(c.config, '$.members')) || ' members'
                                END
                            ELSE
                                CASE
                                    WHEN json_extract(c.config, '$._TYPE') = 'workflow' THEN
                                        '1 member'
                                    ELSE
                                        COALESCE(json_extract(c.config, '$."info.name"'), 'Assistant')
                                END
                        END as member_count,
                        CASE
                            WHEN json_extract(config, '$._TYPE') = 'workflow' THEN
                                (
                                    SELECT GROUP_CONCAT(json_extract(m.value, '$.config."info.avatar_path"'), '//##//##//')
                                    FROM json_each(json_extract(config, '$.members')) m
                                    WHERE COALESCE(json_extract(m.value, '$.del'), 0) = 0
                                )
                            ELSE
                                COALESCE(json_extract(config, '$."info.avatar_path"'), '')
                        END AS avatar,
                        c.folder_id
                    FROM contexts c
                    LEFT JOIN (
                        SELECT
                            context_id,
                            MAX(id) as latest_message_id
                        FROM contexts_messages
                        GROUP BY context_id
                    ) cmsg ON c.id = cmsg.context_id
                    WHERE c.parent_id IS NULL
                    AND c.kind = 'SET'
                    GROUP BY c.id
                    ORDER BY
                        COALESCE(cmsg.latest_message_id, 0) DESC
                    LIMIT ? OFFSET ?;
                    """,
                schema=[
                    {
                        'text': 'name',
                        'type': str,
                        'image_key': 'avatar',
                        'stretch': True,
                    },
                    {
                        'text': 'id',
                        'key': 'id',
                        'type': int,
                        'visible': False,
                    },
                    {
                        'key': 'member_count',
                        'text': '',
                        'type': str,
                        'width': 100,
                    },
                    {
                        'key': 'avatar',
                        'text': '',
                        'type': str,
                        'visible': False,
                    },
                    # {
                    #     'text': '',
                    #     'type': QPushButton,
                    #     'icon': ':/resources/icon-chat.png',
                    #     'func': self.on_chat_btn_clicked,
                    #     'width': 45,
                    # },
                ],
                kind='SET',
                dynamic_load=True,
                add_item_prompt=('Add Context', 'Enter a name for the context:'),
                del_item_prompt=('Delete Context', 'Are you sure you want to permanently delete this context?'),
                layout_type=QVBoxLayout,
                config_widget=None,
                # tree_width=600,
                tree_height=600,
                tree_header_hidden=True,
                folder_key='sets',
                init_select=False,
                filterable=True,
                searchable=True,
                archiveable=True,
            )


class Page_Lists_Settings(ConfigDBTree):
    def __init__(self, parent):
        super().__init__(
            parent=parent,
            db_table='lists',
            propagate=False,
            query="""
                SELECT
                    name,
                    id,
                    folder_id
                FROM blocks""",
            schema=[
                {
                    'text': 'Blocks',
                    'key': 'name',
                    'type': str,
                    'stretch': True,
                },
                {
                    'text': 'id',
                    'key': 'id',
                    'type': int,
                    'visible': False,
                },
            ],
            add_item_prompt=('Add Block', 'Enter a placeholder tag for the block:'),
            del_item_prompt=('Delete Block', 'Are you sure you want to delete this block?'),
            folder_key='blocks',
            readonly=False,
            layout_type=QHBoxLayout,
            config_widget=self.Block_Config_Widget(parent=self),
            tree_width=150,
        )

    def on_edited(self):
        self.parent.main.system.blocks.load()

    def on_item_selected(self):
        super().on_item_selected()
        # self.config_widget.output.setPlainText('')
        # self.config_widget.output.setVisible(True)
        self.config_widget.toggle_run_box(visible=False)

    class Block_Config_Widget(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            # self.main = find_main_widget(self)
            from src.system.base import manager
            self.schema = [
                {
                    'text': 'Type',
                    'key': 'block_type',
                    'type': ('Text', 'Prompt', 'Code', 'Metaprompt'),
                    'width': 100,
                    'default': 'Text',
                    'row_key': 0,
                },
                {
                    'text': 'Model',
                    'key': 'prompt_model',
                    'type': 'ModelComboBox',
                    'label_position': None,
                    'default': '',  # convert_model_json_to_obj(manager.config.dict.get('system.default_chat_model', 'mistral/mistral-large-latest')),  # todo
                    'row_key': 0,
                },
                {
                    'text': 'Language',
                    'type':
                    ('AppleScript', 'HTML', 'JavaScript', 'Python', 'PowerShell', 'R', 'React', 'Ruby', 'Shell',),
                    'width': 100,
                    'tooltip': 'The language of the code, to be passed to open interpreter',
                    'label_position': None,
                    'row_key': 0,
                    'default': 'Python',
                },
                {
                    'text': 'Data',
                    'type': str,
                    'default': '',
                    'num_lines': 23,
                    'width': 385,
                    'label_position': None,
                },
            ]

        def after_init(self):  # !! #
            self.refresh_model_visibility()

            self.btn_run = QPushButton('Run')
            self.btn_run.clicked.connect(self.on_run)

            self.output = QTextEdit()
            self.output.setReadOnly(True)
            self.output.setFixedHeight(150)
            self.layout.addWidget(self.btn_run)
            self.layout.addWidget(self.output)

        def on_run(self):
            name = self.parent.tree.get_column_value(0)
            output = self.parent.parent.main.system.blocks.compute_block(name=name)  # , source_text=source_text)
            self.output.setPlainText(output)
            # self.output.setVisible(True)
            self.toggle_run_box(visible=True)

        def toggle_run_box(self, visible):
            self.output.setVisible(visible)
            if not visible:
                self.output.setPlainText('')
            self.data.setFixedHeight(443 if visible else 593)

        def load(self):
            super().load()
            self.refresh_model_visibility()

        def update_config(self):
            super().update_config()
            self.refresh_model_visibility()

        def refresh_model_visibility(self):
            block_type = get_widget_value(self.block_type)
            model_visible = block_type == 'Prompt' or block_type == 'Metaprompt'
            lang_visible = block_type == 'Code'
            self.prompt_model.setVisible(model_visible)
            self.language.setVisible(lang_visible)
