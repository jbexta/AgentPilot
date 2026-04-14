from gui import system
from gui.widgets.config_db_tree import ConfigDBTree
from plugins.workflows.widgets.chat_widget import ChattableWorkflowWidget


class Page_Skill_Settings(ConfigDBTree):
    display_name = 'Skills'
    icon_path = ":/resources/icon-blocks.png"
    page_type = 'any'  # either 'settings', 'main', or 'any' ('any' means it can be pinned between main and settings)

    def __init__(self, parent):
        super().__init__(
            parent=parent,
            manager='skills',
            query="""
                SELECT
                    name,
                    id,
                    uuid,
                    folder_id,
                    parent_id
                FROM skills
                ORDER BY pinned DESC, ordr, name COLLATE NOCASE""",
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
            config_widget=self.Skill_Config_Widget(parent=self),
            folder_config_widget=self.Folder_Config_Widget(parent=self),
            folder_key='skills',
            support_item_nesting=True,
            searchable=True,
            has_chat=True,
        )
        self.splitter.setSizes([400, 1000])

    def on_edited(self):
        system.manager.skills.load()
        system.manager.skills.sync_to_disk()

    class Skill_Config_Widget(ChattableWorkflowWidget):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                kind='SKILL',
            )
