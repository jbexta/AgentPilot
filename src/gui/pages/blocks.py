
from gui.widgets.config_db_tree import ConfigDBTree
from gui.widgets.workflow_settings import WorkflowSettings


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
            readonly=False,
            layout_type='horizontal',
            tree_header_hidden=True,
            default_item_icon=':/resources/icon-block.png',
            config_widget=self.Block_Config_Widget(parent=self),
            searchable=True,
        )
        self.splitter.setSizes([400, 1000])

    class Block_Config_Widget(WorkflowSettings):
        def __init__(self, parent):
            super().__init__(parent=parent)
