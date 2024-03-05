import json
from abc import abstractmethod

from PySide6.QtWidgets import *
from PySide6.QtGui import QColor, Qt

from src.utils.helpers import display_messagebox, block_signals
from src.utils import sql

from src.gui.components.config import ConfigPages, ConfigFields, ConfigTabs, ConfigJsonTree, ConfigTree, \
    ConfigJoined, ConfigJsonFileTree, ConfigPlugin, ConfigJsonToolTree  # , ConfigJsonFileTree
from src.gui.widgets.base import APIComboBox, BaseTableWidget, IconButton


def find_main_widget(widget):
    if hasattr(widget, 'main'):
        return widget.main
    if not hasattr(widget, 'parent'):
        return None
    return find_main_widget(widget.parent)


class AgentSettings(ConfigPages):
    def __init__(self, parent, is_context_member_agent=False):
        super().__init__(parent=parent)
        # self.parent = parent
        self.main = find_main_widget(parent)
        self.is_context_member_agent = is_context_member_agent
        self.ref_id = None
        self.layout.addSpacing(10)

        self.pages = {
            'Info': self.Info_Settings(self),
            'Chat': self.Chat_Settings(self),
            'Files': self.File_Settings(self),
            'Tools': self.Tool_Settings(self),
            # 'Voice': self.Voice_Settings(self),
        }
        # self.build_schema()

    @abstractmethod
    def save_config(self):
        """Saves the config to database when modified"""
        pass
        # # # todo - ignore instance keys
        # item = self.parent.tree_config.tree.currentItem()
        # if not item:
        #     return False
        #
        # id = int(item.text(0))
        # json_config = json.dumps(self.config)
        # if self.is_context_member_agent:
        #     sql.execute("UPDATE contexts_members SET agent_config = ? WHERE id = ?", (json_config, self.agent_id))
        #     self.main.page_chat.workflow.load_members()
        #     self.settings_sidebar.load()
        # else:
        #     pass  # Now overridden
        #     # name = self.config.get('general.name', 'Assistant')
        #     # sql.execute("UPDATE agents SET config = ?, name = ? WHERE id = ?", (json_config, name, self.agent_id))
        #     # self.settings_sidebar.load()

    class ConfigSidebarWidget(ConfigPages.ConfigSidebarWidget):
        def __init__(self, parent):
            super().__init__(parent=parent, width=75)
            self.parent = parent

            self.button_layout = QHBoxLayout()
            self.button_layout.addStretch(1)

            self.btn_pull = IconButton(self, icon_path=':/resources/icon-pull.png', colorize=False)
            self.btn_pull.setToolTip("Set member config to agent default")
            self.btn_pull.clicked.connect(self.pull_member_config)
            self.button_layout.addWidget(self.btn_pull)

            self.btn_push = IconButton(self, icon_path=':/resources/icon-push.png', colorize=False)
            self.btn_push.setToolTip("Set all member configs to agent default")
            self.btn_push.clicked.connect(self.push_member_config)
            self.button_layout.addWidget(self.btn_push)

            self.button_layout.addStretch(1)

            self.warning_label = QLabel("A plugin is enabled, these settings may not work as expected")
            self.warning_label.setFixedWidth(75)
            self.warning_label.setWordWrap(True)
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
                member_id = self.parent.ref_id
                default_config_str = sql.get_scalar("SELECT config FROM agents WHERE id = (SELECT agent_id FROM contexts_members WHERE id = ?)", (member_id,))
                if default_config_str is None:
                    default_config = {}
                else:
                    default_config = json.loads(default_config_str)
                member_config = self.parent.config
                # todo dirty
                # remove instance keys
                member_config = {key: value for key, value in member_config.items() if not key.startswith('instance.')}
                config_mismatch = default_config != member_config

                self.btn_pull.setVisible(config_mismatch)
            else:
                self.btn_pull.hide()
                # only called from a member config settings:
                # if any context member config is not the same as agent config default, then show
                default_config = self.parent.config
                member_configs = sql.get_results("SELECT agent_config FROM contexts_members WHERE agent_id = ?",
                                                 (self.parent.ref_id,), return_type='list')
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
            default_config = sql.get_scalar("SELECT config FROM agents WHERE id = (SELECT agent_id FROM contexts_members WHERE id = ?)", (self.parent.ref_id,))
            sql.execute("UPDATE contexts_members SET agent_config = ? WHERE id = ?", (default_config, self.parent.ref_id))
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
            default_config = self.parent.config
            sql.execute("UPDATE contexts_members SET agent_config = ? WHERE agent_id = ?", (json.dumps(default_config), self.parent.ref_id))
            self.load()

        def onButtonToggled(self, button, checked):
            if checked:
                index = self.button_group.id(button)
                self.parent.content.setCurrentIndex(index)
                self.parent.content.currentWidget().load()
                self.refresh_warning_label()

        def refresh_warning_label(self):
            index = self.parent.content.currentIndex()
            show_plugin_warning = index > 0 and self.parent.config.get('info.use_plugin', '') != ''
            if show_plugin_warning:
                self.warning_label.show()
            else:
                self.warning_label.hide()

    class Info_Settings(ConfigJoined):
        def __init__(self, parent):
            super().__init__(parent=parent, layout_type=QVBoxLayout)
            self.widgets = [
                self.Info_Fields(parent=self),
                self.Info_Plugin(parent=self),
            ]
            self.layout.setAlignment(Qt.AlignHCenter)

        class Info_Fields(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.parent = parent
                self.namespace = 'info'
                self.alignment = Qt.AlignCenter
                self.schema = [
                    {
                        'text': 'Avatar',
                        'key': 'avatar_path',
                        'type': 'CircularImageLabel',
                        'default': '',
                        'label_position': None,
                    },
                    {
                        'text': 'Name',
                        'type': str,
                        'default': 'Assistant',
                        'width': 400,
                        'text_size': 15,
                        'text_alignment': Qt.AlignCenter,
                        'label_position': None,
                        'transparent': True,
                        'fill_width': True,
                    },
                ]

        class Info_Plugin(ConfigPlugin):
            def __init__(self, parent):
                super().__init__(parent=parent, plugin_type='Agent')
                self.parent = parent
                # self.namespace = 'plugin'
                self.default = ''

    class Chat_Settings(ConfigTabs):
        def __init__(self, parent):
            super().__init__(parent=parent)

            self.pages = {
                'Messages': self.Page_Chat_Messages(parent=self),
                'Preload': self.Page_Chat_Preload(parent=self),
                'Group': self.Page_Chat_Group(parent=self),
            }

        class Page_Chat_Messages(ConfigFields):
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
                        'text': 'Display markdown',
                        'type': bool,
                        'default': True,
                        'row_key': 0,
                    },
                    {
                        'text': 'System message',
                        'key': 'sys_msg',
                        'type': str,
                        'num_lines': 8,
                        'default': '',
                        'width': 520,
                        'label_position': 'top',
                    },
                    {
                        'text': 'Max messages',
                        'type': int,
                        'default': 8,
                        'width': 60,
                        'row_key': 1,
                    },
                    {
                        'text': 'Max turns',
                        'type': int,
                        'default': 5,
                        'width': 60,
                        'row_key': 1,
                    },
                    {
                        'text': 'Consecutive responses',
                        'key': 'on_consecutive_response',
                        'type': ('PAD', 'REPLACE', 'NOTHING'),
                        'default': 'REPLACE',
                        'width': 90,
                        'row_key': 2,
                    },
                    {
                        'text': 'User message',
                        'key': 'user_msg',
                        'type': str,
                        'num_lines': 2,
                        'default': '',
                        'width': 520,
                        'label_position': 'top',
                        'tooltip': 'Text to override the user/input message. When empty, the default user/input message is used.',
                    },
                ]

        class Page_Chat_Preload(ConfigJsonTree):
            def __init__(self, parent):
                super().__init__(parent=parent,
                                 add_item_prompt=('NA', 'NA'),
                                 del_item_prompt=('NA', 'NA'))
                self.parent = parent
                self.namespace = 'chat.preload'
                self.schema = [
                    {
                        'text': 'Role',
                        'type': 'RoleComboBox',
                        'width': 120,
                        'default': 'assistant',
                    },
                    {
                        'text': 'Content',
                        'type': str,
                        'stretch': True,
                        'default': '',
                    },
                    {
                        'text': 'Freeze',
                        'type': bool,
                        'default': True,
                    },
                    {
                        'text': 'Visible',
                        'type': bool,
                        'default': False,
                    },
                ]

            # def add_item(self):
            #     """Overrides the ConfigTree's add_item method"""
            #     pass
            #
            # def delete_item(self):
            #     """Overrides the ConfigTree's delete_item method"""
            #     pass

        class Page_Chat_Group(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.parent = parent
                self.namespace = 'group'
                self.label_width = 175
                self.schema = [
                    {
                        'text': 'Hide responses',
                        'type': bool,
                        'tooltip': 'When checked, the responses from this member will not be shown in the chat',
                        'default': False,
                    },
                    {
                        'text': 'Output placeholder',
                        'type': str,
                        'tooltip': 'A tag to refer to this member\'s output from other members system messages',
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
                    {
                        'text': 'Member description',
                        'key': 'sys_msg',
                        'type': str,
                        'num_lines': 4,
                        'width': 320,
                        'tooltip': 'A description of the member that can be used by other members',
                        'default': '',
                        # 'label_position': 'top',
                    }
                ]

    class File_Settings(ConfigJsonFileTree):
        def __init__(self, parent):
            super().__init__(parent=parent,
                             add_item_prompt=('NA', 'NA'),
                             del_item_prompt=('NA', 'NA'),
                             tree_header_hidden=True,
                             readonly=True)
            self.parent = parent
            self.namespace = 'files'
            self.schema = [
                {
                    'text': 'Filename',
                    'type': str,
                    'width': 175,
                    'default': '',
                },
                {
                    'text': 'Location',
                    'type': str,
                    # 'visible': False,
                    'stretch': True,
                    'default': '',
                },
            ]

    class Tool_Settings(ConfigJsonToolTree):
        def __init__(self, parent):
            super().__init__(parent=parent,
                             add_item_prompt=('NA', 'NA'),
                             del_item_prompt=('NA', 'NA'),
                             tree_header_hidden=True,
                             readonly=True)
            self.parent = parent
            self.namespace = 'tools'
            self.schema = [
                {
                    'text': 'Tool',
                    'type': str,
                    'width': 175,
                    'default': '',
                },
                {
                    'text': 'id',
                    'visible': False,
                    'default': '',
                },
            ]

    # class Tool_Settings(ConfigJoined):
    #     def __init__(self, parent):
    #         super().__init__(parent=parent, layout_type=QHBoxLayout)
    #         self.widgets = [
    #             self.Tool_Json_Tree(parent=self),
    #             self.Tool_Prompt(parent=self),
    #         ]
    #
    #     class Tool_Json_Tree(ConfigJsonTree):
    #         def __init__(self, parent):
    #             super().__init__(parent=parent)
    #             self.parent = parent
    #             self.namespace = 'tools'
    #
    #     # class Tool_Prompt(ConfigFields):
    #     #     def __init__(self, parent):
    #     #         super().__init__(parent=parent)
    #     #         self.namespace = 'prompt'
    #     #         self.schema = [
    #     #             {
    #     #                 'text': 'Prompt',
    #     #                 'key': 'model',
    #     #                 'type': 'ModelComboBox',
    #     #                 'default': 'gpt-3.5-turbo',
    #     #             },
    #     #             {
    #     #                 'text': 'Prompt',
    #     #                 'type': str,
    #     #                 'width': 300,
    #     #                 'num_lines': 15,
    #     #                 'label_position': None,
    #     #                 'default': '',
    #     #             },
    #     #         ]

    # class File_Settings(ConfigJsonTree):
    #     def __init__(self, parent):
    #         super().__init__(parent=parent, layout_type=QHBoxLayout)
    #         self.widgets = []

    # class Voice_Settings(ConfigFields):
    #     def __init__(self, parent):
    #         super().__init__(parent=parent)
    #         self.parent = parent
    #         self.namespace = 'voice'
    #         # self.layout = QVBoxLayout(self)
    #
    #         # Search panel setup
    #         self.search_panel = QWidget(self)
    #         self.search_layout = QHBoxLayout(self.search_panel)
    #         self.api_dropdown = APIComboBox(self, first_item='ALL')
    #         self.search_field = QLineEdit(self)
    #         self.search_layout.addWidget(QLabel("API:"))
    #         self.search_layout.addWidget(self.api_dropdown)
    #         self.search_layout.addWidget(QLabel("Search:"))
    #         self.search_layout.addWidget(self.search_field)
    #         self.layout.addWidget(self.search_panel)
    #
    #         self.table = BaseTableWidget(self)
    #
    #         # Creating a new QWidget to hold the buttons
    #         self.buttons_panel = QWidget(self)
    #         self.buttons_layout = QHBoxLayout(self.buttons_panel)
    #         self.buttons_layout.setAlignment(Qt.AlignRight)
    #
    #         # Set as voice button
    #         self.set_voice_button = QPushButton("Set as voice", self)
    #         self.set_voice_button.setFixedWidth(150)
    #
    #         # Test voice button
    #         self.test_voice_button = QPushButton("Test voice", self)
    #         self.test_voice_button.setFixedWidth(150)
    #
    #         # Adding buttons to the layout
    #         self.buttons_layout.addWidget(self.set_voice_button)
    #         self.buttons_layout.addWidget(self.test_voice_button)
    #         self.layout.addWidget(self.table)
    #         self.layout.addWidget(self.buttons_panel)
    #
    #         self.set_voice_button.clicked.connect(self.set_as_voice)
    #         self.test_voice_button.clicked.connect(self.test_voice)
    #
    #         self.api_dropdown.currentIndexChanged.connect(self.filter_table)
    #         self.search_field.textChanged.connect(self.filter_table)
    #
    #         self.load_data_from_db()
    #         self.current_id = 0
    #
    #     def load(self):  # Load Voices
    #         # Database fetch and display
    #         with block_signals(self):
    #             # self.load_apis()
    #             self.current_id = self.parent.config.get('voice.current_id', 0)
    #             self.highlight_and_select_current_voice()
    #
    #     def load_data_from_db(self):
    #         # Fetch all voices initially
    #         self.all_voices, self.col_names = sql.get_results("""
    #             SELECT
    #                 v.`id`,
    #                 a.`name` AS api_id,
    #                 v.`display_name`,
    #                 v.`known_from`,
    #                 v.`uuid`,
    #                 v.`added_on`,
    #                 v.`updated_on`,
    #                 v.`rating`,
    #                 v.`creator`,
    #                 v.`lang`,
    #                 v.`deleted`,
    #                 v.`fav`,
    #                 v.`full_in_prompt`,
    #                 v.`verb`,
    #                 v.`add_prompt`
    #             FROM `voices` v
    #             LEFT JOIN apis a
    #                 ON v.api_id = a.id""", incl_column_names=True)
    #
    #         self.display_data_in_table(self.all_voices)
    #
    #     def highlight_and_select_current_voice(self):
    #         for row_index in range(self.table.rowCount()):
    #             item_id = int(self.table.item(row_index, 0).text())
    #             is_current = (item_id == self.current_id)
    #
    #             for col_index in range(self.table.columnCount()):
    #                 item = self.table.item(row_index, col_index)
    #                 bg_col = QColor("#33ffffff") if is_current else QColor("#00ffffff")
    #                 item.setBackground(bg_col)
    #
    #             if is_current:
    #                 self.table.selectRow(row_index)
    #                 self.table.scrollToItem(self.table.item(row_index, 0))
    #
    #     def filter_table(self):
    #         api_name = self.api_dropdown.currentText().lower()
    #         search_text = self.search_field.text().lower()
    #
    #         # Define the filtering criteria as a function
    #         def matches_filter(voice):
    #             name, known_from = voice[2].lower(), voice[3].lower()
    #             return (api_name == 'all' or api_name in name) and (
    #                     search_text in name or search_text in known_from)
    #
    #         filtered_voices = filter(matches_filter, self.all_voices)
    #         self.display_data_in_table(list(filtered_voices))
    #
    #     def display_data_in_table(self, voices):
    #         # Add a row for each voice
    #         self.table.setRowCount(len(voices))
    #         # Add an extra column for the play buttons
    #         self.table.setColumnCount(len(voices[0]) if voices else 0)
    #         # Add a header for the new play button column
    #         self.table.setHorizontalHeaderLabels(self.col_names)
    #         self.table.hideColumn(0)
    #
    #         for row_index, row_data in enumerate(voices):
    #             for col_index, cell_data in enumerate(row_data):  # row_data is a tuple, not a dict
    #                 self.table.setItem(row_index, col_index, QTableWidgetItem(str(cell_data)))
    #
    #     def set_as_voice(self):
    #         current_row = self.table.currentRow()
    #         if current_row == -1:
    #             QMessageBox.warning(self, "Selection Error", "Please select a voice from the table!")
    #             return
    #
    #         new_voice_id = int(self.table.item(current_row, 0).text())
    #         if new_voice_id == self.current_id:
    #             new_voice_id = 0
    #         self.current_id = new_voice_id
    #         self.parent.update_agent_config()  # 'voice.current_id', voice_id)
    #         # self.parent.main.page_chat.load()
    #         # self.load()
    #         # self.parent.update_agent_config()
    #         # Further actions can be taken using voice_id or the data of the selected row
    #         # QMessageBox.information(self, "Voice Set", f"Voice with ID {self.current_id} has been set!")
    #
    #     def test_voice(self):
    #         # todo - Implement functionality to test the voice
    #         pass
