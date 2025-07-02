
from gui.widgets.config_db_tree import ConfigDBTree
from gui.widgets.workflow_settings import WorkflowSettings


class Page_Tool_Settings(ConfigDBTree):
    display_name = 'Tools'
    icon_path = ":/resources/icon-tool.png"
    page_type = 'any'  # either 'settings', 'main', or 'any' ('any' means it can be pinned between main and settings)

    def __init__(self, parent):
        super().__init__(
            parent=parent,
            manager='tools',
            query="""
                SELECT
                    name,
                    id,
                    uuid,
                    COALESCE(json_extract(config, '$.type'), ''),
                    -- COALESCE(json_extract(config, '$.environment'), 'Local'),
                    folder_id
                FROM tools
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
                    'type': str,
                    'visible': False,
                },
                {
                    'text': 'Type',
                    'key': 'type',
                    'type': str,
                    'is_config_field': True,
                    'width': 150,
                },
                # {
                #     'text': 'Type',
                #     'key': 'type',
                #     'type': ('Function', 'computer_20241022',),  # , 'Prompt based',),
                #     'is_config_field': True,
                #     'width': 175,
                # },
            ],
            add_item_options={'title': 'Add Tool', 'prompt': 'Enter a name for the tool:'},
            del_item_options={'title': 'Delete Tool', 'prompt': 'Are you sure you want to delete this tool?'},
            readonly=False,
            layout_type='horizontal',
            folder_key='tools',
            config_widget=self.ToolWorkflowSettings(parent=self),
            tree_header_resizable=True,
            default_item_icon=':/resources/icon-tool-small.png',
        )
        self.splitter.setSizes([500, 500])

    def on_edited(self):
        from system import manager
        manager.tools.load()

    class ToolWorkflowSettings(WorkflowSettings):
        def __init__(self, parent):
            super().__init__(parent)  # , compact_mode=True)
