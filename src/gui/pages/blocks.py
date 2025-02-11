
from src.gui.config import ConfigDBTree
from src.members.workflow import WorkflowSettings


class Page_Block_Settings(ConfigDBTree):
    def __init__(self, parent):
        super().__init__(
            parent=parent,
            table_name='blocks',
            query="""
                SELECT
                    name,
                    id,
                    uuid,
                    folder_id
                FROM blocks
                ORDER BY pinned DESC, ordr, name""",
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
                    'type': int,
                    'visible': False,
                },
            ],
            add_item_options={'title': 'Add Block', 'prompt': 'Enter a name for the block:'},
            del_item_options={'title': 'Delete Block', 'prompt': 'Are you sure you want to delete this block?'},
            folder_key='blocks',
            readonly=False,
            layout_type='horizontal',
            tree_header_hidden=True,
            config_widget=self.Block_Config_Widget(parent=self),
            searchable=True,
            versionable=True,
            default_item_icon=':/resources/icon-block.png',
        )
        self.icon_path = ":/resources/icon-blocks.png"
        self.try_add_breadcrumb_widget(root_title='Blocks')
        self.splitter.setSizes([400, 1000])

    def on_edited(self):
        self.parent.main.system.blocks.load()

    class Block_Config_Widget(WorkflowSettings):
        def __init__(self, parent):
            super().__init__(parent=parent)
