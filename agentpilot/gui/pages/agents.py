
import json
import sqlite3

from PySide6.QtWidgets import *

from agentpilot.utils.helpers import display_messagebox
from agentpilot.utils import sql

from agentpilot.gui.components.agent_settings import AgentSettings
from agentpilot.gui.components.config import ConfigTree
from agentpilot.gui.widgets.base import ContentPage


class Page_Agents(ContentPage):
    def __init__(self, main):
        super().__init__(main=main, title='Agents')
        self.main = main
        self.tree_config = ConfigTree(
            parent=self,
            db_table='agents',
            db_config_field='config',
            query="""
                SELECT
                    COALESCE(json_extract(config, '$."info.name"'), name) AS name,
                    id,
                    json_extract(config, '$."info.avatar_path"') AS avatar,
                    config,
                    '' AS chat_button,
                    folder_id
                FROM agents
                ORDER BY ordr""",
            schema=[
                {
                    'text': 'Name',
                    'key': 'name',
                    'type': str,
                    'stretch': True,
                    'image_key': 'avatar',
                },
                {
                    'text': 'id',
                    'key': 'id',
                    'type': int,
                    'visible': False,
                },
                {
                    'key': 'avatar',
                    'text': '',
                    'type': str,
                    'visible': False,
                },
                {
                    'text': 'Config',
                    'type': str,
                    'visible': False,
                },
                {
                    'text': '',
                    'type': QPushButton,
                    'icon': ':/resources/icon-chat.png',
                    'func': self.on_chat_btn_clicked,
                    'width': 45,
                },
            ],
            add_item_prompt=('Add Agent', 'Enter a name for the agent:'),
            del_item_prompt=('Delete Agent', 'Are you sure you want to delete this agent?'),
            layout_type=QVBoxLayout,
            config_widget=self.Agent_Config_Widget(parent=self),
            tree_width=600,
            tree_header_hidden=True,
            folder_key='agents'
        )
        self.tree_config.tree.setSortingEnabled(False)
        # self.tree_config = TreeConfig(self)
        self.tree_config.build_schema()

        self.tree_config.tree.itemDoubleClicked.connect(self.on_row_double_clicked)

        self.layout.addWidget(self.tree_config)
        self.layout.addStretch(1)

    def load(self):
        self.tree_config.load()

    class Agent_Config_Widget(AgentSettings):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent

        def save_config(self):
            """Saves the config to database when modified"""
            if self.ref_id is None:
                return
            json_config_dict = self.get_config()
            json_config = json.dumps(json_config_dict)
            name = json_config_dict.get('info.name', 'Assistant')
            try:
                sql.execute("UPDATE agents SET config = ?, name = ? WHERE id = ?", (json_config, name, self.ref_id))
            except sqlite3.IntegrityError as e:
                display_messagebox(
                    icon=QMessageBox.Warning,
                    title='Error',
                    text='Name already exists',
                )
                return
            self.load_config(json_config)  # todo needed for configjsontree, but why
            self.settings_sidebar.load()

    def on_row_double_clicked(self):
        agent_id = self.tree_config.get_current_id()
        if not agent_id:
            return

        self.chat_with_agent(agent_id)

    def on_chat_btn_clicked(self, row_data):
        agent_id = self.tree_config.get_current_id()
        if not agent_id:
            return
        self.chat_with_agent(agent_id)

    def chat_with_agent(self, agent_id):
        if self.main.page_chat.workflow.responding:
            return
        self.main.page_chat.new_context(agent_id=agent_id)
        self.main.sidebar.btn_new_context.click()


# class TreeConfig(ConfigTree):
#     def __init__(self, parent):
#         super().__init__(
#             parent=parent,
#             db_table='agents',
#             db_config_field='config',
#             query="""
#                 SELECT
#                     COALESCE(json_extract(config, '$."general.name"'), name) AS name,
#                     id,
#                     json_extract(config, '$."info.avatar_path"') AS avatar,
#                     config,
#                     '' AS chat_button,
#                     folder_id
#                 FROM agents
#                 ORDER BY id DESC""",
#             schema=[
#                 {
#                     'text': 'Name',
#                     'key': 'name',
#                     'type': str,
#                     'stretch': True,
#                     'image_key': 'avatar',
#                 },
#                 {
#                     'text': 'id',
#                     'key': 'id',
#                     'type': int,
#                     'visible': False,
#                     # 'visible': False,
#                     # 'readonly': True,
#                 },
#                 {
#                     'key': 'avatar',
#                     'text': '',
#                     'type': str,
#                     'visible': False,
#                 },
#                 {
#                     'text': 'Config',
#                     'type': str,
#                     'visible': False,
#                 },
#                 {
#                     'text': '',
#                     'type': QPushButton,
#                     'icon': ':/resources/icon-chat.png',
#                     'func': self.on_chat_btn_clicked,
#                     'width': 45,
#                 },
#             ],
#             add_item_prompt=('Add Agent', 'Enter a name for the agent:'),
#             del_item_prompt=('Delete Agent', 'Are you sure you want to delete this agent?'),
#             layout_type=QVBoxLayout,
#             config_widget=self.Agent_Config_Widget(parent=self),
#             tree_width=600,
#             tree_header_hidden=True,
#             folder_key='agents'
#         )
