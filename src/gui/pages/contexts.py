
from PySide6.QtWidgets import *
from src.gui.config import ConfigDBTree
from src.gui.widgets import ContentPage


class Page_Contexts(ContentPage):
    def __init__(self, main):
        super().__init__(main=main, title='Chats')
        self.tree_config = ConfigDBTree(
            parent=self,
            db_table='contexts',
            query="""
                SELECT
                    c.summary,
                    c.id,
                    CASE
                        WHEN json_extract(c.config, '$.members') IS NOT NULL THEN
                            CASE
                                WHEN json_array_length(json_extract(c.config, '$.members')) = 2 THEN
                                    json_extract(json_extract(c.config, '$.members'), '$[1].config."info.name"')
                                ELSE
                                    json_array_length(json_extract(c.config, '$.members')) || ' members'
                            END
                        ELSE '0 members'
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
                    '' AS goto_button,
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
                GROUP BY c.id
                ORDER BY
                    COALESCE(cmsg.latest_message_id, 0) DESC
                LIMIT ? OFFSET ?;
                """,
            # query="""
            #     SELECT
            #         c.summary,
            #         c.id,
            #         CASE WHEN COUNT(a.name) > 1 THEN
            #             CAST(COUNT(a.name) AS TEXT) || ' members'
            #         ELSE
            #             MAX(a.name)
            #         END as name,
            #         group_concat(json_extract(a.config, '$."info.avatar_path"'), ';') as avatar_paths,
            #         '' AS goto_button,
            #         c.folder_id
            #     FROM contexts c
            #     LEFT JOIN contexts_members cm
            #         ON c.id = cm.context_id
            #         AND cm.del != 1
            #     LEFT JOIN agents a
            #         ON cm.agent_id = a.id
            #     LEFT JOIN (
            #         SELECT
            #             context_id,
            #             MAX(id) as latest_message_id
            #         FROM contexts_messages
            #         GROUP BY context_id
            #     ) cmsg ON c.id = cmsg.context_id
            #     WHERE c.parent_id IS NULL
            #     GROUP BY c.id
            #     ORDER BY
            #         COALESCE(cmsg.latest_message_id, 0) DESC;""",
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
                {
                    'text': '',
                    'type': QPushButton,
                    'icon': ':/resources/icon-chat.png',
                    'func': self.on_chat_btn_clicked,
                    'width': 45,
                },
            ],
            dynamic_load=True,
            add_item_prompt=None,
            del_item_prompt=('Delete Context', 'Are you sure you want to permanently delete this context?'),
            layout_type=QVBoxLayout,
            config_widget=None,
            has_config_field=False,
            tree_width=600,
            tree_height=590,
            tree_header_hidden=True,
            folder_key='contexts',
            init_select=False,
            filterable=True,
            searchable=True,
        )
        self.tree_config.build_schema()

        self.tree_config.tree.itemDoubleClicked.connect(self.on_row_double_clicked)

        self.layout.addWidget(self.tree_config)
        self.layout.addStretch(1)

    def load(self):
        self.tree_config.load()
        pass

    def on_row_double_clicked(self):
        context_id = self.tree_config.get_selected_item_id()
        if not context_id:
            return
        self.chat_with_context(context_id)

    def on_chat_btn_clicked(self, _):
        context_id = self.tree_config.get_selected_item_id()
        if not context_id:
            return
        self.chat_with_context(context_id)

    def chat_with_context(self, context_id):
        if self.main.page_chat.workflow.responding:
            return
        self.main.page_chat.goto_context(context_id=context_id)
        self.main.content.setCurrentWidget(self.main.page_chat)
        self.main.sidebar.btn_new_context.setChecked(True)
