
from functools import partial
from PySide6.QtWidgets import *
from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon, Qt

from agentpilot.utils.helpers import display_messagebox, block_signals
from agentpilot.utils import sql

import logging

from agentpilot.gui.components.config import ConfigTreeWidget
from agentpilot.gui.widgets.base import BaseTreeWidget, ContentPage


class Page_Contexts(ContentPage):
    def __init__(self, main):
        super().__init__(main=main, title='Contexts')
        self.main = main
        self.tree_config = ConfigTreeWidget(
            parent=self,
            db_table='contexts',
            query="""
                SELECT
                    c.summary,
                    c.id,
                    group_concat(a.name, ' + ') as name,
                    group_concat(json_extract(a.config, '$."general.avatar_path"'), ';') as avatar_paths,
                    '' AS goto_button
                FROM contexts c
                LEFT JOIN contexts_members cp
                    ON c.id = cp.context_id
                LEFT JOIN agents a
                    ON cp.agent_id = a.id
                LEFT JOIN (
                    SELECT
                        context_id,
                        MAX(id) as latest_message_id
                    FROM contexts_messages
                    GROUP BY context_id
                ) cm ON c.id = cm.context_id
                WHERE c.parent_id IS NULL
                GROUP BY c.id
                ORDER BY
                    COALESCE(cm.latest_message_id, 0) DESC, 
                    c.id DESC;""",
            schema=[
                {
                    'text': 'summary',
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
                    'text': 'Name',
                    'key': 'name',
                    'type': str,
                    'width': 125,
                },
                {
                    'key': 'avatar',
                    'text': '',
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
            add_item_prompt=None,
            del_item_prompt=('Delete Context', 'Are you sure you want to delete this context?'),
            layout_type=QVBoxLayout,
            config_widget=None,
            has_config_field=False,
            tree_width=600,
            tree_header_hidden=True,
        )
        self.tree_config.build_schema()

        self.tree_config.tree.itemDoubleClicked.connect(self.on_row_double_clicked)

        self.layout.addWidget(self.tree_config)
        self.layout.addStretch(1)

    def load(self):
        self.tree_config.load()

    def on_row_double_clicked(self):
        context_id = self.tree_config.get_current_id()
        if not context_id:
            return
        self.chat_with_context(context_id)

    def on_chat_btn_clicked(self, row_data):
        id_value = row_data[0]  # self.table_widget.item(row_item, 0).text()
        self.chat_with_context(id_value)

    def chat_with_context(self, context_id):
        if self.main.page_chat.workflow.responding:
            return
        self.main.page_chat.goto_context(context_id=context_id)
        self.main.content.setCurrentWidget(self.main.page_chat)
        self.main.sidebar.btn_new_context.setChecked(True)
