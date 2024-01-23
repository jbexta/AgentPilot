import json

from PySide6.QtWidgets import *
from PySide6.QtCore import Signal
from PySide6.QtGui import QPixmap, QColor, QIcon, QFont, QPainter, QPainterPath, QIntValidator, Qt

from agentpilot.utils.filesystem import simplify_path
from agentpilot.utils.helpers import path_to_pixmap, display_messagebox, block_signals, block_pin_mode
from agentpilot.utils import sql
from agentpilot.utils.plugin import get_plugin_agent_class

from agentpilot.gui.style import SECONDARY_COLOR, TEXT_COLOR
from agentpilot.gui.components.widgets import CComboBox, ModelComboBox, APIComboBox, BaseTableWidget, PluginComboBox, \
    ConfigPageWidget, ConfigPages, DynamicPluginSettings, get_widget_value  # , ConfigSidebarWidget


class AgentSettings(ConfigPages):
    def __init__(self, parent, is_context_member_agent=False):
        super().__init__(parent=parent)
        self.parent = parent
        self.main = parent.main
        self.is_context_member_agent = is_context_member_agent
        self.agent_id = 0
        # self.agent_config = {}

        self.pages = {
            'General': self.Page_General_Settings(self),
            'Context': self.Page_Context_Settings(self),
            'Tools': self.Page_Actions_Settings(self),
            'Group': self.Page_Group_Settings(self),
            'Voice': self.Page_Voice_Settings(self),
        }
        self.create_pages()
        # self.settings_sidebar = self.Agent_Settings_SideBar(self)

        # # Set the size policy
        # sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        # sizePolicy.setHorizontalStretch(0)
        # sizePolicy.setVerticalStretch(0)
        # self.setSizePolicy(sizePolicy)
    #
    # def get_current_config(self):
    #     pass
    #     # Retrieve the current values from the pages and construct a new 'config' dictionary
    #     current_config = {
    #         'general.name': self.page_general.name.text(),
    #         'general.avatar_path': self.page_general.avatar_path,
    #         'general.use_plugin': self.page_general.plugin_combo.currentData(),
    #         'context.model': self.page_context.model_combo.currentData(),
    #         'context.sys_msg': self.page_context.sys_msg.toPlainText(),
    #         'context.max_messages': self.page_context.max_messages.value(),
    #         'context.max_turns': self.page_context.max_turns.value(),
    #         'context.auto_title': self.page_context.auto_title.isChecked(),
    #         'context.display_markdown': self.page_context.display_markdown.isChecked(),
    #         'context.on_consecutive_response': self.page_context.on_consecutive_response.currentText(),
    #         'context.user_msg': self.page_context.user_msg.toPlainText(),
    #         'actions.enable_actions': self.page_functions.enable_actions.isChecked(),
    #         'actions.source_directory': self.page_functions.source_directory.text(),
    #         'actions.replace_busy_action_on_new': self.page_functions.replace_busy_action_on_new.isChecked(),
    #         'actions.use_function_calling': self.page_functions.use_function_calling.isChecked(),
    #         'actions.use_validator': self.page_functions.use_validator.isChecked(),
    #         'actions.code_auto_run_seconds': self.page_functions.code_auto_run_seconds.text(),
    #         'group.hide_responses': self.page_group.hide_responses.isChecked(),
    #         'group.output_context_placeholder': self.page_group.output_context_placeholder.text().replace('{', '').replace('}', ''),
    #         'group.on_multiple_inputs': self.page_group.on_multiple_inputs.currentText(),
    #         'group.set_members_as_user_role': self.page_group.set_members_as_user_role.isChecked(),
    #         'voice.current_id': int(self.page_voice.current_id),
    #     }
    #     # plugin config
    #     # for widget in page general
    #     for widget in self.page_general.plugin_settings.findChildren(QWidget):
    #         key = widget.property('config_key')
    #         if not key:
    #             continue
    #         current_config[f'plugin.{key}'] = self.get_widget_value(widget)
    #
    #     # instance config
    #     member = self.main.page_chat.context.members.get(self.agent_id, None)
    #     if member and self.is_context_member_agent:
    #         instance_config = getattr(member.agent, 'instance_config', {})
    #         current_config.update({f'instance.{key}': value for key, value in instance_config.items()})
    #
    #     return json.dumps(current_config)
    #
    # def get_widget_value(self, widget):
    #     if isinstance(widget, QCheckBox):
    #         return widget.isChecked()
    #     elif isinstance(widget, QLineEdit):
    #         return widget.text()
    #     elif isinstance(widget, QComboBox):
    #         return widget.currentText()
    #     elif isinstance(widget, QSpinBox):
    #         return widget.value()
    #     elif isinstance(widget, QDoubleSpinBox):
    #         return widget.value()
    #     elif isinstance(widget, QTextEdit):
    #         return widget.toPlainText()
    #     else:
    #         raise Exception(f'Widget not implemented: {type(widget)}')

    def save_config(self):
        """Saves the config to database when modified"""
        # current_config = self.get_current_config()
        # self.agent_config = json.loads(current_config)
        # name = self.page_general.name.text()
        # todo - ignore instance keys
        if self.is_context_member_agent:
            sql.execute("UPDATE contexts_members SET agent_config = ? WHERE id = ?", (self.config, self.agent_id))
            self.main.page_chat.context.load_members()
            # self.load()
        else:
            name = self.config.get('general.name', 'Assistant')
            sql.execute("UPDATE agents SET config = ?, name = ? WHERE id = ?", (self.config, name, self.agent_id))
            # self.parent.load()

    # def load(self):
    #     pages = (
    #         self.page_general,
    #         self.page_context,
    #         self.page_functions,
    #         self.page_group,
    #         self.page_voice
    #     )
    #     for page in pages:
    #         page.load()
    #
    #     self.settings_sidebar.load()

    class ConfigSidebarWidget(ConfigPages.ConfigSidebarWidget):
        def __init__(self, parent):
            super().__init__(parent=parent, width=75)

            self.button_layout = QHBoxLayout()
            self.button_layout.addStretch(1)

            self.btn_pull = QPushButton(self)
            self.btn_pull.setIcon(QIcon(QPixmap(":/resources/icon-pull.png")))
            self.btn_pull.setToolTip("Set member config to agent default")
            self.btn_pull.clicked.connect(self.pull_member_config)
            self.button_layout.addWidget(self.btn_pull)

            self.btn_push = QPushButton(self)
            self.btn_push.setIcon(QIcon(QPixmap(":/resources/icon-push.png")))
            self.btn_push.setToolTip("Set all member configs to agent default")
            self.btn_push.clicked.connect(self.push_member_config)
            self.button_layout.addWidget(self.btn_push)

            self.button_layout.addStretch(1)

            self.warning_label = QLabel("A plugin is enabled, these settings may not work as expected")
            self.warning_label.setFixedWidth(75)
            self.warning_label.setWordWrap(True)
            # self.warning_label.setStyleSheet(f"color: {TEXT_COLOR};")
            self.warning_label.setAlignment(Qt.AlignCenter)

            self.warning_label.hide()
            self.wl_font = self.warning_label.font()
            self.wl_font.setPointSize(7)
            self.warning_label.setFont(self.wl_font)

            self.layout.addLayout(self.button_layout)
            self.layout.addStretch(1)
            self.layout.addWidget(self.warning_label)
            self.layout.addStretch(1)

        def load(self):
            self.refresh_warning_label()

            # Different load depending on source of AgentSetting
            if self.parent.is_context_member_agent:
                self.btn_push.hide()
                # only called from a default agent settings:
                # if context member config is not the same as agent config default, then show
                member_id = self.parent.agent_id
                default_config_str = sql.get_scalar("SELECT config FROM agents WHERE id = (SELECT agent_id FROM contexts_members WHERE id = ?)", (member_id,))
                if default_config_str is None:
                    default_config = {}
                else:
                    default_config = json.loads(default_config_str)
                member_config = self.parent.agent_config
                # todo dirty
                # remove instance keys
                member_config = {key: value for key, value in member_config.items() if not key.startswith('instance.')}
                config_mismatch = default_config != member_config

                self.btn_pull.setVisible(config_mismatch)
            else:
                self.btn_pull.hide()
                # only called from a member config settings:
                # if any context member config is not the same as agent config default, then show
                default_config = self.parent.agent_config
                member_configs = sql.get_results("SELECT agent_config FROM contexts_members WHERE agent_id = ?",
                                                 (self.parent.agent_id,), return_type='list')
                config_mismatch = any([json.loads(member_config) != default_config for member_config in member_configs])
                self.btn_push.setVisible(config_mismatch)

        def pull_member_config(self):
            # only called from a member config settings: sets member config to default
            retval = display_messagebox(
                icon=QMessageBox.Question,
                text="Are you sure you want to set this member config to default?",
                title="Pull Default Settings",
                buttons=QMessageBox.Yes | QMessageBox.No,
            )
            if retval != QMessageBox.Yes:
                return
            default_config = sql.get_scalar("SELECT config FROM agents WHERE id = (SELECT agent_id FROM contexts_members WHERE id = ?)", (self.parent.agent_id,))
            sql.execute("UPDATE contexts_members SET agent_config = ? WHERE id = ?", (default_config, self.parent.agent_id))
            self.parent.load()

        def push_member_config(self):
            # only called from a default agent settings: sets all member configs to default
            retval = display_messagebox(
                icon=QMessageBox.Question,
                text="Are you sure you want to set all member configs to default?",
                title="Push To Members",
                buttons=QMessageBox.Yes | QMessageBox.No,
            )
            # todo
            if retval != QMessageBox.Yes:
                return
            default_config = self.parent.agent_config
            sql.execute("UPDATE contexts_members SET agent_config = ? WHERE agent_id = ?", (json.dumps(default_config), self.parent.agent_id))
            self.load()

        def onButtonToggled(self, button, checked):
            if checked:
                index = self.button_group.id(button)
                self.parent.content.setCurrentIndex(index)
                # self.parent.content.currentWidget().load()
                self.refresh_warning_label()

        def refresh_warning_label(self):
            index = self.parent.content.currentIndex()
            show_plugin_warning = index > 0 and self.parent.agent_config.get('general.use_plugin', '') != ''
            if show_plugin_warning:
                self.warning_label.show()
            else:
                self.warning_label.hide()

        # class Settings_SideBar_Button(QPushButton):
        #     def __init__(self, parent, text=''):
        #         super().__init__(parent=parent)
        #         self.setProperty("class", "menuitem")
        #
        #         self.setText(text)
        #         self.setFixedSize(75, 30)
        #         self.setCheckable(True)
        #
        #         self.font = QFont()
        #         self.font.setPointSize(13)
        #         self.setFont(self.font)

    class Page_General_Settings(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)  # , alignment=Qt.AlignCenter)
            self.parent = parent
            # self.namespace = 'general'
            # self.schema = [
            #     {
            #         'text': 'Avatar',
            #         'type': bool,
            #         'default': False,
            #     },
            #     {
            #         'text': 'Output context placeholder',
            #         'type': str,
            #         'default': '',
            #     },
            #     {
            #         'text': 'On multiple inputs',
            #         'type': ('Append to system msg', 'Merged user message', 'Reply individually'),
            #         'default': 'Merged user message',
            #     },
            #     {
            #         'text': 'Show members as user role',
            #         'type': bool,
            #         'default': True,
            #     },
            # ]

            main_layout = QVBoxLayout(self)
            main_layout.setAlignment(Qt.AlignCenter)

            profile_layout = QHBoxLayout()
            profile_layout.setAlignment(Qt.AlignCenter)

            self.avatar_path = ''
            self.avatar = self.ClickableAvatarLabel(self)
            self.avatar.clicked.connect(self.change_avatar)

            self.name = QLineEdit()
            self.name.textChanged.connect(parent.update_agent_config)

            # print('#424')
            self.name_font = QFont()
            self.name_font.setPointSize(15)
            self.name.setFont(self.name_font)

            self.name.setAlignment(Qt.AlignCenter)

            # Create a combo box for the plugin selection
            self.plugin_combo = PluginComboBox()
            self.plugin_settings = DynamicPluginSettings(self, self.plugin_combo)

            # # set first item text to 'No Plugin' if no plugin is selected
            # if self.plugin_combo.currentData() == '':
            #     self.plugin_combo.setItemText(0, "Choose Plugin")
            # else:
            #     self.plugin_combo.setItemText(0, "< No Plugin >")

            # Adding avatar and name to the main layout
            profile_layout.addWidget(self.avatar)  # Adding the avatar

            # add profile layout to main layout
            main_layout.addLayout(profile_layout)
            main_layout.addWidget(self.name)
            main_layout.addWidget(self.plugin_combo, alignment=Qt.AlignCenter)
            main_layout.addWidget(self.plugin_settings)
            main_layout.addStretch()

        def load(self):
            pass
            # with block_signals(self):
            #     self.avatar_path = self.parent.agent_config.get('general.avatar_path', '')
            #     diameter = self.avatar.width()
            #     avatar_img = path_to_pixmap(self.avatar_path, diameter=diameter)
            #
            #     self.avatar.setPixmap(avatar_img)
            #     self.avatar.update()
            #
            #     self.name.setText(self.parent.agent_config.get('general.name', ''))
            #
            #     active_plugin = self.parent.agent_config.get('general.use_plugin', '')
            #     for i in range(self.plugin_combo.count()):  # todo dirty
            #         if self.plugin_combo.itemData(i) == active_plugin:
            #             self.plugin_combo.setCurrentIndex(i)
            #             break
            #     else:
            #         self.plugin_combo.setCurrentIndex(0)
            #     self.plugin_settings.load()

        def get_config(self):
            config = {
                'general.name': get_widget_value(self.name),
                'general.avatar_path': get_widget_value(self.avatar_path),
                'general.use_plugin': get_widget_value(self.plugin_combo),
            }
            return config

        # def plugin_changed(self):
        #     self.parent.update_agent_config()

        class ClickableAvatarLabel(QLabel):
            clicked = Signal()

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.setAlignment(Qt.AlignCenter)
                self.setCursor(Qt.PointingHandCursor)
                self.setFixedSize(100, 100)
                self.setStyleSheet(
                    f"border: 1px dashed {TEXT_COLOR}; border-radius: 50px;")  # A custom style for the empty label

            def mousePressEvent(self, event):
                super().mousePressEvent(event)
                if event.button() == Qt.LeftButton:
                    self.clicked.emit()

            def setPixmap(self, pixmap):
                super().setPixmap(pixmap.scaled(
                    self.width(), self.height(),
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation
                ))

            def paintEvent(self, event):
                # Override paintEvent to draw a circular image
                painter = QPainter(self)
                painter.setRenderHint(QPainter.Antialiasing)
                # attempts = 0  # todo - temp to try to find segfault
                # while not painter.isActive() and attempts < 10:
                #     attempts += 1
                #     time.sleep(0.5)
                # if not painter.isActive():
                #     raise Exception('Painter not active after 5 seconds')

                path = QPainterPath()
                path.addEllipse(0, 0, self.width(), self.height())
                painter.setClipPath(path)
                painter.drawPixmap(0, 0, self.pixmap())
                painter.end()

        def change_avatar(self):
            with block_pin_mode():
                options = QFileDialog.Options()
                filename, _ = QFileDialog.getOpenFileName(self, "Choose Avatar", "",
                                                          "Images (*.png *.jpeg *.jpg *.bmp *.gif)", options=options)

            if filename:
                filename = filename
                print('change_avatar, simplified fn: ', filename)
                self.avatar.setPixmap(QPixmap(filename))

                simp_path = simplify_path(filename)
                print(f'Simplified {filename} to {simp_path}')
                self.avatar_path = simplify_path(filename)
                self.parent.update_agent_config()

    class Page_Context_Settings(ConfigPageWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.namespace = 'context'
            self.schema = [
                {
                    'text': 'Model',
                    'type': 'ModelComboBox',
                    'default': 'gpt-3.5-turbo',
                    'row_key': 0,
                },
                {
                    'text': 'Auto title',
                    'type': bool,
                    'default': True,
                    'row_key': 0,
                },
                {
                    'text': 'System message',
                    'key': 'sys_msg',
                    'type': str,
                    'num_lines': 10,
                    'default': '',
                    'width': 450,
                    'label_align': 'top',
                },
                {
                    'text': 'Max messages',
                    'type': int,
                    'default': 8,
                    'width': 60,
                    'row_key': 2,
                },
                {
                    'text': 'Display markdown',
                    'type': bool,
                    'default': True,
                    'row_key': 2,
                },
                {
                    'text': 'Max turns',
                    'type': int,
                    'default': 5,
                    'width': 60,
                    'row_key': 3,
                },
                {
                    'text': 'Consecutive responses',
                    'key': 'on_consecutive_response',
                    'type': ('PAD', 'REPLACE', 'NOTHING'),
                    'default': 'REPLACE',
                    'width': 90,
                    'row_key': 3,
                },
                {
                    'text': 'User message',
                    'key': 'user_msg',
                    'type': str,
                    'num_lines': 3,
                    'default': '',
                    'width': 450,
                    'label_align': 'top',
                },
            ]


            # ######################################
            #
            # self.form_layout = QFormLayout()
            #
            # self.model_combo = ModelComboBox()
            # self.model_combo.setFixedWidth(150)
            #
            # self.auto_title = QCheckBox()
            # self.auto_title.setFixedWidth(30)
            # # self.form_layout.addRow(QLabel('Auto title:'), self.auto_title)
            #
            # # Create a QHBoxLayout and add max_messages and auto_title to it
            # self.model_and_auto_title_layout = QHBoxLayout()
            # self.model_and_auto_title_layout.setSpacing(70)
            # self.model_and_auto_title_layout.addWidget(QLabel('Model:'))
            # self.model_and_auto_title_layout.addWidget(self.model_combo)
            # self.model_and_auto_title_layout.addWidget(QLabel('Auto title:'))
            # self.model_and_auto_title_layout.addWidget(self.auto_title)
            #
            # # Add the QHBoxLayout to the form layout
            # self.form_layout.addRow(self.model_and_auto_title_layout)
            #
            # self.sys_msg = QTextEdit()
            # self.sys_msg.setFixedHeight(140)
            # self.form_layout.addRow(QLabel('System message:'), self.sys_msg)
            #
            # self.max_messages = QSpinBox()
            # self.max_messages.setFixedWidth(60)  # Consistent width
            # # self.form_layout.addRow(QLabel('Max messages:'), self.max_messages)
            #
            # display_markdown_label = QLabel('Display markdown:')
            # display_markdown_label.setFixedWidth(100)
            # self.display_markdown = QCheckBox()
            # self.display_markdown.setFixedWidth(30)
            # # self.form_layout.addRow(QLabel('Display markdown:'), self.display_markdown)
            # self.max_msgs_and_markdown_layout = QHBoxLayout()
            # self.max_msgs_and_markdown_layout.setSpacing(10)
            # self.max_msgs_and_markdown_layout.addWidget(QLabel('Max messages:'))
            # self.max_msgs_and_markdown_layout.addWidget(self.max_messages)
            # self.max_msgs_and_markdown_layout.addStretch(1)
            # self.max_msgs_and_markdown_layout.addWidget(QLabel('Display markdown:'))
            # self.max_msgs_and_markdown_layout.addWidget(self.display_markdown)
            #
            # # Add the QHBoxLayout to the form layout
            # self.form_layout.addRow(self.max_msgs_and_markdown_layout)
            #
            # self.max_turns_and_consec_response_layout = QHBoxLayout()
            # self.max_turns_and_consec_response_layout.setSpacing(10)
            # self.max_turns_and_consec_response_layout.addStretch(1)
            # self.max_turns_and_consec_response_layout.addWidget(QLabel('Max turns:'))
            # self.max_turns = QSpinBox()
            # self.max_turns.setFixedWidth(60)
            # self.max_turns_and_consec_response_layout.addWidget(self.max_turns)
            #
            # self.max_turns_and_consec_response_layout.addStretch(1)
            #
            # self.max_turns_and_consec_response_layout.addWidget(QLabel('Consecutive responses:'))
            # self.on_consecutive_response = CComboBox()
            # self.on_consecutive_response.addItems(['PAD', 'REPLACE', 'NOTHING'])
            # self.on_consecutive_response.setFixedWidth(90)
            # self.max_turns_and_consec_response_layout.addWidget(self.on_consecutive_response)
            # self.form_layout.addRow(self.max_turns_and_consec_response_layout)
            #
            # self.user_msg = QTextEdit()
            # # set placeholder text with grey color
            # self.user_msg.setFixedHeight(80)  # Adjust height as per requirement
            # self.form_layout.addRow(QLabel('User message:'), self.user_msg)
            #
            # # Add the form layout to a QVBoxLayout and add a spacer to push everything to the top
            # self.main_layout = QVBoxLayout(self)
            # self.main_layout.addLayout(self.form_layout)
            # spacer = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
            # self.main_layout.addItem(spacer)
            #
            # self.model_combo.currentIndexChanged.connect(parent.update_agent_config)
            # self.auto_title.stateChanged.connect(parent.update_agent_config)
            # self.sys_msg.textChanged.connect(parent.update_agent_config)
            # self.display_markdown.stateChanged.connect(parent.update_agent_config)
            # self.max_messages.valueChanged.connect(parent.update_agent_config)
            # self.max_turns.valueChanged.connect(parent.update_agent_config)
            # self.on_consecutive_response.currentIndexChanged.connect(parent.update_agent_config)
            # self.user_msg.textChanged.connect(parent.update_agent_config)

        def load(self):
            pass
            # parent = self.parent
            # with block_signals(self):
            #     self.model_combo.load()
            #
            #     # Save current position
            #     sys_msg_cursor_pos = self.sys_msg.textCursor().position()
            #     user_msg_cursor_pos = self.user_msg.textCursor().position()
            #
            #     model_name = parent.agent_config.get('context.model', '')
            #     index = self.model_combo.findData(model_name)
            #     self.model_combo.setCurrentIndex(index)
            #
            #     self.auto_title.setChecked(parent.agent_config.get('context.auto_title', True))
            #     self.sys_msg.setText(parent.agent_config.get('context.sys_msg', ''))
            #     # self.fallback_to_davinci.setChecked(parent.agent_config.get('context.fallback_to_davinci', False))
            #     self.max_messages.setValue(parent.agent_config.get('context.max_messages', 5))
            #     self.display_markdown.setChecked(parent.agent_config.get('context.display_markdown', False))
            #     self.max_turns.setValue(parent.agent_config.get('context.max_turns', 5))
            #     self.on_consecutive_response.setCurrentText(
            #         parent.agent_config.get('context.on_consecutive_response', 'REPLACE'))
            #     self.user_msg.setText(parent.agent_config.get('context.user_msg', ''))
            #
            #     # Restore cursor position
            #     sys_msg_cursor = self.sys_msg.textCursor()
            #     sys_msg_cursor.setPosition(sys_msg_cursor_pos)
            #     self.sys_msg.setTextCursor(sys_msg_cursor)
            #
            #     user_msg_cursor = self.user_msg.textCursor()
            #     user_msg_cursor.setPosition(user_msg_cursor_pos)
            #     self.user_msg.setTextCursor(user_msg_cursor)

    class Page_Actions_Settings(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent

            self.form_layout = QFormLayout()

            # Enable actions - checkbox
            self.enable_actions = QCheckBox()
            self.form_layout.addRow(QLabel('Enable actions:'), self.enable_actions)

            # Source directory - path field and button to trigger folder dialog
            self.source_directory = QLineEdit()
            self.browse_button = QPushButton("..")
            self.browse_button.setFixedSize(25, 25)
            self.browse_button.clicked.connect(self.browse_for_folder)

            # Create labels as member variables
            self.label_source_directory = QLabel('Source Directory:')
            self.label_replace_busy_action_on_new = QLabel('Replace busy action on new:')
            self.label_use_function_calling = QLabel('Use function calling:')
            self.label_use_validator = QLabel('Use validator:')
            self.label_code_auto_run_seconds = QLabel('Code auto-run seconds:')

            hbox = QHBoxLayout()
            hbox.addWidget(self.browse_button)
            hbox.addWidget(self.source_directory)
            self.form_layout.addRow(self.label_source_directory, hbox)

            self.replace_busy_action_on_new = QCheckBox()
            self.form_layout.addRow(self.label_replace_busy_action_on_new, self.replace_busy_action_on_new)

            self.use_function_calling = QCheckBox()
            # self.form_layout.addRow(self.label_use_function_calling, self.use_function_calling)

            # Create the combo box and add the items
            self.function_calling_mode = CComboBox()
            self.function_calling_mode.addItems(['ISOLATED', 'INTEGRATED'])
            # self.form_layout.addRow(QLabel('Function Calling Mode:'), self.function_calling_mode)

            # Create a new horizontal layout to include the check box and the combo box
            function_calling_layout = QHBoxLayout()
            function_calling_layout.addWidget(self.use_function_calling)
            function_calling_layout.addWidget(self.function_calling_mode)
            function_calling_layout.addStretch(1)

            # Make the combo box initially hidden
            self.function_calling_mode.setVisible(False)
            self.function_calling_mode.setFixedWidth(150)
            self.form_layout.addRow(self.label_use_function_calling, function_calling_layout)

            self.use_validator = QCheckBox()
            self.form_layout.addRow(self.label_use_validator, self.use_validator)

            self.code_auto_run_seconds = QLineEdit()
            self.code_auto_run_seconds.setValidator(QIntValidator(0, 300))
            self.form_layout.addRow(self.label_code_auto_run_seconds, self.code_auto_run_seconds)

            self.setLayout(self.form_layout)

            # Connect the 'stateChanged' signal of 'use_function_calling' to a new method
            self.use_function_calling.stateChanged.connect(self.toggle_function_calling_type_visibility())

            self.enable_actions.stateChanged.connect(self.toggle_enabled_state)
            self.enable_actions.stateChanged.connect(parent.update_agent_config)
            self.source_directory.textChanged.connect(parent.update_agent_config)
            self.replace_busy_action_on_new.stateChanged.connect(parent.update_agent_config)
            self.use_function_calling.stateChanged.connect(parent.update_agent_config)
            self.use_validator.stateChanged.connect(parent.update_agent_config)
            self.code_auto_run_seconds.textChanged.connect(parent.update_agent_config)

        def load(self):
            parent = self.parent
            with block_signals(self):
                self.enable_actions.setChecked(parent.agent_config.get('actions.enable_actions', False))
                self.source_directory.setText(parent.agent_config.get('actions.source_directory', ''))
                self.replace_busy_action_on_new.setChecked(
                    parent.agent_config.get('actions.replace_busy_action_on_new', False))
                self.use_function_calling.setChecked(parent.agent_config.get('actions.use_function_calling', False))
                self.use_validator.setChecked(parent.agent_config.get('actions.use_validator', False))
                self.code_auto_run_seconds.setText(str(parent.agent_config.get('actions.code_auto_run_seconds', 5)))

            self.toggle_enabled_state()
            self.toggle_function_calling_type_visibility()

        def browse_for_folder(self):
            folder = QFileDialog.getExistingDirectory(self, "Select Source Directory")
            if folder:
                self.source_directory.setText(folder)

        def toggle_enabled_state(self):
            global TEXT_COLOR
            is_enabled = self.enable_actions.isChecked()

            self.source_directory.setEnabled(is_enabled)
            self.browse_button.setEnabled(is_enabled)
            self.replace_busy_action_on_new.setEnabled(is_enabled)
            self.use_function_calling.setEnabled(is_enabled)
            self.use_validator.setEnabled(is_enabled)

            if is_enabled:
                color = TEXT_COLOR
            else:
                color = "#4d4d4d"

            self.label_source_directory.setStyleSheet(f"color: {color}")
            self.label_replace_busy_action_on_new.setStyleSheet(f"color: {color}")
            self.label_use_function_calling.setStyleSheet(f"color: {color}")
            self.label_use_validator.setStyleSheet(f"color: {color}")

        def toggle_function_calling_type_visibility(self):
            self.function_calling_mode.setVisible(self.use_function_calling.isChecked())

    class Page_Group_Settings(ConfigPageWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.namespace = 'group'
            self.label_width = 175
            self.schema = [
                {
                    'text': 'Hide responses',
                    'type': bool,
                    'default': False,
                },
                {
                    'text': 'Output context placeholder',
                    'type': str,
                    'default': '',
                },
                {
                    'text': 'On multiple inputs',
                    'type': ('Append to system msg', 'Merged user message', 'Reply individually'),
                    'default': 'Merged user message',
                },
                {
                    'text': 'Show members as user role',
                    'type': bool,
                    'default': True,
                },
            ]
            # self.form_layout = QFormLayout(self)
            #
            # self.label_hide_responses = QLabel('Hide responses:')
            # self.label_output_context_placeholder = QLabel('Output context placeholder:')
            #
            # self.hide_responses = QCheckBox()
            # self.form_layout.addRow(self.label_hide_responses, self.hide_responses)
            #
            # self.output_context_placeholder = QLineEdit()
            # self.form_layout.addRow(self.label_output_context_placeholder, self.output_context_placeholder)
            #
            # self.on_multiple_inputs = CComboBox()
            # self.on_multiple_inputs.setFixedWidth(170)
            # self.on_multiple_inputs.addItems(['Append to system msg', 'Merged user message', 'Reply individually'])
            # self.form_layout.addRow(QLabel('On multiple inputs:'), self.on_multiple_inputs)
            #
            # # add checkbox for 'Show members as user role
            # self.set_members_as_user_role = QCheckBox()
            # self.form_layout.addRow(QLabel('Show members as user role:'), self.set_members_as_user_role)
            #
            # self.hide_responses.stateChanged.connect(parent.update_agent_config)
            # self.output_context_placeholder.textChanged.connect(parent.update_agent_config)
            # self.on_multiple_inputs.currentIndexChanged.connect(parent.update_agent_config)
            # self.set_members_as_user_role.stateChanged.connect(parent.update_agent_config)

        def load(self):
            pass
            # parent = self.parent
            # with block_signals(self):
            #     self.hide_responses.setChecked(parent.agent_config.get('group.hide_responses', False))
            #     self.output_context_placeholder.setText(
            #         str(parent.agent_config.get('group.output_context_placeholder', '')))
            #     self.on_multiple_inputs.setCurrentText(
            #         parent.agent_config.get('group.on_multiple_inputs', 'Use system message'))
            #     self.set_members_as_user_role.setChecked(
            #         parent.agent_config.get('group.set_members_as_user_role', True))

    class Page_Voice_Settings(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.layout = QVBoxLayout(self)

            # Search panel setup
            self.search_panel = QWidget(self)
            self.search_layout = QHBoxLayout(self.search_panel)
            self.api_dropdown = APIComboBox(self, first_item='ALL')
            self.search_field = QLineEdit(self)
            self.search_layout.addWidget(QLabel("API:"))
            self.search_layout.addWidget(self.api_dropdown)
            self.search_layout.addWidget(QLabel("Search:"))
            self.search_layout.addWidget(self.search_field)
            self.layout.addWidget(self.search_panel)

            self.table = BaseTableWidget(self)

            # Creating a new QWidget to hold the buttons
            self.buttons_panel = QWidget(self)
            self.buttons_layout = QHBoxLayout(self.buttons_panel)
            self.buttons_layout.setAlignment(Qt.AlignRight)

            # Set as voice button
            self.set_voice_button = QPushButton("Set as voice", self)
            self.set_voice_button.setFixedWidth(150)

            # Test voice button
            self.test_voice_button = QPushButton("Test voice", self)
            self.test_voice_button.setFixedWidth(150)

            # Adding buttons to the layout
            self.buttons_layout.addWidget(self.set_voice_button)
            self.buttons_layout.addWidget(self.test_voice_button)
            self.layout.addWidget(self.table)
            self.layout.addWidget(self.buttons_panel)

            self.set_voice_button.clicked.connect(self.set_as_voice)
            self.test_voice_button.clicked.connect(self.test_voice)

            self.api_dropdown.currentIndexChanged.connect(self.filter_table)
            self.search_field.textChanged.connect(self.filter_table)

            self.load_data_from_db()
            self.current_id = 0

        def load(self):  # Load Voices
            # Database fetch and display
            with block_signals(self):
                # self.load_apis()
                self.current_id = self.parent.agent_config.get('voice.current_id', 0)
                self.highlight_and_select_current_voice()

        def load_data_from_db(self):
            # Fetch all voices initially
            self.all_voices, self.col_names = sql.get_results("""
                SELECT
                    v.`id`,
                    a.`name` AS api_id,
                    v.`display_name`,
                    v.`known_from`,
                    v.`uuid`,
                    v.`added_on`,
                    v.`updated_on`,
                    v.`rating`,
                    v.`creator`,
                    v.`lang`,
                    v.`deleted`,
                    v.`fav`,
                    v.`full_in_prompt`,
                    v.`verb`,
                    v.`add_prompt`
                FROM `voices` v
                LEFT JOIN apis a
                    ON v.api_id = a.id""", incl_column_names=True)

            self.display_data_in_table(self.all_voices)

        def highlight_and_select_current_voice(self):
            for row_index in range(self.table.rowCount()):
                item_id = int(self.table.item(row_index, 0).text())
                is_current = (item_id == self.current_id)

                for col_index in range(self.table.columnCount()):
                    item = self.table.item(row_index, col_index)
                    bg_col = QColor("#33ffffff") if is_current else QColor("#00ffffff")
                    item.setBackground(bg_col)

                if is_current:
                    self.table.selectRow(row_index)
                    self.table.scrollToItem(self.table.item(row_index, 0))

        def filter_table(self):
            api_name = self.api_dropdown.currentText().lower()
            search_text = self.search_field.text().lower()

            # Define the filtering criteria as a function
            def matches_filter(voice):
                name, known_from = voice[2].lower(), voice[3].lower()
                return (api_name == 'all' or api_name in name) and (
                        search_text in name or search_text in known_from)

            filtered_voices = filter(matches_filter, self.all_voices)
            self.display_data_in_table(list(filtered_voices))

        def display_data_in_table(self, voices):
            # Add a row for each voice
            self.table.setRowCount(len(voices))
            # Add an extra column for the play buttons
            self.table.setColumnCount(len(voices[0]) if voices else 0)
            # Add a header for the new play button column
            self.table.setHorizontalHeaderLabels(self.col_names)
            self.table.hideColumn(0)

            for row_index, row_data in enumerate(voices):
                for col_index, cell_data in enumerate(row_data):  # row_data is a tuple, not a dict
                    self.table.setItem(row_index, col_index, QTableWidgetItem(str(cell_data)))

        def set_as_voice(self):
            current_row = self.table.currentRow()
            if current_row == -1:
                QMessageBox.warning(self, "Selection Error", "Please select a voice from the table!")
                return

            new_voice_id = int(self.table.item(current_row, 0).text())
            if new_voice_id == self.current_id:
                new_voice_id = 0
            self.current_id = new_voice_id
            self.parent.update_agent_config()  # 'voice.current_id', voice_id)
            # self.parent.main.page_chat.load()
            # self.load()
            # self.parent.update_agent_config()
            # Further actions can be taken using voice_id or the data of the selected row
            # QMessageBox.information(self, "Voice Set", f"Voice with ID {self.current_id} has been set!")

        def test_voice(self):
            # todo - Implement functionality to test the voice
            pass
