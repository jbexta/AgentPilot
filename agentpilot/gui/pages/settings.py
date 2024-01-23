
import json

from PySide6.QtWidgets import *
from PySide6.QtGui import QPixmap, QIcon, QFont, QIntValidator, Qt, QFontDatabase, QDoubleValidator

from agentpilot.utils import sql, api, config
from agentpilot.utils.apis import llm
from agentpilot.gui.components.widgets import ModelComboBox, ColorPickerButton, CComboBox, RoleComboBox, \
    BaseTableWidget, IconButton, ContentPage, ConfigPages  # , ConfigSidebarWidget
from agentpilot.utils.helpers import block_signals, display_messagebox, block_pin_mode


class Page_Settings(ConfigPages):
    def __init__(self, main):
        super().__init__(parent=main)
        self.main = main

        ContentPageTitle = ContentPage(main=main, title='Settings')
        self.layout.addWidget(ContentPageTitle)
        #
        # self.content = QStackedWidget(self)
        #
        self.pages = {
            'System': self.Page_System_Settings(self),
            'API': self.Page_API_Settings(self),
            'Display': self.Page_Display_Settings(self),
            'Blocks': self.Page_Block_Settings(self),
            'Roles': self.Page_Role_Settings(self),
            'Tools': self.Page_Tool_Settings(self),
            'Sandbox': self.Page_Sandboxes_Settings(self),

        }
        self.create_pages()
        self.settings_sidebar.layout.addStretch(1)
        #
        # self.settings_sidebar = self.ConfigSidebarWidget(parent=self)
        #
        # for page_name, page in self.pages.items():
        #     self.content.addWidget(page)
        #
        # layout = QHBoxLayout()
        # layout.addWidget(self.settings_sidebar)
        # layout.addWidget(self.content)
        #
        # container = QWidget()
        # container.setLayout(layout)
        #
        # self.layout.addWidget(container)
        # self.layout.addStretch(1)

    # def load(self):  # Load Settings
    #     self.content.currentWidget().load()

    def update_config(self, key, value):
        config.set_value(key, value)
        config.load_config()
        exclude_load = [
            'system.auto_title_prompt',
        ]
        if key in exclude_load:
            return
        self.main.set_stylesheet()
        self.main.page_chat.load()

    class Page_System_Settings(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.form_layout = QFormLayout(self)

            # text field for dbpath
            self.dev_mode = QCheckBox()
            self.form_layout.addRow(QLabel('Dev Mode:'), self.dev_mode)
            self.dev_mode.stateChanged.connect(lambda state: self.toggle_dev_mode(state))

            self.model_combo = ModelComboBox()
            self.model_combo.setFixedWidth(150)
            self.form_layout.addRow(QLabel('Auto-title Model:'), self.model_combo)
            # connect model data key to update config
            self.model_combo.currentTextChanged.connect(
                lambda: self.parent.update_config('system.auto_title_model', self.model_combo.currentData()))

            # self.model_combo.currentTextChanged.connect(
            #     lambda model: self.parent.update_config('system.auto_title_model',

            self.model_prompt = QTextEdit()
            self.model_prompt.setFixedHeight(45)
            self.form_layout.addRow(QLabel('Auto-title Prompt:'), self.model_prompt)
            self.model_prompt.textChanged.connect(
                lambda: self.parent.update_config('system.auto_title_prompt', self.model_prompt.toPlainText()))

            self.form_layout.addRow(QLabel(''), QLabel(''))

            # add a button 'Reset database'
            self.reset_app_btn = QPushButton('Reset Application')
            self.reset_app_btn.clicked.connect(self.reset_application)
            self.form_layout.addRow(self.reset_app_btn, QLabel(''))

            # add button 'Fix empty titles'
            self.fix_empty_titles_btn = QPushButton('Fix Empty Titles')
            self.fix_empty_titles_btn.clicked.connect(self.fix_empty_titles)
            self.form_layout.addRow(self.fix_empty_titles_btn, QLabel(''))

            # self.setLayout(self.form_layout)

        def load(self):
            with block_signals(self):
                self.dev_mode.setChecked(config.get_value('system.dev_mode', False))
                model_name = config.get_value('system.auto_title_model', '')
                index = self.model_combo.findData(model_name)
                self.model_combo.setCurrentIndex(index)
                self.model_prompt.setText(config.get_value('system.auto_title_prompt', ''))

        def toggle_dev_mode(self, state):
            self.parent.update_config('system.dev_mode', state)
            self.refresh_dev_mode()

        def refresh_dev_mode(self):
            state = config.get_value('system.dev_mode', False)
            main = self.parent.main
            main.page_chat.topbar.btn_info.setVisible(state)
            main.page_chat.topbar.group_settings.group_topbar.btn_clear.setVisible(state)
            main.page_settings.pages['System'].reset_app_btn.setVisible(state)
            main.page_settings.pages['System'].fix_empty_titles_btn.setVisible(state)

        def reset_application(self):
            from agentpilot.context.base import Context

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
            self.refresh_dev_mode()
            self.parent.main.page_chat.context = Context(main=self.parent.main)
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

    class Page_Display_Settings(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.form_layout = QFormLayout()

            # Primary Color
            primary_color_label = QLabel('Primary Color:')
            primary_color_label.setFixedWidth(220)  # Stops width changing when changing role
            self.primary_color_picker = ColorPickerButton()
            self.form_layout.addRow(primary_color_label, self.primary_color_picker)
            self.primary_color_picker.colorChanged.connect(
                lambda color: self.parent.update_config('display.primary_color', color))

            # Secondary Color
            self.secondary_color_picker = ColorPickerButton()
            self.form_layout.addRow(QLabel('Secondary Color:'), self.secondary_color_picker)
            self.secondary_color_picker.colorChanged.connect(
                lambda color: self.parent.update_config('display.secondary_color', color))

            # Text Color
            self.text_color_picker = ColorPickerButton()
            self.form_layout.addRow(QLabel('Text Color:'), self.text_color_picker)
            self.text_color_picker.colorChanged.connect(
                lambda color: self.parent.update_config('display.text_color', color))

            # Text Font (dummy data)
            self.text_font_dropdown = CComboBox()
            available_fonts = QFontDatabase.families()
            self.text_font_dropdown.addItems(available_fonts)

            font_delegate = self.FontItemDelegate(self.text_font_dropdown)
            self.text_font_dropdown.setItemDelegate(font_delegate)
            self.form_layout.addRow(QLabel('Text Font:'), self.text_font_dropdown)
            self.text_font_dropdown.currentTextChanged.connect(
                lambda font: self.parent.update_config('display.text_font', font))

            # Text Size
            self.text_size_input = QSpinBox()
            self.text_size_input.setFixedWidth(150)
            self.text_size_input.setRange(6, 72)  # Assuming a reasonable range for font sizes
            self.form_layout.addRow(QLabel('Text Size:'), self.text_size_input)
            self.text_size_input.valueChanged.connect(lambda size: self.parent.update_config('display.text_size', size))

            # Show Agent Bubble Avatar (combobox with In Group/Always/Never)
            self.agent_avatar_dropdown = CComboBox()
            self.agent_avatar_dropdown.addItems(['In Group', 'Always', 'Never'])
            self.form_layout.addRow(QLabel('Show Agent Bubble Avatar:'), self.agent_avatar_dropdown)
            self.agent_avatar_dropdown.currentTextChanged.connect(
                lambda text: self.parent.update_config('display.agent_avatar_show', text))

            # Agent Bubble Avatar position Top or Middle
            self.agent_avatar_position_dropdown = CComboBox()
            self.agent_avatar_position_dropdown.addItems(['Top', 'Middle'])
            self.form_layout.addRow(QLabel('Agent Bubble Avatar Position:'), self.agent_avatar_position_dropdown)
            self.agent_avatar_position_dropdown.currentTextChanged.connect(
                lambda text: self.parent.update_config('display.agent_avatar_position', text))
            # add spacer
            self.form_layout.addRow(QLabel(''), QLabel(''))

            # Role Combo Box
            self.role_dropdown = RoleComboBox()
            # self.form_layout.addRow(QLabel('Role:'), self.role_dropdown)
            self.form_layout.addRow(self.role_dropdown)
            self.role_dropdown.currentIndexChanged.connect(self.load_role_config)

            selected_role = self.role_dropdown.currentText().title()
            # Bubble Colors
            self.bubble_bg_color_picker = ColorPickerButton()
            self.bubble_bg_color_label = QLabel(f'{selected_role} Bubble Background Color:')
            self.form_layout.addRow(self.bubble_bg_color_label, self.bubble_bg_color_picker)
            self.bubble_bg_color_picker.colorChanged.connect(self.role_config_changed)

            self.bubble_text_color_picker = ColorPickerButton()
            self.bubble_text_color_label = QLabel(f'{selected_role} Bubble Text Color:')
            self.form_layout.addRow(self.bubble_text_color_label, self.bubble_text_color_picker)
            self.bubble_text_color_picker.colorChanged.connect(self.role_config_changed)

            self.bubble_image_size_input = QLineEdit()
            self.bubble_image_size_label = QLabel(f'{selected_role} Image Size:')
            self.bubble_image_size_input.setValidator(QIntValidator(3, 100))
            self.form_layout.addRow(self.bubble_image_size_label, self.bubble_image_size_input)
            self.bubble_image_size_input.textChanged.connect(self.role_config_changed)

            self.setLayout(self.form_layout)

        def load_role_config(self):
            with block_signals(self):
                role_id = self.role_dropdown.currentData()
                role_config_str = sql.get_scalar("""SELECT `config` FROM roles WHERE id = ? """, (role_id,))
                role_config = json.loads(role_config_str)
                bg = role_config.get('display.bubble_bg_color', '#ffffff')
                self.bubble_bg_color_picker.set_color(bg)
                self.bubble_text_color_picker.set_color(role_config.get('display.bubble_text_color', '#ffffff'))
                self.bubble_image_size_input.setText(str(role_config.get('display.bubble_image_size', 50)))

                role = self.role_dropdown.currentText().title()
                self.bubble_bg_color_label.setText(f'{role} Bubble Background Color:')
                self.bubble_text_color_label.setText(f'{role} Bubble Text Color:')
                self.bubble_image_size_label.setText(f'{role} Image Size:')

        def role_config_changed(self):
            role_id = self.role_dropdown.currentData()
            role_config_str = sql.get_scalar("""SELECT `config` FROM roles WHERE id = ? """, (role_id,))
            role_config = json.loads(role_config_str)
            role_config['display.bubble_bg_color'] = self.bubble_bg_color_picker.get_color()
            role_config['display.bubble_text_color'] = self.bubble_text_color_picker.get_color()
            role_config['display.bubble_image_size'] = self.bubble_image_size_input.text()
            sql.execute("""UPDATE roles SET `config` = ? WHERE id = ? """, (json.dumps(role_config), role_id,))
            self.parent.main.system.roles.load()

        def load(self):
            with block_signals(self):
                self.primary_color_picker.set_color(config.get_value('display.primary_color'))
                self.secondary_color_picker.set_color(config.get_value('display.secondary_color'))
                self.text_color_picker.set_color(config.get_value('display.text_color'))
                self.text_font_dropdown.setCurrentText(config.get_value('display.text_font'))
                self.text_size_input.setValue(config.get_value('display.text_size'))
                self.agent_avatar_dropdown.setCurrentText(config.get_value('display.agent_avatar_show'))
                self.agent_avatar_position_dropdown.setCurrentText(config.get_value('display.agent_avatar_position'))

            self.load_role_config()

        class FontItemDelegate(QStyledItemDelegate):
            def paint(self, painter, option, index):
                font_name = index.data()

                self.font = option.font
                self.font.setFamily(font_name)
                self.font.setPointSize(12)

                painter.setFont(self.font)
                painter.drawText(option.rect, Qt.TextSingleLine, index.data())

    class Page_API_Settings(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent

            self.layout = QVBoxLayout(self)

            # container for the table and a 20px wide sidebar
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
                self.parent.parent.main.page_chat.context.load()
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

    class Page_Block_Settings(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.layout = QHBoxLayout(self)

            self.table = BaseTableWidget(self)
            self.table.setColumnCount(2)
            self.table.setColumnHidden(0, True)
            self.table.setHorizontalHeaderLabels(['ID', 'Name'])
            self.table.horizontalHeader().setStretchLastSection(True)
            self.table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed)
            # self.table.setFixedWidth(175)
            self.table.itemChanged.connect(self.name_edited)  # Connect the itemChanged signal to the item_edited method
            self.table.itemSelectionChanged.connect(self.on_block_selected)

            # self.table.setColumnWidth(1, 125)  # Set Name column width

            # container holding a button bar and the table
            self.table_container = QWidget(self)
            self.table_container_layout = QVBoxLayout(self.table_container)
            self.table_container_layout.setContentsMargins(0, 0, 0, 0)
            self.table_container_layout.setSpacing(0)

            # button bar
            self.button_layout = QHBoxLayout()
            self.add_block_button = QPushButton(self)
            self.add_block_button.setIcon(QIcon(QPixmap(":/resources/icon-new.png")))
            self.add_block_button.clicked.connect(self.add_block)
            self.button_layout.addWidget(self.add_block_button)

            self.delete_block_button = QPushButton(self)
            self.delete_block_button.setIcon(QIcon(QPixmap(":/resources/icon-minus.png")))
            self.delete_block_button.clicked.connect(self.delete_block)
            self.button_layout.addWidget(self.delete_block_button)
            self.button_layout.addStretch(1)

            # add the button bar to the table container layout
            self.table_container_layout.addLayout(self.button_layout)
            # add the table to the table container layout
            self.table_container_layout.addWidget(self.table)
            # Adding table container to the layout
            self.layout.addWidget(self.table_container)

            # block data area
            self.block_data_layout = QVBoxLayout()
            self.block_data_label = QLabel("Block data")
            self.block_data_text_area = QTextEdit()
            self.block_data_text_area.textChanged.connect(self.text_edited)

            # Adding pages to the vertical layout
            self.block_data_layout.addWidget(self.block_data_label)
            self.block_data_layout.addWidget(self.block_data_text_area)

            # Adding the vertical layout to the main layout
            self.layout.addLayout(self.block_data_layout)

        def load(self):
            # Fetch the data from the database
            with block_signals(self):
                self.table.setRowCount(0)
                data = sql.get_results("""
                    SELECT
                        id,
                        name
                    FROM blocks""")
                for row_data in data:
                    row_position = self.table.rowCount()
                    self.table.insertRow(row_position)
                    for column, item in enumerate(row_data):
                        self.table.setItem(row_position, column, QTableWidgetItem(str(item)))

            if self.table.rowCount() > 0:
                self.table.selectRow(0)

        def name_edited(self, item):
            row = item.row()
            if row == -1: return
            block_id = self.table.item(row, 0).text()

            id_map = {
                1: 'name',
            }

            column = item.column()
            if column not in id_map:
                return
            column_name = id_map.get(column)
            new_value = item.text()
            sql.execute(f"""
                UPDATE blocks
                SET {column_name} = ?
                WHERE id = ?
            """, (new_value, block_id,))

            # reload blocks
            self.parent.main.system.blocks.load()

        def text_edited(self):
            current_row = self.table.currentRow()
            if current_row == -1: return
            block_id = self.table.item(current_row, 0).text()
            text = self.block_data_text_area.toPlainText()
            sql.execute(f"""
                UPDATE blocks
                SET text = ?
                WHERE id = ?
            """, (text, block_id,))

            self.parent.main.system.blocks.load()

        def on_block_selected(self):
            current_row = self.table.currentRow()
            if current_row == -1: return
            att_id = self.table.item(current_row, 0).text()
            att_text = sql.get_scalar(f"""
                SELECT
                    `text`
                FROM blocks
                WHERE id = ?
            """, (att_id,))

            with block_signals(self):
                self.block_data_text_area.setText(att_text)

        def add_block(self):
            with block_pin_mode():
                text, ok = QInputDialog.getText(self, 'New Block', 'Enter the placeholder tag for the block:')

                if ok:
                    sql.execute("INSERT INTO `blocks` (`name`, `text`) VALUES (?, '')", (text,))
                    self.load()
                    self.parent.main.system.blocks.load()

        def delete_block(self):
            current_row = self.table.currentRow()
            if current_row == -1: return
            # ask confirmation qdialog
            retval = display_messagebox(
                icon=QMessageBox.Warning,
                text="Are you sure you want to delete this block?",
                title="Delete Block",
                buttons=QMessageBox.Yes | QMessageBox.No,
            )
            if retval != QMessageBox.Yes:
                return

            block_id = self.table.item(current_row, 0).text()
            sql.execute("DELETE FROM `blocks` WHERE `id` = ?", (block_id,))
            self.load()
            self.parent.main.system.blocks.load()

    class Page_Role_Settings(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.layout = QHBoxLayout(self)

            self.table = BaseTableWidget(self)
            self.table.setColumnCount(2)
            self.table.setColumnHidden(0, True)
            self.table.setHorizontalHeaderLabels(['ID', 'Name'])
            self.table.horizontalHeader().setStretchLastSection(True)
            self.table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed)
            self.table.setFixedWidth(175)
            self.table.itemChanged.connect(self.name_edited)  # Connect the itemChanged signal to the item_edited method
            # self.table.itemSelectionChanged.connect(self.on_block_selected)

            # self.table.setColumnWidth(1, 125)  # Set Name column width

            # container holding a button bar and the table
            self.table_container = QWidget(self)
            self.table_container_layout = QVBoxLayout(self.table_container)
            self.table_container_layout.setContentsMargins(0, 0, 0, 0)
            self.table_container_layout.setSpacing(0)

            # button bar
            self.button_layout = QHBoxLayout()
            self.add_role_button = QPushButton(self)
            self.add_role_button.setIcon(QIcon(QPixmap(":/resources/icon-new.png")))
            self.add_role_button.clicked.connect(self.add_role)
            self.button_layout.addWidget(self.add_role_button)

            self.delete_role_button = QPushButton(self)
            self.delete_role_button.setIcon(QIcon(QPixmap(":/resources/icon-minus.png")))
            self.delete_role_button.clicked.connect(self.delete_role)
            self.button_layout.addWidget(self.delete_role_button)
            self.button_layout.addStretch(1)

            # add the button bar to the table container layout
            self.table_container_layout.addLayout(self.button_layout)
            # add the table to the table container layout
            self.table_container_layout.addWidget(self.table)
            # Adding table container to the layout
            self.layout.addWidget(self.table_container)

            # # block data area
            # self.block_data_layout = QVBoxLayout()
            # self.block_data_label = QLabel("Block data")
            # self.block_data_text_area = QTextEdit()
            # self.block_data_text_area.textChanged.connect(self.text_edited)
            #
            # # Adding pages to the vertical layout
            # self.block_data_layout.addWidget(self.block_data_label)
            # self.block_data_layout.addWidget(self.block_data_text_area)
            #
            # # Adding the vertical layout to the main layout
            # self.layout.addLayout(self.block_data_layout)

        def load(self):
            # Fetch the data from the database
            with block_signals(self):
                self.table.setRowCount(0)
                data = sql.get_results("""
                    SELECT
                        id,
                        name
                    FROM roles""")
                for row_data in data:
                    row_position = self.table.rowCount()
                    self.table.insertRow(row_position)
                    for column, item in enumerate(row_data):
                        self.table.setItem(row_position, column, QTableWidgetItem(str(item)))

            if self.table.rowCount() > 0:
                self.table.selectRow(0)

        def name_edited(self, item):
            row = item.row()
            if row == -1: return
            role_id = self.table.item(row, 0).text()

            id_map = {
                1: 'name',
            }

            column = item.column()
            if column not in id_map:
                return
            column_name = id_map.get(column)
            new_value = item.text()
            sql.execute(f"""
                UPDATE roles
                SET {column_name} = ?
                WHERE id = ?
            """, (new_value, role_id,))

            # reload blocks
            self.parent.main.system.roles.load()

        def add_role(self):
            with block_pin_mode():
                text, ok = QInputDialog.getText(self, 'New Role', 'Enter a name for the role:')

                if ok:
                    sql.execute("INSERT INTO `roles` (`name`) VALUES (?)", (text,))
                    self.load()
                    self.parent.main.system.blocks.load()

        def delete_role(self):
            current_row = self.table.currentRow()
            if current_row == -1: return
            # ask confirmation qdialog
            retval = display_messagebox(
                icon=QMessageBox.Warning,
                text="Are you sure you want to delete this role?",
                title="Delete Role",
                buttons=QMessageBox.Yes | QMessageBox.No,
            )
            if retval != QMessageBox.Yes:
                return

            block_id = self.table.item(current_row, 0).text()
            sql.execute("DELETE FROM `roles` WHERE `id` = ?", (block_id,))
            self.load()
            self.parent.main.system.blocks.load()

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

                combobox_param_type = CComboBox()
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
                    combobox_param_type = CComboBox()
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