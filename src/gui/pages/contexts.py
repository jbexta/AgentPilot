
from gui.util import find_main_widget
from gui.widgets.config_db_tree import ConfigDBTree


class Page_Contexts(ConfigDBTree):
    display_name = 'Chats'
    icon_path = ":/resources/icon-contexts.png"
    page_type = 'main'  # either 'settings', 'main', or 'any' ('any' means it can be pinned between main and settings)

    def __init__(self, parent):
        super().__init__(
            parent=parent,
            table_name='contexts',
            query="""
                SELECT
                    c.name,
                    c.id,
                    CASE
                        WHEN json_extract(c.config, '$.members') IS NOT NULL THEN
                            CASE
                                WHEN json_array_length(json_extract(c.config, '$.members')) > 2 THEN
                                    json_array_length(json_extract(c.config, '$.members')) || ' members'
                                WHEN json_array_length(json_extract(c.config, '$.members')) = 2 THEN
                                    COALESCE(json_extract(json_extract(c.config, '$.members'), '$[1].config."name"'), 'Assistant')
                                WHEN json_extract(json_extract(c.config, '$.members'), '$[1].config._TYPE') = 'agent' THEN
                                    json_extract(json_extract(c.config, '$.members'), '$[1].config."name"')
                                ELSE
                                    json_array_length(json_extract(c.config, '$.members')) || ' members'
                            END
                        ELSE
                            CASE
                                WHEN json_extract(c.config, '$._TYPE') = 'workflow' THEN
                                    '1 member'
                                ELSE
                                    COALESCE(json_extract(c.config, '$."name"'), 'Assistant')
                            END
                    END as member_count,
                    c.config,
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
                AND c.kind = :kind
                GROUP BY c.id
                ORDER BY
                    pinned DESC,
                    COALESCE(cmsg.latest_message_id, 0) DESC, 
                    c.id DESC
                LIMIT :limit OFFSET :offset;
                """,
            schema=[
                {
                    'text': 'name',
                    'type': str,
                    'image_key': 'config',
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
                    'key': 'config',
                    'text': '',
                    'type': str,
                    'visible': False,
                },
                {
                    'text': '',
                    'type': 'button',
                    'icon_path': ':/resources/icon-chat.png',
                    'target': self.on_chat_btn_clicked,
                    'width': 45,
                },
            ],
            dynamic_load=True,
            add_item_options=None,
            del_item_options={'title': 'Delete Context', 'prompt': 'Are you sure you want to permanently delete this chat?'},
            layout_type='vertical',
            config_widget=None,
            tree_header_hidden=True,
            kind='CHAT',
            kind_list=['CHAT', 'BLOCK', 'TOOL', 'TASK'],
            folder_key={'CHAT': 'contexts', 'BLOCK': 'block_contexts', 'TOOL': 'tool_contexts', 'TASK': 'task_contexts'},
            init_select=False,
            filterable=True,
            searchable=True,
            archiveable=True,
        )
        self.tree.itemDoubleClicked.connect(self.on_row_double_clicked)

    def on_row_double_clicked(self):
        context_id = self.get_selected_item_id()
        if not context_id:
            return
        self.chat_with_context(context_id)

    def on_chat_btn_clicked(self):
        context_id = self.get_selected_item_id()
        if not context_id:
            return
        self.chat_with_context(context_id)

    def chat_with_context(self, context_id):
        main = find_main_widget(self)
        page_chat = main.main_pages.get('chat')
        if page_chat.workflow.responding:
            return
        page_chat.goto_context(context_id=context_id)
        page_chat.ensure_visible()
