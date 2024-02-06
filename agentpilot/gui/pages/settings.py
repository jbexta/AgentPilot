
import json
import logging

from PySide6.QtWidgets import *
from PySide6.QtGui import Qt, QDoubleValidator

from agentpilot.gui.components.config import ConfigPages, ConfigFieldsWidget, ConfigTreeWidget, ConfigTabs
from agentpilot.utils import sql, api, config
from agentpilot.utils.apis import llm
from agentpilot.gui.widgets.base import BaseComboBox, BaseTableWidget, IconButton, ContentPage
from agentpilot.utils.helpers import block_signals, display_messagebox, block_pin_mode


class Page_Settings(ConfigPages):
    def __init__(self, main):
        super().__init__(parent=main)
        self.main = main

        ContentPageTitle = ContentPage(main=main, title='Settings')
        self.layout.addWidget(ContentPageTitle)

        self.pages = {
            'System': self.Page_System_Settings(self),
            'API': self.Page_API_Settings(self),
            'Display': self.Page_Display_Settings(self),
            'Blocks': self.Page_Block_Settings(self),
            'Roles': self.Page_Role_Settings(self),
            'Tools': self.Page_Tool_Settings(self),
            'Sandbox': self.Page_Sandboxes_Settings(self),
            "Vector DB": self.Page_Sandboxes_Settings(self)

        }
        self.build_schema()
        self.settings_sidebar.layout.addStretch(1)

    def save_config(self):
        """
        Overrides ConfigPages.save_config() to save the config to config.yaml instead of the database.
        This is temporary until the next breaking version, where the config will be moved to the database.
        """
        pass

    class Page_System_Settings(ConfigFieldsWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.label_width = 125
            self.schema = [
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
                    'text': 'Auto-title model',
                    'type': 'ModelComboBox',
                    'default': 'gpt-3.5-turbo',
                },
                {
                    'text': 'Auto-title prompt',
                    'type': str,
                    'default': 'Generate a brief and concise title for a chat that begins with the following message:\n\n{user_msg}',
                    'num_lines': 4,
                    'width': 300,
                },
            ]

        def after_init(self):
            self.dev_mode.stateChanged.connect(lambda state: self.toggle_dev_mode(state))

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
            main.page_chat.topbar.btn_info.setVisible(state)
            main.page_chat.topbar.group_settings.group_topbar.btn_clear.setVisible(state)
            main.page_settings.pages['System'].reset_app_btn.setVisible(state)
            main.page_settings.pages['System'].fix_empty_titles_btn.setVisible(state)

        def reset_application(self):
            from agentpilot.context.base import Workflow

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
            self.parent.update_config('system.dev_mode', False)
            self.toggle_dev_mode(False)
            self.parent.main.page_chat.workflow = Workflow(main=self.parent.main)
            self.load()

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

            model_name = config.get_value('system.auto_title_model', 'gpt-3.5-turbo')
            model_obj = (model_name, self.parent.main.system.models.to_dict()[model_name])  # todo make prettier

            prompt = config.get_value('system.auto_title_prompt',
                                      'Generate a brief and concise title for a chat that begins with the following message:\n\n{user_msg}')
            try:
                for context_id, msg in contexts_first_msgs.items():
                    context_prompt = prompt.format(user_msg=msg)

                    title = llm.get_scalar(context_prompt, model_obj=model_obj)
                    title = title.replace('\n', ' ').strip("'").strip('"')
                    sql.execute('UPDATE contexts SET summary = ? WHERE id = ?', (title, context_id))

            except Exception as e:
                # show error message
                display_messagebox(
                    icon=QMessageBox.Warning,
                    text="Error generating titles: " + str(e),
                    title="Error",
                    buttons=QMessageBox.Ok,
                )

    class Page_Display_Settings(ConfigFieldsWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent

            self.label_width = 185
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
                    'default': 'Arial',
                },
                {
                    'text': 'Text size',
                    'type': int,
                    'minimum': 6,
                    'maximum': 72,
                    'default': 12,
                },
                {
                    'text': 'Show agent bubble avatar',
                    'type': ('In Group', 'Always', 'Never',),
                    'default': 'In Group',
                },
                {
                    'text': 'Agent bubble avatar position',
                    'type': ('Top', 'Middle',),
                    'default': 'Top',
                },
            ]

    class Page_API_Settings(ConfigTreeWidget):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                db_table='apis',
                has_config_field=False,
                query="""
                    SELECT
                        id,
                        name,
                        client_key,
                        priv_key
                    FROM apis""",
                schema=[
                    {
                        'text': 'id',
                        'key': 'id',
                        'type': int,
                        'visible': False,
                    },
                    {
                        'text': 'Name',
                        'key': 'name',
                        'type': str,
                        'width': 120,
                    },
                    {
                        'text': 'Client Key',
                        'key': 'client_key',
                        'type': str,
                        'width': 100,
                    },
                    {
                        'text': 'API Key',
                        'key': 'priv_key',
                        'type': str,
                        'stretch': True,
                    },
                ],
                add_item_prompt=('Add API', 'Enter a name for the API:'),
                del_item_prompt=('Delete API', 'Are you sure you want to delete this API?'),
                readonly=False,
                layout_type=QVBoxLayout,
                config_widget=self.API_Tab_Widget(parent=self),
                tree_width=500,
            )

        def on_item_selected(self):
            item = self.tree.currentItem()
            if not item:
                return

            self.config_widget.load()

        class API_Tab_Widget(ConfigTabs):
            def __init__(self, parent):
                super().__init__(parent=parent)

                self.tabs = {
                    'Models': self.Tab_Models(parent=self),
                }

            class Tab_Models(ConfigTreeWidget):
                def __init__(self, parent):
                    # current_tree_id = parent.parent.tree.currentItem().data(0, Qt.UserRole)

                    # item = parent.parent.tree.currentItem()
                    # if not item:
                    #     return False
                    # id = int(item.text(0))

                    super().__init__(
                        parent=parent,
                        db_table='models',
                        db_config_field='model_config',
                        query="""
                            SELECT
                                id,
                                alias
                            FROM models
                            WHERE api_id = ?
                            ORDER BY alias""",  # (parent.parent.tree.currentItem(),),
                        query_params=(parent.parent,),
                        schema=[
                            {
                                'text': 'id',
                                'key': 'id',
                                'type': int,
                                'visible': False,
                            },
                            {
                                'text': 'Name',
                                'key': 'name',
                                'type': str,
                                'width': 150,
                            },
                        ],
                        add_item_prompt=('Add Model', 'Enter a placeholder tag for the model:'),
                        del_item_prompt=('Delete Model', 'Are you sure you want to delete this model?'),
                        layout_type=QHBoxLayout,
                        config_widget=self.Model_Config_Widget(parent=self),
                        tree_width=150,
                    )

                class Model_Config_Widget(ConfigFieldsWidget):
                    def __init__(self, parent):
                        super().__init__(parent=parent)
                        self.parent = parent
                        self.schema = [
                            {
                                'text': 'Alias',
                                'type': str,
                                'width': 300,
                                'label_position': 'top',
                                'default': '',
                            },
                            {
                                'text': 'Model name',
                                'type': str,
                                'width': 300,
                                'label_position': 'top',
                                'default': '',
                            },
                            {
                                'text': 'Api Base',
                                'type': str,
                                'width': 300,
                                'label_position': 'top',
                                'default': '',
                            },
                            {
                                'text': 'Custom provider',
                                'type': str,
                                'label_position': 'top',
                                'default': '',
                            },
                            {
                                'text': 'Temperature',
                                'type': float,
                                'label_position': 'top',
                                'default': 0.5,
                            },
                        ]

                    # def load(self):
                    #     pass

    class Page_API_Settingszzz(ConfigFieldsWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent

            self.table_layout = QHBoxLayout()
            self.table_layout.setContentsMargins(0, 0, 0, 0)
            self.table_layout.setSpacing(0)

            self.table_container = QWidget(self)
            self.table_container.setLayout(self.table_layout)

            # API settings part
            self.table = BaseTableWidget(self)
            self.table.setColumnCount(4)
            self.table.setColumnHidden(0, True)
            self.table.setHorizontalHeaderLabels(['ID', 'Name', 'Client Key', 'API Key'])
            self.table.horizontalHeader().setStretchLastSection(True)
            self.table.itemChanged.connect(self.item_edited)
            self.table.currentItemChanged.connect(self.load_models)

            self.table_layout.addWidget(self.table)

            self.button_layout = QVBoxLayout()
            self.button_layout.addStretch(1)
            self.new_api_button = self.Button_New_API(self)
            self.button_layout.addWidget(self.new_api_button)
            self.del_api_button = self.Button_Delete_API(self)
            self.button_layout.addWidget(self.del_api_button)

            self.table_layout.addLayout(self.button_layout)

            self.layout.addWidget(self.table_container)

            # Tab Widget
            self.tab_widget = QTabWidget(self)

            # Models Tab
            self.models_tab = QWidget(self.tab_widget)
            self.models_layout = QHBoxLayout(self.models_tab)

            # Create a container for the model list and a button bar above
            self.models_container = QWidget(self.models_tab)
            self.models_container_layout = QVBoxLayout(self.models_container)
            self.models_container_layout.setContentsMargins(0, 0, 0, 0)
            self.models_container_layout.setSpacing(0)

            self.models_button_layout = QHBoxLayout()
            self.models_button_layout.addStretch(1)
            self.new_model_button = self.Button_New_Model(self)
            self.models_button_layout.addWidget(self.new_model_button)
            self.del_model_button = self.Button_Delete_Model(self)
            self.models_button_layout.addWidget(self.del_model_button)
            self.models_container_layout.addLayout(self.models_button_layout)

            self.models_list = QListWidget(self.models_container)
            self.models_list.setSelectionMode(QListWidget.SingleSelection)
            self.models_list.setFixedWidth(200)
            self.models_container_layout.addWidget(self.models_list)
            self.models_layout.addWidget(self.models_container)

            self.fields_layout = QVBoxLayout()

            # connect model list selection changed to load_model_fields
            self.models_list.currentItemChanged.connect(self.load_model_fields)

            self.alias_label = QLabel("Alias")
            self.alias_label.hide()
            self.alias_field = QLineEdit()
            self.alias_field.hide()
            alias_layout = QHBoxLayout()
            alias_layout.addWidget(self.alias_label)
            alias_layout.addWidget(self.alias_field)
            self.fields_layout.addLayout(alias_layout)

            self.model_name_label = QLabel("Model name")
            self.model_name_label.hide()
            self.model_name_field = QLineEdit()
            self.model_name_field.hide()
            model_name_layout = QHBoxLayout()
            model_name_layout.addWidget(self.model_name_label)
            model_name_layout.addWidget(self.model_name_field)
            self.fields_layout.addLayout(model_name_layout)

            self.api_base_label = QLabel("Api Base")
            self.api_base_label.hide()
            self.api_base_field = QLineEdit()
            self.api_base_field.hide()
            api_base_layout = QHBoxLayout()
            api_base_layout.addWidget(self.api_base_label)
            api_base_layout.addWidget(self.api_base_field)
            self.fields_layout.addLayout(api_base_layout)

            self.custom_provider_label = QLabel("Custom provider")
            self.custom_provider_label.hide()
            self.custom_provider_field = QLineEdit()
            self.custom_provider_field.hide()
            custom_provider_layout = QHBoxLayout()
            custom_provider_layout.addWidget(self.custom_provider_label)
            custom_provider_layout.addWidget(self.custom_provider_field)
            self.fields_layout.addLayout(custom_provider_layout)

            self.temperature_label = QLabel("Temperature")
            self.temperature_label.hide()
            self.temperature_field = QLineEdit()
            self.temperature_field.hide()
            # self.temperature_field.setValidator(QValidator(3, 100))
            # float validator
            self.temperature_field.setValidator(QDoubleValidator(0.0, 100.0, 2))
            temperature_layout = QHBoxLayout()
            temperature_layout.addWidget(self.temperature_label)
            temperature_layout.addWidget(self.temperature_field)
            self.fields_layout.addLayout(temperature_layout)

            self.models_layout.addLayout(self.fields_layout)

            # Voices Taboo
            self.voices_tab = QWidget(self.tab_widget)
            self.voices_layout = QVBoxLayout(self.voices_tab)
            # self.voices_label = QLabel("Voices:")
            self.voices_list = QListWidget(self.voices_tab)
            self.voices_list.setSelectionMode(QListWidget.SingleSelection)
            self.voices_list.setFixedWidth(200)
            # self.voices_layout.addWidget(self.voices_label)
            self.voices_layout.addWidget(self.voices_list)

            # Add tabs to the Tab Widget
            self.tab_widget.addTab(self.models_tab, "Models")
            self.tab_widget.addTab(self.voices_tab, "Voices")

            # Add Tab Widget to the main layout
            self.layout.addWidget(self.tab_widget)
            self.layout.addStretch(1)

            # connect signals for each field change

            self.alias_field.textChanged.connect(self.update_model_config)
            self.model_name_field.textChanged.connect(self.update_model_config)
            self.api_base_field.textChanged.connect(self.update_model_config)
            self.custom_provider_field.textChanged.connect(self.update_model_config)
            self.temperature_field.textChanged.connect(self.update_model_config)

        def load(self):
            self.load_api_table()
            self.load_models()

        def load_api_table(self):
            with block_signals(self):
                self.table.setRowCount(0)
                data = sql.get_results("""
                    SELECT
                        id,
                        name,
                        client_key,
                        priv_key
                    FROM apis""")
                for row_data in data:
                    row_position = self.table.rowCount()
                    self.table.insertRow(row_position)
                    for column, item in enumerate(row_data):
                        self.table.setItem(row_position, column, QTableWidgetItem(str(item)))

        def load_models(self):
            # Clear the current items in the list
            self.models_list.clear()

            # if none selected then return
            if self.table.currentRow() == -1:
                return

            # Get the currently selected API's ID
            current_api_id = self.table.item(self.table.currentRow(), 0).text()

            # Fetch the models from the database
            data = sql.get_results("""
                SELECT 
                    id, 
                    alias 
                FROM models 
                WHERE api_id = ?
                ORDER BY alias""", (current_api_id,))
            for row_data in data:
                model_id, model_name = row_data
                item = QListWidgetItem(model_name)
                item.setData(Qt.UserRole, model_id)
                self.models_list.addItem(item)

            show_fields = (self.models_list.count() > 0)  # and (self.models_list.currentItem() is not None)
            self.alias_label.setVisible(show_fields)
            self.alias_field.setVisible(show_fields)
            self.model_name_label.setVisible(show_fields)
            self.model_name_field.setVisible(show_fields)
            self.api_base_label.setVisible(show_fields)
            self.api_base_field.setVisible(show_fields)
            self.custom_provider_label.setVisible(show_fields)
            self.custom_provider_field.setVisible(show_fields)
            self.temperature_label.setVisible(show_fields)
            self.temperature_field.setVisible(show_fields)

            # Select the first model in the list by default
            if self.models_list.count() > 0:
                self.models_list.setCurrentRow(0)

        def load_model_fields(self):
            current_item = self.models_list.currentItem()
            if current_item is None:
                return
            current_selected_id = self.models_list.currentItem().data(Qt.UserRole)

            model_data = sql.get_results("""
                SELECT
                    alias,
                    model_name,
                    model_config
                FROM models
                WHERE id = ?""",
                 (current_selected_id,),
                 return_type='hdict')
            if len(model_data) == 0:
                return
            alias = model_data['alias']
            model_name = model_data['model_name']
            model_config = json.loads(model_data['model_config'])
            api_base = model_config.get('api_base', '')
            custom_provider = model_config.get('custom_llm_provider', '')
            temperature = model_config.get('temperature', '')

            with block_signals(self):
                self.alias_field.setText(alias)
                self.model_name_field.setText(model_name)
                self.api_base_field.setText(api_base)
                self.custom_provider_field.setText(custom_provider)
                self.temperature_field.setText(str(temperature))

        def get_model_config(self):
            # Retrieve the current values from the pages and construct a new 'config' dictionary
            # temp = int(self.temperature_field.text()) if self.temperature_field.text() != '' else None
            current_config = {
                'api_base': self.api_base_field.text(),
                'custom_llm_provider': self.custom_provider_field.text(),
                'temperature': self.temperature_field.text()
            }
            return json.dumps(current_config)

        def update_model_config(self):
            current_model = self.models_list.currentItem()
            if current_model is None:
                return

            current_model_id = current_model.data(Qt.UserRole)
            current_config = self.get_model_config()
            sql.execute("UPDATE models SET model_config = ? WHERE id = ?", (current_config, current_model_id))

            model_alias = self.alias_field.text()
            model_name = self.model_name_field.text()
            sql.execute("UPDATE models SET alias = ?, model_name = ? WHERE id = ?",
                        (model_alias, model_name, current_model_id))
            # self.load()

        class Button_New_API(IconButton):
            def __init__(self, parent):
                super().__init__(parent=parent, icon_path=':/resources/icon-new.png')
                self.clicked.connect(self.new_api)

            def new_api(self):
                pass

        class Button_Delete_API(IconButton):
            def __init__(self, parent):
                super().__init__(parent=parent, icon_path=':/resources/icon-minus.png')
                self.clicked.connect(self.delete_api)

            def delete_api(self):
                pass

        class Button_New_Model(IconButton):
            def __init__(self, parent):
                super().__init__(parent=parent, icon_path=':/resources/icon-new.png')
                self.clicked.connect(self.new_model)

            def new_model(self):
                with block_pin_mode():
                    text, ok = QInputDialog.getText(self, 'New Model', 'Enter a name for the model:')

                # Check if the OK button was clicked
                if ok and text:
                    current_api_id = self.parent.table.item(self.parent.table.currentRow(), 0).text()
                    sql.execute("INSERT INTO `models` (`alias`, `api_id`, `model_name`) VALUES (?, ?, '')",
                                (text, current_api_id,))
                    self.parent.load_models()
                    self.parent.parent.main.page_chat.load()

        class Button_Delete_Model(IconButton):
            def __init__(self, parent):
                super().__init__(parent=parent, icon_path=':/resources/icon-minus.png')
                self.clicked.connect(self.delete_model)

            def delete_model(self):
                current_item = self.parent.models_list.currentItem()
                if current_item is None:
                    return

                retval = display_messagebox(
                    icon=QMessageBox.Warning,
                    text="Are you sure you want to delete this model?",
                    title="Delete Model",
                    buttons=QMessageBox.Yes | QMessageBox.No,
                )

                if retval != QMessageBox.Yes:
                    return

                # Logic for deleting a model from the database
                current_model_id = current_item.data(Qt.UserRole)
                sql.execute("DELETE FROM `models` WHERE `id` = ?", (current_model_id,))
                self.parent.load_models()  # Reload the list of models
                self.parent.parent.main.page_chat.workflow.load()
                self.parent.parent.main.page_chat.refresh()

        def item_edited(self, item):
            row = item.row()
            api_id = self.table.item(row, 0).text()

            id_map = {
                2: 'client_key',
                3: 'priv_key'
            }

            column = item.column()
            if column not in id_map:
                return
            column_name = id_map.get(column)
            new_value = item.text()
            sql.execute(f"""
                UPDATE apis
                SET {column_name} = ?
                WHERE id = ?
            """, (new_value, api_id,))

            api.load_api_keys()

    class Page_Block_Settings(ConfigTreeWidget):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                db_table='blocks',
                db_config_field='config',
                query="""
                    SELECT
                        id,
                        name
                    FROM blocks""",
                schema=[
                    {
                        'text': 'id',
                        'key': 'id',
                        'type': int,
                        'visible': False,
                        # 'readonly': True,
                    },
                    {
                        'text': 'Name',
                        'key': 'name',
                        'type': str,
                        'stretch': True,
                    },
                ],
                add_item_prompt=('Add Block', 'Enter a placeholder tag for the block:'),
                del_item_prompt=('Delete Block', 'Are you sure you want to delete this block?'),
                readonly=False,
                layout_type=QHBoxLayout,
                config_widget=self.Block_Config_Widget(parent=self),
                tree_width=150,
            )
            # self.parent = parent

        def field_edited(self, item):
            super().field_edited(item)

            # reload blocks
            self.parent.main.system.blocks.load()

        def add_item(self):
            if not super().add_item():
                return
            self.load()
            self.parent.main.system.blocks.load()

        def delete_item(self):
            if not super().delete_item():
                return
            self.load()
            self.parent.main.system.blocks.load()

        class Block_Config_Widget(ConfigFieldsWidget):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.schema = [
                    {
                        'text': 'Data',
                        'type': str,
                        'default': '',
                        'num_lines': 20,
                        'width': 450,
                        'label_position': 'top',
                    },
                ]

    class Page_Role_Settings(ConfigTreeWidget):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                db_table='roles',
                db_config_field='config',
                query="""
                    SELECT
                        id,
                        name
                    FROM roles""",
                schema=[
                    {
                        'text': 'id',
                        'key': 'id',
                        'type': int,
                        'visible': False,
                        # 'readonly': True,
                    },
                    {
                        'text': 'Name',
                        'key': 'name',
                        'type': str,
                        'stretch': True,
                    },
                ],
                add_item_prompt=('Add Role', 'Enter a name for the role:'),
                del_item_prompt=('Delete Role', 'Are you sure you want to delete this role?'),
                readonly=False,
                layout_type=QHBoxLayout,
                config_widget=self.Role_Config_Widget(parent=self),
                tree_width=150,
            )
            # self.parent = parent

        def field_edited(self, item):
            super().field_edited(item)

            # reload blocks
            self.parent.main.system.roles.load()

        def add_item(self):
            if not super().add_item():
                return
            self.load()
            self.parent.main.system.roles.load()

        def delete_item(self):
            if not super().delete_item():
                return
            self.load()
            self.parent.main.system.roles.load()

        class Role_Config_Widget(ConfigFieldsWidget):
            def __init__(self, parent):
                super().__init__(parent=parent)
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
                ]

    class Page_Tool_Settings(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent

            self.layout = QVBoxLayout(self)

            # Function list and description
            self.function_layout = QVBoxLayout()
            self.functions_table = BaseTableWidget(self)
            self.functions_table.setColumnCount(4)
            self.functions_table.setHorizontalHeaderLabels(["ID", "Name", "Description", "On trigger"])
            # self.functions_table.horizontalHeader().setStretchLastSection(True)
            self.functions_table.setColumnWidth(3, 100)
            self.functions_table.setColumnHidden(0, True)
            self.functions_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
            self.functions_table.verticalHeader().setVisible(False)
            self.functions_table.verticalHeader().setDefaultSectionSize(20)
            self.functions_table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)

            self.function_layout.addWidget(self.functions_table)

            # Tab Widget
            self.tab_widget = QTabWidget(self)
            self.function_layout.addWidget(self.tab_widget)

            # Code Tab
            self.code_tab = self.Tab_Page_Code(self.tab_widget)

            # Parameter Tab
            self.parameters_tab = self.Tab_Page_Parameters(self.tab_widget)

            # Used By Tab
            self.used_by_tab = QWidget(self.tab_widget)
            self.used_by_layout = QHBoxLayout(self.used_by_tab)

            # Add tabs to the Tab Widget
            self.tab_widget.addTab(self.code_tab, "Code")
            self.tab_widget.addTab(self.parameters_tab, "Parameters")
            self.tab_widget.addTab(self.used_by_tab, "Used By")

            # # Create a container for the model list and a button bar above
            # self.parameters_container = QWidget(self.models_tab)
            # self.models_container_layout = QVBoxLayout(self.models_container)
            # self.models_container_layout.setContentsMargins(0, 0, 0, 0)
            # self.models_container_layout.setSpacing(0)

            # Parameters section
            # self.parameters_layout = QVBoxLayout(self.parameters_tab)  # Use QHBoxLayout for putting label and buttons in the same row
            # # self.parameters_label = QLabel("Parameters", self)
            # # self.parameters_label.setStyleSheet("QLabel { font-size: 15px; font-weight: bold; }")
            # # self.parameters_layout.addWidget(self.parameters_label)
            #
            # # Parameter buttons
            # self.new_parameter_button = IconButton(self, icon_path=':/resources/icon-new.png')
            # self.delete_parameter_button = IconButton(self, icon_path=':/resources/icon-minus.png')
            #
            # # # Add buttons to the parameters layout
            # # self.parameters_buttons_layout.addWidget(self.new_parameter_button)
            # # self.parameters_buttons_layout.addWidget(self.delete_parameter_button)
            # # self.parameters_buttons_layout.addStretch(1)

            # self.parameters_table = BaseTableWidget()
            # self.parameters_table.setColumnCount(5)
            # self.parameters_table.setHorizontalHeaderLabels(
            #     ["ID", "Name", "Type", "Req", "Default"])
            # self.parameters_table.horizontalHeader().setStretchLastSection(True)
            # self.parameters_table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft)
            # self.parameters_table.setColumnHidden(0, True)
            # self.parameters_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
            # self.parameters_table.verticalHeader().setVisible(False)
            # self.parameters_table.verticalHeader().setDefaultSectionSize(20)
            # self.parameters_table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
            #
            # # self.function_layout.addLayout(self.parameters_layout)
            # self.parameters_layout.addWidget(self.parameters_table)

            # Add the function layout to the main layout
            self.layout.addLayout(self.function_layout)

            # # Connect signals for parameters
            # self.new_parameter_button.clicked.connect(self.new_parameter)
            # self.delete_parameter_button.clicked.connect(self.delete_parameter)

            # Load the initial data
            # self.load_parameters()

        def load(self):
            self.load_functions()
            self.parameters_tab.load()


        def load_functions(self):
            # Load the function list from the database or a config file
            # add dummy data:
            # id, name, description
            data = [
                [1, "Get weather", "Gets current weather for any given locations", 'Run code'],  # script
                [2, "Generate image", "Generate an image", ''],
                [3, "Create file", "Create a new file", ''],
            ]
            self.functions_table.setRowCount(len(data))
            for row, row_data in enumerate(data):
                for column, item in enumerate(row_data):
                    self.functions_table.setItem(row, column, QTableWidgetItem(str(item)))

                combobox_param_type = BaseComboBox()
                combobox_param_type.setFixedWidth(100)
                combobox_param_type.addItems(['Run code'])
                self.functions_table.setCellWidget(row, 3, combobox_param_type)
                combobox_param_type.setCurrentText(row_data[3])

        class Tab_Page_Code(QWidget):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.parent = parent

                self.layout = QVBoxLayout(self)

                self.code_text_area = QTextEdit()
                self.layout.addWidget(self.code_text_area)

        class Tab_Page_Parameters(QWidget):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.parent = parent

                self.layout = QVBoxLayout(self)

                self.parameters_table = BaseTableWidget()
                self.parameters_table.setColumnCount(5)
                self.parameters_table.setHorizontalHeaderLabels(
                    ["ID", "Name", "Type", "Req", "Default"])
                self.parameters_table.horizontalHeader().setStretchLastSection(True)
                self.parameters_table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft)
                self.parameters_table.setColumnHidden(0, True)
                self.parameters_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
                self.parameters_table.verticalHeader().setVisible(False)
                self.parameters_table.verticalHeader().setDefaultSectionSize(20)
                self.parameters_table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)

                self.layout.addWidget(self.parameters_table)

            def load(self):
                # Load the parameters for the selected function
                # add dummy data:
                #   id,
                #   name,
                #   description,
                #   type (dropdown of items ['integer', 'string', ]),,
                #   required (checkbox),
                #   hidden (checkbox)
                data = [
                    [1, "Parameter 1", "integer", True, False],
                    [2, "Parameter 2", "string", False, False],
                    [3, "Parameter 3", "integer", False, True],
                ]
                self.parameters_table.setRowCount(len(data))
                for row, row_data in enumerate(data):
                    for column, item in enumerate(row_data):
                        self.parameters_table.setItem(row, column, QTableWidgetItem(str(item)))

                    # add a combobox column
                    combobox_param_type = BaseComboBox()
                    combobox_param_type.setFixedWidth(100)
                    combobox_param_type.addItems(['INTEGER', 'STRING', 'BOOL', 'LIST'])
                    combobox_param_type.setCurrentText(row_data[2])
                    self.parameters_table.setCellWidget(row, 2, combobox_param_type)

                    chkBox_req = QTableWidgetItem()
                    chkBox_req.setFlags(chkBox_req.flags() | Qt.ItemIsUserCheckable)
                    chkBox_req.setCheckState(Qt.Checked if row_data[3] else Qt.Unchecked)
                    self.parameters_table.setItem(row, 3, chkBox_req)

        def new_function(self):
            # Logic for creating a new function
            pass

        def delete_function(self):
            # Logic for deleting the selected function
            pass

        def rename_function(self):
            # Logic for renaming the selected function
            pass

        def new_parameter(self):
            # Add method logic here
            pass

        def delete_parameter(self):
            # Add method logic here
            pass


    class Page_Sandboxes_Settings(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent

            self.layout = QVBoxLayout(self)

        def load(self):
            pass