
from PySide6.QtWidgets import *
from agentpilot.gui.components.config import ConfigTree
from agentpilot.gui.widgets.base import ContentPage


class Page_Contexts(ContentPage):
    def __init__(self, main):
        super().__init__(main=main, title='Chats')
        self.tree_config = ConfigTree(
            parent=self,
            db_table='contexts',
            query="""
                SELECT
                    c.summary,
                    c.id,
                    CASE WHEN COUNT(a.name) > 1 THEN
                        CAST(COUNT(a.name) AS TEXT) || ' members'
                    ELSE
                        MAX(a.name)
                    END as name,
                    group_concat(json_extract(a.config, '$."info.avatar_path"'), ';') as avatar_paths,
                    '' AS goto_button
                FROM contexts c
                LEFT JOIN contexts_members cm
                    ON c.id = cm.context_id
                    AND cm.del != 1
                LEFT JOIN agents a
                    ON cm.agent_id = a.id
                LEFT JOIN (
                    SELECT
                        context_id,
                        MAX(id) as latest_message_id
                    FROM contexts_messages
                    GROUP BY context_id
                ) cmsg ON c.id = cmsg.context_id
                WHERE c.parent_id IS NULL
                GROUP BY c.id
                ORDER BY
                    COALESCE(cmsg.latest_message_id, 0) DESC, 
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
            del_item_prompt=('Delete Context', 'Are you sure you want to permanently delete this context?'),
            layout_type=QVBoxLayout,
            config_widget=None,
            has_config_field=False,
            tree_width=600,
            tree_height=590,
            tree_header_hidden=True,
            init_select=False,
            filterable=True,
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

    def on_chat_btn_clicked(self, _):
        context_id = self.tree_config.get_current_id()
        if not context_id:
            return
        self.chat_with_context(context_id)

    def chat_with_context(self, context_id):
        if self.main.page_chat.workflow.responding:
            return
        self.main.page_chat.goto_context(context_id=context_id)
        self.main.content.setCurrentWidget(self.main.page_chat)
        self.main.sidebar.btn_new_context.setChecked(True)
