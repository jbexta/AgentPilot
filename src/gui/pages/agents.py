
import json
import sqlite3

from PySide6.QtWidgets import *

from src.utils.helpers import display_messagebox
from src.utils import sql

from src.members.workflow import WorkflowSettings
from src.gui.config import ConfigDBTree
from src.gui.widgets import find_main_widget


class Page_Entities(ConfigDBTree):
    def __init__(self, parent):
        super().__init__(
            parent=parent,
            db_table='entities',
            query="""
                SELECT
                    COALESCE(json_extract(config, '$."info.name"'), name) AS name,
                    id,
                    CASE
                        WHEN json_extract(config, '$._TYPE') = 'workflow' THEN
                            COALESCE(
                                (
                                    SELECT GROUP_CONCAT(COALESCE(json_extract(m.value, '$.config."info.avatar_path"'), ''), '//##//##//')
                                    FROM json_each(json_extract(config, '$.members')) m
                                    WHERE COALESCE(json_extract(m.value, '$.del'), 0) = 0
                                ),
                                ''
                            )
                        ELSE
                            COALESCE(json_extract(config, '$."info.avatar_path"'), '')
                    END AS avatar,
                    config,
                    '' AS chat_button,
                    folder_id
                FROM entities
                WHERE kind = "{{kind}}"
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
                    'text': 'config',
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
            kind='AGENT',
            # kind_list=['AGENT', 'CONTACT'],
            add_item_prompt=('Add Agent', 'Enter a name for the agent:'),
            del_item_prompt=('Delete Agent', 'Are you sure you want to delete this agent?'),
            layout_type=QVBoxLayout,
            config_widget=self.Entity_Config_Widget(parent=self),
            # tree_width=600,
            # tree_height=250,
            tree_header_hidden=True,
            folder_key='agents',
            filterable=True,
            searchable=True
        )
        self.icon_path = ":/resources/icon-agent.png"
        self.tree.itemDoubleClicked.connect(self.on_row_double_clicked)
        self.try_add_breadcrumb_widget(root_title='Agents')

    def load(self, select_id=None, silent_select_id=None, append=False):
        self.config_widget.set_edit_mode(False)
        super().load(select_id, silent_select_id, append)

    def on_row_double_clicked(self):
        agent_id = self.get_selected_item_id()
        if not agent_id:
            return

        self.chat_with_agent(agent_id)

    def on_chat_btn_clicked(self, row_data):
        agent_id = self.get_selected_item_id()
        if not agent_id:
            return
        self.chat_with_agent(agent_id)

    def chat_with_agent(self, agent_id):
        main = find_main_widget(self)
        if main.page_chat.workflow.responding:
            return
        main.page_chat.new_context(entity_id=agent_id)
        main.page_chat.ensure_visible()

    def explore(self):
        print('explore')
        pass

    class Entity_Config_Widget(WorkflowSettings):
        def __init__(self, parent):
            super().__init__(parent=parent,
                             compact_mode=True)

        def save_config(self):
            """Saves the config to database when modified"""
            json_config_dict = self.get_config()
            json_config = json.dumps(json_config_dict)

            entity_id = self.parent.get_selected_item_id()
            if not entity_id:
                raise NotImplementedError()

            try:
                sql.execute("UPDATE entities SET config = ? WHERE id = ?", (json_config, entity_id))
            except sqlite3.IntegrityError as e:
                display_messagebox(
                    icon=QMessageBox.Warning,
                    title='Error',
                    text='Name already exists',
                )  # todo

            self.load_config(json_config)  # reload config
            self.parent.reload_current_row()

# class Page_Explore(QWidget):
#     def __init__(self, parent):
#         super().__init__(parent=parent)
#         self.layout = CVBoxLayout(self)
#
#     def load(self):
#         pass