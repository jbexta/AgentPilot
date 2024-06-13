
import json
import os

from PySide6.QtCore import QFileInfo
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import *

from src.gui.config import ConfigPages, ConfigFields, ConfigDBTree, ConfigTabs, \
    ConfigJoined, ConfigJsonTree, CVBoxLayout, get_widget_value, CHBoxLayout, ConfigWidget, \
    ConfigJsonFileTree
from src.members.workflow import WorkflowSettings
from src.plugins.matrix.modules.settings_plugin import Page_Settings_Matrix
from src.utils import sql, llm
from src.gui.widgets import ContentPage, ModelComboBox, IconButton, PythonHighlighter, find_main_widget
from src.utils.helpers import display_messagebox, block_signals, block_pin_mode

from src.plugins.crewai.modules.settings_plugin import Page_Settings_CrewAI
from src.plugins.openaiassistant.modules.settings_plugin import Page_Settings_OAI


class Page_Settings(ConfigPages):
    def __init__(self, main):
        super().__init__(parent=main)
        self.main = main

        ContentPageTitle = ContentPage(main=main, title='Settings')
        self.layout.addWidget(ContentPageTitle)

        self.pages = {
            'System': self.Page_System_Settings(self),
            'Display': self.Page_Display_Settings(self),
            # 'Defaults': self.Page_Default_Settings(self),
            'Models': self.Page_Models_Settings(self),
            'Blocks': self.Page_Block_Settings(self),
            'Roles': self.Page_Role_Settings(self),
            'Tools': self.Page_Tool_Settings(self),
            'Files': self.Page_Files_Settings(self),
            'VecDB': self.Page_VecDB_Settings(self),
            'SBoxes': self.Page_Sandbox_Settings(self),
            'Plugins': self.Page_Plugin_Settings(self),
            # 'Matrix': self.Page_Matrix_Settings(self),
            # 'Sandbox': self.Page_Role_Settings(self),
            # "Vector DB": self.Page_Role_Settings(self),
        }
        self.build_schema()
        self.settings_sidebar.layout.addStretch(1)

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
            self.label_width = 125
            self.margin_left = 20
            self.namespace = 'system'
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
                    'text': 'Always on top',
                    'type': bool,
                    'default': True,
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
                    'default': 'gpt-3.5-turbo',
                    'row_key': 0,
                },
                {
                    'text': 'Auto-title prompt',
                    'type': str,
                    'default': 'Generate a brief and concise title for a chat that begins with the following message:\n\n{user_msg}',
                    'num_lines': 4,
                    'width': 360,
                },
                {
                    'text': 'Auto-completion',
                    'type': bool,
                    'width': 40,
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
                },
                {
                    'text': 'Voice input method',
                    'type': ('None',),
                    'default': 'None',
                }
            ]

        def after_init(self):
            self.dev_mode.stateChanged.connect(lambda state: self.toggle_dev_mode(state))
            self.always_on_top.stateChanged.connect(self.parent.main.toggle_always_on_top)

            # add a button 'Reset database'
            self.reset_app_btn = QPushButton('Reset Application')
            self.reset_app_btn.clicked.connect(self.reset_application)
            self.layout.addWidget(self.reset_app_btn)

            # add button 'Fix empty titles'
            self.fix_empty_titles_btn = QPushButton('Fix Empty Titles')
            self.fix_empty_titles_btn.clicked.connect(self.fix_empty_titles)
            self.layout.addWidget(self.fix_empty_titles_btn)

        def toggle_dev_mode(self, state=None):
            # pass
            if state is None and hasattr(self, 'dev_mode'):
                state = self.dev_mode.isChecked()

            main = self.parent.main
            main.page_chat.top_bar.btn_info.setVisible(state)
            main.page_settings.pages['System'].reset_app_btn.setVisible(state)
            main.page_settings.pages['System'].fix_empty_titles_btn.setVisible(state)

        def reset_application(self):
            from src.members.workflow import Workflow

            retval = display_messagebox(
                icon=QMessageBox.Warning,
                text="Are you sure you want to permanently reset the database and config? This will permanently delete all contexts, messages, and logs.",
                title="Reset Database",
                buttons=QMessageBox.Ok | QMessageBox.Cancel,
            )

            if retval != QMessageBox.Ok:
                return

            sql.execute('DELETE FROM contexts_messages')
            sql.execute('DELETE FROM contexts_members')
            sql.execute('DELETE FROM contexts')
            sql.execute('DELETE FROM embeddings WHERE id > 1984')
            sql.execute('DELETE FROM logs')
            sql.execute('VACUUM')
            # # self.parent.update_config('system.dev_mode', False)
            # # self.toggle_dev_mode(False)
            raise NotImplementedError()
            # self.parent.main.page_chat.workflow = Workflow(main=self.parent.main)
            # self.load()

        def fix_empty_titles(self):
            retval = display_messagebox(
                icon=QMessageBox.Warning,
                text="Are you sure you want to fix empty titles? This could be very expensive and may take a while. The application will be unresponsive until it is finished.",
                title="Fix titles",
                buttons=QMessageBox.Yes | QMessageBox.No,
            )

            if retval != QMessageBox.Yes:
                return

            # get all contexts with empty titles
            contexts_first_msgs = sql.get_results("""
                SELECT c.id, cm.msg
                FROM contexts c
                INNER JOIN (
                    SELECT *
                    FROM contexts_messages
                    WHERE rowid IN (
                        SELECT MIN(rowid)
                        FROM contexts_messages
                        GROUP BY context_id
                    )
                ) cm ON c.id = cm.context_id
                WHERE c.summary = '';
            """, return_type='dict')

            conf = self.parent.main.system.config.dict
            model_name = conf.get('system.auto_title_model', 'gpt-3.5-turbo')
            model_obj = (model_name, self.parent.main.system.models.get_llm_parameters(model_name))

            prompt = conf.get('system.auto_title_prompt',
                              'Generate a brief and concise title for a chat that begins with the following message:\n\n{user_msg}')
            try:
                for context_id, msg in contexts_first_msgs.items():
                    context_prompt = prompt.format(user_msg=msg)

                    title = llm.get_scalar(context_prompt, model_obj=model_obj)
                    title = title.replace('\n', ' ').strip("'").strip('"')
                    sql.execute('UPDATE contexts SET summary = ? WHERE id = ?', (title, context_id))

            except Exception as e:
                display_messagebox(
                    icon=QMessageBox.Warning,
                    text="Error generating titles: " + str(e),
                    title="Error",
                    buttons=QMessageBox.Ok,
                )

    class Page_Display_Settings(ConfigJoined):
        def __init__(self, parent):
            super().__init__(parent=parent)

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
                'display': {
                    'primary_color': get_widget_value(display_page.primary_color),
                    'secondary_color': get_widget_value(display_page.secondary_color),
                    'text_color': get_widget_value(display_page.text_color),
                },
                'user': {
                    'bubble_bg_color': roles_config['user']['bubble_bg_color'],
                    'bubble_text_color': roles_config['user']['bubble_text_color'],
                },
                'assistant': {
                    'bubble_bg_color': roles_config['assistant']['bubble_bg_color'],
                    'bubble_text_color': roles_config['assistant']['bubble_text_color'],
                },
                'code': {
                    'bubble_bg_color': roles_config['code']['bubble_bg_color'],
                    'bubble_text_color': roles_config['code']['bubble_text_color'],
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
                sql.execute("""
                    UPDATE `settings` SET `value` = json_set(value, '$."display.primary_color"', ?) WHERE `field` = 'app_config'
                """, (self.all_themes[theme_name]['display']['primary_color'],))
                sql.execute("""
                    UPDATE `settings` SET `value` = json_set(value, '$."display.secondary_color"', ?) WHERE `field` = 'app_config'
                """, (self.all_themes[theme_name]['display']['secondary_color'],))
                sql.execute("""
                    UPDATE `settings` SET `value` = json_set(value, '$."display.text_color"', ?) WHERE `field` = 'app_config'
                """, (self.all_themes[theme_name]['display']['text_color'],))
                sql.execute("""
                    UPDATE `roles` SET `config` = json_set(config, '$."bubble_bg_color"', ?) WHERE `name` = 'user'
                """, (self.all_themes[theme_name]['user']['bubble_bg_color'],))
                sql.execute("""
                    UPDATE `roles` SET `config` = json_set(config, '$."bubble_text_color"', ?) WHERE `name` = 'user'
                """, (self.all_themes[theme_name]['user']['bubble_text_color'],))
                sql.execute("""
                    UPDATE `roles` SET `config` = json_set(config, '$."bubble_bg_color"', ?) WHERE `name` = 'assistant'
                """, (self.all_themes[theme_name]['assistant']['bubble_bg_color'],))
                sql.execute("""
                    UPDATE `roles` SET `config` = json_set(config, '$."bubble_text_color"', ?) WHERE `name` = 'assistant'
                """, (self.all_themes[theme_name]['assistant']['bubble_text_color'],))
                sql.execute("""
                    UPDATE `roles` SET `config` = json_set(config, '$."bubble_bg_color"', ?) WHERE `name` = 'code'
                """, (self.all_themes[theme_name]['code']['bubble_bg_color'],))
                sql.execute("""
                    UPDATE `roles` SET `config` = json_set(config, '$."bubble_text_color"', ?) WHERE `name` = 'code'
                """, (self.all_themes[theme_name]['code']['bubble_text_color'],))
                system = self.parent.parent.main.system
                system.config.load()
                system.roles.load()
                self.parent.parent.main.apply_stylesheet()

                page_settings = self.parent.parent
                page_settings.load_config(system.config.dict)
                page_settings.load()

        class Page_Display_Fields(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.parent = parent

                self.label_width = 185
                self.margin_left = 20
                self.namespace = 'display'
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
                ]

            def load(self):
                super().load()
                # load theme
                self.parent.widgets[0].load()

            def update_config(self):
                super().update_config()
                main = self.parent.parent.main
                main.system.config.load()
                main.apply_stylesheet()
                main.page_chat.refresh_waiting_bar()
                self.load()  # reload theme combobox for custom

    class Page_Default_Settings(ConfigTabs):
        def __init__(self, parent):
            super().__init__(parent=parent)

            self.pages = {
                'Agent': self.Tab_Agent_Defaults(parent=self),
                # 'Config': self.Tab_Chat_Config(parent=self),
            }

        class Tab_Agent_Defaults(QWidget):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.parent = parent
                self.layout = CVBoxLayout(self)

                self.agent_defaults = self.Agent_Defaults(parent=self)
                self.layout.addWidget(self.agent_defaults)
                self.agent_defaults.build_schema()

            class Agent_Defaults(WorkflowSettings):
                def __init__(self, parent):
                    super().__init__(parent=parent,
                                     compact_mode=True)
                    self.parent = parent

                def save_config(self):
                    """Saves the config to database when modified"""
                    raise NotImplementedError()
                    # if self.ref_id is None:
                    #     return
                    json_config_dict = self.get_config()
                    json_config = json.dumps(json_config_dict)

                    # entity_id = self.parent.tree_config.get_selected_item_id()
                    # if not entity_id:
                    #     raise NotImplementedError()

                    # name = json_config_dict.get('info.name', 'Assistant')  todo
                    try:
                        sql.execute("UPDATE entities SET config = ? WHERE id = ?", (json_config, entity_id))
                    except sqlite3.IntegrityError as e:
                        # display_messagebox(
                        #     icon=QMessageBox.Warning,
                        #     title='Error',
                        #     text='Name already exists',
                        # )  todo
                        return

                    self.load_config(json_config)  # todo needed for configjsontree, but why
                    self.load()

    class Page_Models_Settings(ConfigDBTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                db_table='apis',
                propagate=False,
                query="""
                    SELECT
                        name,
                        id,
                        client_key,
                        api_key
                    FROM apis
                    ORDER BY name""",
                schema=[
                    {
                        'text': 'Name',
                        'key': 'name',
                        'type': str,
                        'width': 120,
                    },
                    {
                        'text': 'id',
                        'key': 'id',
                        'type': int,
                        'visible': False,
                    },
                    {
                        'text': 'Client Key',
                        'key': 'client_key',
                        'type': str,
                        'width': 100,
                    },
                    {
                        'text': 'API Key',
                        'type': str,
                        'encrypt': True,
                        'stretch': True,
                    },
                ],
                add_item_prompt=('Add API', 'Enter a name for the API:'),
                del_item_prompt=('Delete API', 'Are you sure you want to delete this API?'),
                readonly=False,
                layout_type=QVBoxLayout,
                config_widget=self.Models_Tab_Widget(parent=self),
                tree_width=500,
            )
            # self.config_widget = self.API_Tab_Widget(parent=self)
            # self.layout.addWidget(self.config_widget)

        # def on_item_selected(self):
        #     super().on_item_selected()
        #     api_name = self.get_column_value(0)
        #     fine_tunable_apis = ['openai', 'anyscale']
        #     self.config_widget.tree_buttons.btn_finetune.setVisible(api_name in fine_tunable_apis)

        def on_edited(self):
            main = self.parent.main
            main.system.models.load()
            for model_combobox in main.findChildren(ModelComboBox):
                model_combobox.load()

        class Models_Tab_Widget(ConfigTabs):
            def __init__(self, parent):
                super().__init__(parent=parent)

                self.pages = {
                    'Chat': self.Tab_Chat(parent=self),  # , visibility_param='pages.show_chat'),
                    'Voice': self.Tab_Voice(parent=self),  # , visibility_param='pages.show_voice'),
                    'Speech': self.Tab_Voice(parent=self),  # , visibility_param='pages.show_speech'),
                    'Image': self.Tab_Voice(parent=self),  # , visibility_param='pages.show_image'),
                    'Embedding': self.Tab_Voice(parent=self),  # , visibility_param='pages.show_embedding'),
                    # '..': self.Tab_Options(parent=self),
                }

            # def load(self):
            #     super().load()
            #
            #     show_chat = self.config.get('pages.show_chat', True)
            #     show_voice = self.config.get('pages.show_voice', True)
            #     show_speech = self.config.get('pages.show_speech', True)
            #     show_image = self.config.get('pages.show_image', True)
            #     show_embedding = self.config.get('pages.show_embedding', True)
            #
            #     self.content.tabBar().setTabVisible(0, show_chat)
            #     self.content.tabBar().setTabVisible(1, show_voice)
            #     self.content.tabBar().setTabVisible(2, show_speech)
            #     self.content.tabBar().setTabVisible(3, show_image)
            #     self.content.tabBar().setTabVisible(4, show_embedding)
            #
            #     self.content.update()
            #     self.update()  # Force a repaint
            #     self.content.tabBar().repaint()
            #     self.content.repaint()
            #     QApplication.processEvents()
            #     # # update to show the tab visibility
            #     # self.content.tabBar().update()

            # class Tab_Options(ConfigFields):
            #     def __init__(self, parent):
            #         super().__init__(parent=parent)
            #         self.parent = parent
            #
            #         self.label_width = 185
            #         self.margin_left = 20
            #         self.namespace = 'pages'
            #         self.schema = [
            #             {
            #                 'text': 'Show chat',
            #                 'type': bool,
            #                 'default': True,
            #             },
            #             {
            #                 'text': 'Show voice',
            #                 'type': bool,
            #                 'default': True,
            #             },
            #             {
            #                 'text': 'Show speech',
            #                 'type': bool,
            #                 'default': True,
            #             },
            #             {
            #                 'text': 'Show image',
            #                 'type': bool,
            #                 'default': True,
            #             },
            #             {
            #                 'text': 'Show embedding',
            #                 'type': bool,
            #                 'default': True,
            #             },
            #         ]
            #
            #     def update_config(self):
            #         super().update_config()
            #         conf = self.get_config()
            #         self.load_config(conf)
            #         # self.parent.load()

            class Tab_Chat(ConfigTabs):
                def __init__(self, parent, visibility_param=None):
                    super().__init__(parent=parent)
                    self.visibility_param = visibility_param
                    self.pages = {
                        'Models': self.Tab_Chat_Models(parent=self),
                        'Config': self.Tab_Chat_Config(parent=self),
                    }

                class Tab_Chat_Models(ConfigDBTree):
                    def __init__(self, parent):
                        super().__init__(
                            parent=parent,
                            db_table='models',
                            kind='CHAT',
                            query="""
                                SELECT
                                    name,
                                    id
                                FROM models
                                WHERE api_id = ?
                                    AND kind = ?
                                ORDER BY name""",
                            query_params=(
                                lambda: parent.parent.parent.get_selected_item_id(),
                                lambda: self.kind,
                            ),
                            schema=[
                                {
                                    'text': 'Name',
                                    'key': 'name',
                                    'type': str,
                                    'width': 150,
                                },
                                {
                                    'text': 'id',
                                    'key': 'id',
                                    'type': int,
                                    'visible': False,
                                },
                            ],
                            add_item_prompt=('Add Model', 'Enter a name for the model:'),
                            del_item_prompt=('Delete Model', 'Are you sure you want to delete this model?'),
                            layout_type=QHBoxLayout,
                            readonly=False,
                            config_widget=self.Chat_Config_Tabs(parent=self),
                            tree_header_hidden=True,
                            tree_width=150,
                        )
                        # add finetune button
                        self.btn_finetune = IconButton(
                            parent=self,
                            icon_path=':/resources/icon-finetune.png',
                            tooltip='Finetune model',
                            size=18,
                        )
                        setattr(self.tree_buttons, 'btn_finetune', self.btn_finetune)
                        self.tree_buttons.layout.takeAt(self.tree_buttons.layout.count() - 1)  # remove last stretch
                        self.tree_buttons.layout.addWidget(self.btn_finetune)
                        self.tree_buttons.layout.addStretch(1)

                        # switches to finetune tab of model config in one line
                        self.btn_finetune.clicked.connect(lambda: self.config_widget.content.setCurrentIndex(1))

                        self.fine_tunable_api_models = {
                            'anyscale': [
                                ''
                            ],
                            'openai': [
                                'gpt-3.5-turbo'
                            ]
                        }

                    def on_edited(self):
                        # # bubble upwards towards root until we find `reload_models` method
                        parent = self.parent
                        while parent:
                            if hasattr(parent, 'on_edited'):
                                parent.on_edited()
                                return
                            parent = getattr(parent, 'parent', None)

                    def on_item_selected(self):
                        super().on_item_selected()
                        self.tree_buttons.btn_finetune.setVisible(self.can_finetune())
                        self.config_widget.content.setCurrentIndex(0)

                    def can_finetune(self):
                        api_name = self.parent.parent.parent.get_column_value(0).lower()
                        model_config = self.config_widget.get_config()
                        model_name = model_config.get('model_name', '')  # self.get_column_value(0)
                        return model_name in self.fine_tunable_api_models.get(api_name, [])

                    class Chat_Config_Tabs(ConfigTabs):
                        def __init__(self, parent):
                            super().__init__(parent=parent, hide_tab_bar=True)

                            self.pages = {
                                'Parameters': self.Chat_Config_Parameters_Widget(parent=self),
                                'Finetune': self.Chat_Config_Finetune_Widget(parent=self),
                            }

                        class Chat_Config_Parameters_Widget(ConfigFields):
                            def __init__(self, parent):
                                super().__init__(parent=parent)
                                self.parent = parent
                                self.schema = [
                                    {
                                        'text': 'Model name',
                                        'type': str,
                                        'label_width': 125,
                                        'width': 265,
                                        # 'label_position': 'top',
                                        'tooltip': 'The name of the model to send to the API',
                                        'default': '',
                                    },
                                    {
                                        'text': 'Temperature',
                                        'type': float,
                                        'has_toggle': True,
                                        'label_width': 125,
                                        'minimum': 0.0,
                                        'maximum': 1.0,
                                        'step': 0.05,
                                        'default': 0.6,
                                        'row_key': 'A',
                                    },
                                    {
                                        'text': 'Presence penalty',
                                        'type': float,
                                        'has_toggle': True,
                                        'label_width': 140,
                                        'minimum': -2.0,
                                        'maximum': 2.0,
                                        'step': 0.2,
                                        'default': 0.0,
                                        'row_key': 'A',
                                    },
                                    {
                                        'text': 'Top P',
                                        'type': float,
                                        'has_toggle': True,
                                        'label_width': 125,
                                        'minimum': 0.0,
                                        'maximum': 1.0,
                                        'step': 0.05,
                                        'default': 1.0,
                                        'row_key': 'B',
                                    },
                                    {
                                        'text': 'Frequency penalty',
                                        'type': float,
                                        'has_toggle': True,
                                        'label_width': 140,
                                        'minimum': -2.0,
                                        'maximum': 2.0,
                                        'step': 0.2,
                                        'default': 0.0,
                                        'row_key': 'B',
                                    },
                                    {
                                        'text': 'Max tokens',
                                        'type': int,
                                        'has_toggle': True,
                                        'label_width': 125,
                                        'minimum': 1,
                                        'maximum': 999999,
                                        'step': 1,
                                        'default': 100,
                                    },
                                ]

                        class Chat_Config_Finetune_Widget(ConfigWidget):
                            def __init__(self, parent):
                                super().__init__(parent=parent)
                                self.parent = parent
                                self.propagate = False

                                self.layout = QVBoxLayout(self)
                                self.btn_cancel_finetune = QPushButton('Cancel')
                                self.btn_cancel_finetune.setFixedWidth(150)
                                self.btn_proceed_finetune = QPushButton('Finetune')
                                self.btn_proceed_finetune.setFixedWidth(150)
                                h_layout = QHBoxLayout()
                                h_layout.addWidget(self.btn_cancel_finetune)
                                h_layout.addStretch(1)
                                h_layout.addWidget(self.btn_proceed_finetune)

                                self.layout.addStretch(1)
                                self.layout.addLayout(h_layout)
                                self.btn_cancel_finetune.clicked.connect(self.cancel_finetune)

                            def cancel_finetune(self):
                                # switch to parameters tab
                                self.parent.content.setCurrentIndex(0)

                class Tab_Chat_Config(ConfigFields):
                    def __init__(self, parent):
                        super().__init__(parent=parent)
                        self.label_width = 125
                        self.schema = [
                            {
                                'text': 'Api Base',
                                'type': str,
                                'label_width': 150,
                                'width': 265,
                                'has_toggle': True,
                                # 'label_position': 'top',
                                'tooltip': 'The base URL for the API. This will be used for all models under this API',
                                'default': '',
                            },
                            {
                                'text': 'Litellm prefix',
                                'type': str,
                                'label_width': 150,
                                'width': 118,
                                'has_toggle': True,
                                # 'label_position': 'top',
                                'tooltip': 'The API provider prefix to be prepended to all model names under this API',
                                'row_key': 'F',
                                'default': '',
                            },
                            {
                                'text': 'Custom provider',
                                'type': str,
                                'label_width': 140,
                                'width': 118,
                                'has_toggle': True,
                                # 'label_position': 'top',
                                'tooltip': 'The custom provider for LiteLLM. Usually not needed.',
                                'row_key': 'F',
                                'default': '',
                            },
                            # {
                            #     'text': 'Environ var',
                            #     'type': str,
                            #     'width': 150,
                            #     'row_key': 0,
                            #     'default': '',
                            # },
                            # {
                            #     'text': 'Get key',
                            #     'key': 'get_environ_key',
                            #     'type': bool,
                            #     'label_width': 60,
                            #     'width': 30,
                            #     'row_key': 0,
                            #     'default': True,
                            # },
                            # {
                            #     'text': 'Set key',
                            #     'key': 'set_environ_key',
                            #     'type': bool,
                            #     'label_width': 60,
                            #     'width': 30,
                            #     'row_key': 0,
                            #     'default': True,
                            # },
                            {
                                'text': 'Temperature',
                                'type': float,
                                'label_width': 150,
                                'has_toggle': True,
                                'minimum': 0.0,
                                'maximum': 1.0,
                                'step': 0.05,
                                'tooltip': 'When enabled, this will override the temperature for all models under this API',
                                'row_key': 'A',
                                'default': 0.6,
                            },
                            {
                                'text': 'Presence penalty',
                                'type': float,
                                'has_toggle': True,
                                'label_width': 140,
                                'minimum': -2.0,
                                'maximum': 2.0,
                                'step': 0.2,
                                'row_key': 'A',
                                'default': 0.0,
                            },
                            {
                                'text': 'Top P',
                                'type': float,
                                'label_width': 150,
                                'has_toggle': True,
                                'minimum': 0.0,
                                'maximum': 1.0,
                                'step': 0.05,
                                'tooltip': 'When enabled, this will override the top P for all models under this API',
                                'row_key': 'B',
                                'default': 1.0,
                            },
                            {
                                'text': 'Frequency penalty',
                                'type': float,
                                'has_toggle': True,
                                'label_width': 140,
                                'minimum': -2.0,
                                'maximum': 2.0,
                                'step': 0.2,
                                'row_key': 'B',
                                'default': 0.0,
                            },
                            {
                                'text': 'Max tokens',
                                'type': int,
                                'has_toggle': True,
                                'label_width': 150,
                                'minimum': 1,
                                'maximum': 999999,
                                'step': 1,
                                'tooltip': 'When enabled, this will override the max tokens for all models under this API',
                                'default': 100,
                            },
                        ]

            class Tab_Voice(ConfigTabs):
                def __init__(self, parent, visibility_param=None):
                    super().__init__(parent=parent)
                    self.visibility_param = visibility_param

                    self.pages = {
                        'Voices': self.Tab_Voice_Models(parent=self),
                        # 'Config': self.Tab_TTS_Config(parent=self),
                    }

                class Tab_Voice_Models(ConfigDBTree):
                    def __init__(self, parent):
                        super().__init__(
                            parent=parent,
                            db_table='models',
                            kind='VOICE',
                            query="""
                                SELECT
                                    name,
                                    id
                                FROM models
                                WHERE api_id = ?
                                    AND kind = ?
                                ORDER BY name""",
                            query_params=(
                                lambda: parent.parent.parent.get_selected_item_id(),
                                lambda: self.kind,
                            ),
                            schema=[
                                {
                                    'text': 'Name',
                                    'key': 'name',
                                    'type': str,
                                    'width': 150,
                                },
                                {
                                    'text': 'id',
                                    'key': 'id',
                                    'type': int,
                                    'visible': False,
                                },
                            ],
                            add_item_prompt=('Add Model', 'Enter a name for the model:'),
                            del_item_prompt=('Delete Model', 'Are you sure you want to delete this model?'),
                            layout_type=QHBoxLayout,
                            readonly=False,
                            config_widget=self.Voice_Config_Widget(parent=self),
                            tree_header_hidden=True,
                            tree_width=150,
                        )

                    def on_edited(self):
                        # # bubble upwards towards root until we find `reload_models` method
                        parent = self.parent
                        while parent:
                            if hasattr(parent, 'on_edited'):
                                parent.on_edited()
                                return
                            parent = getattr(parent, 'parent', None)

                    class Voice_Config_Widget(ConfigJoined):
                        def __init__(self, parent):
                            super().__init__(parent=parent, layout_type=QVBoxLayout)
                            self.widgets = [
                                self.Voice_Config_Fields(parent=self),
                                # self.Voice_Config_Plugin(parent=self),
                            ]

                        class Voice_Config_Fields(ConfigFields):
                            def __init__(self, parent):
                                super().__init__(parent=parent)
                                self.parent = parent
                                self.schema = [
                                    {
                                        'text': 'Model name',
                                        'type': str,
                                        'label_width': 125,
                                        'width': 265,
                                        # 'label_position': 'top',
                                        'tooltip': 'The name of the model to send to the API',
                                        'default': '',
                                    },
                                ]

                        # class Voice_Config_Plugin(ConfigPlugin):
                        #     def __init__(self, parent):
                        #         super().__init__(
                        #             parent=parent,
                        #             plugin_type='Agent',
                        #             namespace='plugin',
                        #             plugin_json_key='info.use_plugin'
                        #         )

    class Page_Block_Settings(ConfigDBTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                db_table='blocks',
                # db_config_field='config',
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
                        # 'readonly': True,
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

        class Block_Config_Widget(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.schema = [
                    {
                        'text': 'Type',
                        'key': 'block_type',
                        'type': ('Text', 'Prompt', 'Code'),
                        'width': 90,
                        'default': 'Text',
                        'row_key': 0,
                    },
                    {
                        'text': 'Model',
                        'key': 'prompt_model',
                        'type': 'ModelComboBox',
                        'label_position': None,
                        'default': 'gpt-3.5-turbo',
                        'row_key': 0,
                    },
                    {
                        'text': 'Data',
                        'type': str,
                        'default': '',
                        'num_lines': 31,
                        'width': 385,
                        'label_position': None,
                        # 'label_position': 'top',
                    },
                ]

            def after_init(self):
                self.refresh_model_visibility()

            def load(self):
                super().load()
                self.refresh_model_visibility()

            def update_config(self):
                super().update_config()
                self.refresh_model_visibility()

            def refresh_model_visibility(self):
                block_type = get_widget_value(self.block_type)
                model_visible = block_type == 'Prompt'
                self.prompt_model.setVisible(model_visible)


    class Page_Role_Settings(ConfigDBTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                db_table='roles',
                # db_config_field='config',
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
                tree_width=150,
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
                    # db_config_field='config',
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
                )

            def add_item(self, column_vals=None, icon=None):
                with block_pin_mode():
                    file_dialog = QFileDialog()
                    # file_dialog.setProperty('class', 'uniqueFileDialog')
                    file_dialog.setFileMode(QFileDialog.ExistingFile)
                    file_dialog.setOption(QFileDialog.ShowDirsOnly, False)
                    file_dialog.setFileMode(QFileDialog.Directory)
                    # file_dialog.setStyleSheet("QFileDialog { color: black; }")
                    path, _ = file_dialog.getOpenFileName(None, "Choose Files", "", options=file_dialog.Options())

                if path:
                    self.add_path(path)

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
                    # folder_name = os.path.basename(base_directory) if base_directory else None
                    directories.append(os.path.basename(base_directory))
                    next_directory = os.path.dirname(base_directory)
                    base_directory = next_directory if next_directory != base_directory else None

                directories = reversed(directories)
                parent_id = None
                for directory in directories:
                    parent_id = super().add_folder(directory, parent_id)
                    # sql.execute(f"INSERT INTO `files` (`name`) VALUES (?)", (directory,))
                    # last_insert_id = sql.get_scalar("SELECT seq FROM sqlite_sequence WHERE name=?", (self.db_table,))
                    # self.load(select_id=last_insert_id)

                name = os.path.basename(path)
                config = json.dumps({'path': path, })
                sql.execute(f"INSERT INTO `files` (`name`, `folder_id`) VALUES (?, ?)", (name, parent_id,))
                last_insert_id = sql.get_scalar("SELECT seq FROM sqlite_sequence WHERE name=?", (self.db_table,))
                self.load(select_id=last_insert_id)
                return True
                # filename = os.path.basename(path)
                # is_dir = os.path.isdir(path)
                # row_dict = {'filename': filename, 'location': path, 'is_dir': is_dir}
                #
                # icon_provider = QFileIconProvider()
                # icon = icon_provider.icon(QFileInfo(path))
                # if icon is None or isinstance(icon, QIcon) is False:
                #     icon = QIcon()
                #
                # self.add_item(row_dict, icon)

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
                    self.schema = [
                        # {
                        #     'text': 'Bubble bg color',
                        #     'type': 'ColorPickerWidget',
                        #     'default': '#3b3b3b',
                        # },
                        # {
                        #     'text': 'Bubble text color',
                        #     'type': 'ColorPickerWidget',
                        #     'default': '#c4c4c4',
                        # },
                        # {
                        #     'text': 'Bubble image size',
                        #     'type': int,
                        #     'minimum': 3,
                        #     'maximum': 100,
                        #     'default': 25,
                        # },
                        # # {
                        # #     'text': 'Append to',
                        # #     'type': 'RoleComboBox',
                        # #     'default': 'None'
                        # # },
                        # # {
                        # #     'text': 'Visibility type',
                        # #     'type': ('Global', 'Local',),
                        # #     'default': 'Global',
                        # # },
                        # # {
                        # #     'text': 'Bubble class',
                        # #     'type': str,
                        # #     'width': 350,
                        # #     'num_lines': 15,
                        # #     'label_position': 'top',
                        # #     'highlighter': PythonHighlighter,
                        # #     'default': '',
                        # # },
                    ]

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

    class Page_VecDB_Settings(ConfigTabs):
        def __init__(self, parent):
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
                config_widget=self.VecDB_Config_Widget(parent=self),
                tree_width=150,
            )

        class VecDB_Config_Widget(ConfigJoined):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.widgets = []

    class Page_Sandbox_Settings(ConfigDBTree):
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
                add_item_prompt=('Add Sandbox', 'Enter a name for the sandbox:'),
                del_item_prompt=('Delete Sandbox', 'Are you sure you want to delete this sandbox?'),
                readonly=False,
                layout_type=QHBoxLayout,
                folder_key='sandboxes',
                config_widget=self.Sandbox_Config_Widget(parent=self),
                tree_width=150,
            )

        def on_edited(self):
            self.parent.main.system.sandboxes.load()
            # self.load()

        class Sandbox_Config_Widget(ConfigJoined):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.widgets = [
                    # self.Sandbox_Config_Fields(parent=self)
                ]

        #     class Sandbox_Config_Fields(ConfigPlugin):
        #         def __init__(self, parent):
        #             super().__init__(parent=parent, plugin_type='SandboxSettings')
        # # class Sandbox_Config_Widget(ConfigJoined):
        # #     def __init__(self, parent):
        # #         super().__init__(parent=parent)
        # #         self.widgets = [
        # #             self.Sandbox_Config_Tabs(parent=self)
        # #         ]

            # class Sandbox_Config_Tabs(ConfigTabs):
            #     def __init__(self, parent):
            #         super().__init__(parent=parent)
            #         self.pages = {
            #             'Files': self.Sandbox_Config_Tab_Files(parent=self),
            #         }
            #
            #     class Sandbox_Config_Tab_Files(ConfigTabs):
            #         def __init__(self, parent):
            #             super().__init__(parent=parent)
            #             self.pages = {
            #                 # 'Config': self.Tab_Config(parent=self),
            #                 # 'Files': self.Tab_Files(parent=self),
            #             }

    class Page_Plugin_Settings(ConfigTabs):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.namespace = 'plugins'

            self.pages = {
                # 'GPT Pilot': self.Page_Test(parent=self),
                'CrewAI': Page_Settings_CrewAI(parent=self),
                'OAI': Page_Settings_OAI(parent=self),
                'Matrix': Page_Settings_Matrix(parent=self),
                'Test Pypi': self.Page_Pypi_Packages(parent=self),
            }

        # def get_config(self):
        #     config = {
        #         'plugins.crewai': self.pages['CrewAI'].get_config(),
        #         'plugins.openai': self.pages['OAI'].get_config(),
        #     }
        #     return config

        # def save

            # self.parent = parent
            # self.layout = CVBoxLayout(self)
            #
            # # self.plugin_tree = self.Plugin_Tree(parent=self)
            # # self.layout.addWidget(self.plugin_tree)
            # #
            # # self.plugin_config = self.Plugin_Config(parent=self)
            # # self.layout.addWidget(self.plugin_config)

        # def load(self):
        #     pass

        class Page_Pypi_Packages(ConfigDBTree):
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
                            'text': 'Name',
                            'type': str,
                            'width': 150,
                        },
                    ],
                    layout_type=QHBoxLayout,
                    folder_key='pypi_packages',
                    searchable=True,
                )
                self.tree_buttons.btn_sync = IconButton(
                    parent=self.tree_buttons,
                    icon_path=':/resources/icon-refresh.png',
                    tooltip='Update package list',
                    size=18,
                )
                # remove the last stretch
                self.tree_buttons.layout.takeAt(self.tree_buttons.layout.count() - 1)
                self.tree_buttons.layout.addWidget(self.tree_buttons.btn_sync)
                self.tree_buttons.layout.addStretch(1)

            def on_item_selected(self):
                pass

            def sync_pypi_packages(self):
                import requests
                # from bs4 import BeautifulSoup
                # import html
                from lxml import etree

                url = 'https://pypi.org/simple/'
                response = requests.get(url, stream=True)

                items = []
                batch_size = 10000

                parser = etree.HTMLParser()
                previous_overlap = ''
                for chunk in response.iter_content(chunk_size=10240):
                    if chunk:
                        chunk_str = chunk.decode('utf-8')
                        chunk = previous_overlap + chunk_str
                        previous_overlap = chunk_str[-100:]

                        tree = etree.fromstring(chunk, parser)
                        for element in tree.xpath('//a'):
                            if element is None:
                                continue
                            if element.text is None:
                                continue

                            item_name = element.text.strip()
                            items.append(item_name)

                    if len(items) >= batch_size:
                        # generate the query directly without using params
                        query = 'INSERT OR IGNORE INTO pypi_packages (name) VALUES ' + ', '.join([f"('{item}')" for item in items])
                        sql.execute(query)
                        items = []

                # Insert any remaining items
                if items:
                    query = 'INSERT OR IGNORE INTO pypi_packages (name) VALUES ' + ', '.join([f"('{item}')" for item in items])
                    sql.execute(query)

                print('Scraping and storing items completed.')

    class Page_Tool_Settings(ConfigDBTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                db_table='tools',
                propagate=False,
                query="""
                    SELECT
                        name,
                        id,
                        folder_id
                    FROM tools""",
                schema=[
                    {
                        'text': 'Name',
                        'key': 'name',
                        'type': str,
                        'width': 250,
                    },
                    {
                        'text': 'id',
                        'key': 'id',
                        'type': int,
                        'visible': False,
                    },
                ],
                add_item_prompt=('Add Tool', 'Enter a name for the tool:'),
                del_item_prompt=('Delete Tool', 'Are you sure you want to delete this tool?'),
                readonly=False,
                layout_type=QVBoxLayout,
                folder_key='tools',
                config_widget=self.Tool_Config_Widget(parent=self),
                tree_width=250,  # 500,
            )

        class Tool_Config_Widget(ConfigJoined):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.widgets = [
                    self.Tool_Info_Widget(parent=self),
                    self.Tool_Tab_Widget(parent=self),
                ]

            class Tool_Info_Widget(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.schema = [
                        {
                            'text': 'Description',
                            'type': str,
                            'num_lines': 2,
                            'width': 350,
                            'tooltip': 'A description of the tool, this is required and used by the LLM',
                            'default': '',
                        },
                        {
                            'text': 'Method',
                            'type': ('Function call', 'Prompt based',),
                            'tooltip': 'The method to use for the tool decision. `Function call` will use a function calling LLM. `Prompt based` is cheaper and will use any LLM to decide to use tools.',
                            'default': 'Native',
                        },
                    ]

            class Tool_Tab_Widget(ConfigTabs):
                def __init__(self, parent):
                    super().__init__(parent=parent)

                    self.pages = {
                        'Code': self.Tab_Code(parent=self),
                        'Parameters': self.Tab_Parameters(parent=self),
                        # 'Prompt': self.Tab_Prompt(parent=self),
                    }

                class Tab_Code(ConfigFields):
                    def __init__(self, parent):
                        super().__init__(parent=parent)
                        self.namespace = 'code'
                        self.schema = [
                            {
                                'text': 'Type',
                                'type': ('Native', 'Imported',),
                                'width': 100,
                                'tooltip': 'The type of code to execute. `Native` executes the code within a predefined function. `Script` will execute the code in a python script (Not implented yet). `Imported` will use an externally imported tool.',
                                'row_key': 'A',
                                'default': 'Native',
                            },
                            {
                                'text': 'Delay seconds',
                                'type': int,
                                'minimum': 1,
                                'maximum': 30,
                                'step': 1,
                                'tooltip': 'The delay in seconds before the tool is executed',
                                'has_toggle': True,
                                'row_key': 'A',
                                'default': 5,
                            },
                            {
                                'text': 'Code',
                                'key': 'data',
                                'type': str,
                                'width': 350,
                                'num_lines': 15,
                                'label_position': None,
                                'highlighter': PythonHighlighter,
                                'encrypt': True,
                                'default': '',
                            },
                        ]

                class Tab_Parameters(ConfigJsonTree):
                    def __init__(self, parent):
                        super().__init__(parent=parent,
                                         add_item_prompt=('NA', 'NA'),
                                         del_item_prompt=('NA', 'NA'))
                        self.parent = parent
                        self.namespace = 'parameters'
                        self.schema = [
                            {
                                'text': 'Name',
                                'type': str,
                                'width': 120,
                                'default': '< Enter a parameter name >',
                            },
                            {
                                'text': 'Description',
                                'type': str,
                                'stretch': True,
                                'default': '< Enter a parameter name >',
                            },
                            {
                                'text': 'Type',
                                'type': ('String', 'Integer', 'Float', 'Bool', 'List',),
                                'width': 100,
                                'default': 'String',
                            },
                            {
                                'text': 'Req',
                                'type': bool,
                                'default': True,
                            },
                            {
                                'text': 'Default',
                                'type': str,
                                'default': '',
                            },
                        ]

                    # class Tab_Parameters_Info(ConfigFields):
                    #     def __init__(self, parent):
                    #         super().__init__(parent=parent)
                    #         self.schema = [
                    #             {
                    #                 'text': 'Description',
                    #                 'type': str,
                    #                 'num_lines': 2,
                    #                 'width': 350,
                    #                 'default': '',
                    #             },
                    #         ]