
from gui.widgets.config_db_tree import ConfigDBTree
from plugins.workflows.widgets.chat_widget import ChattableWorkflowWidget


class Page_Block_Settings(ConfigDBTree):
    display_name = 'Blocks'
    icon_path = ":/resources/icon-blocks.png"
    page_type = 'any'  # either 'settings', 'main', or 'any' ('any' means it can be pinned between main and settings)

    def __init__(self, parent):
        super().__init__(
            parent=parent,
            manager='blocks',
            query="""
                SELECT
                    name,
                    id,
                    uuid,
                    folder_id,
                    parent_id,
                    kind
                FROM blocks
                ORDER BY kind, pinned DESC, ordr, name COLLATE NOCASE""",
            schema=[
                {
                    'text': 'Name',
                    'key': 'name',
                    'type': str,
                    'stretch': True,
                },
                {
                    'text': 'id',
                    'key': 'id',
                    'type': int,
                    'visible': False,
                },
                {
                    'text': 'uuid',
                    'key': 'uuid',
                    'type': str,
                    'visible': False,
                },
            ],
            readonly=False,
            layout_type='horizontal',
            tree_header_hidden=True,
            default_item_icon=':/resources/icon-block.png',
            config_widget=self.Block_Config_Widget(parent=self),
            folder_config_widget=self.Folder_Config_Widget(parent=self),
            folder_key='blocks',
            support_item_nesting=True,
            group_by_kind=True,
            kind_folder_key=lambda kind: f'{kind.lower()}:block',
            searchable=True,
            has_chat=True,
            notify_unread=True,
        )
        self.splitter.setSizes([400, 1000])

    class Block_Config_Widget(ChattableWorkflowWidget):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                kind='BLOCK',
            )
