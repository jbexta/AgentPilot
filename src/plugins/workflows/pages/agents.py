from utils import sql
from gui.gui_utils.helpers import find_main
from gui.widgets.config_db_tree import ConfigDBTree
from plugins.workflows.widgets.workflow_settings import WorkflowSettings


class Page_Entities(ConfigDBTree):
    display_name = 'Agents'
    icon_path = ":/resources/icon-agent.png"
    page_type = 'main'  # either 'settings', 'main', or 'any' ('any' means it can be pinned between main and settings)

    def __init__(self, parent):
        super().__init__(
            parent=parent,
            manager='agents',  # todo name
            query="""
                SELECT
                    name,
                    id,
                    config,
                    uuid,
                    folder_id
                FROM entities
                WHERE kind = :kind
                ORDER BY pinned DESC, ordr, name COLLATE NOCASE""",
            schema=[
                {
                    'text': 'Name',
                    'key': 'name',
                    'type': str,
                    'stretch': True,
                    'image_key': 'config',
                },
                {
                    'text': 'id',
                    'key': 'id',
                    'type': int,
                    'visible': False,
                },
                {
                    'text': 'config',
                    'type': str,
                    'visible': False,
                },
                {
                    'text': 'uuid',
                    'key': 'uuid',
                    'type': str,
                    'visible': False,
                },
            ],
            layout_type='horizontal',
            config_widget=self.Entity_Config_Widget(parent=self),
            folder_config_widget=self.Folder_Config_Widget(parent=self),
            tree_header_hidden=True,
            readonly=True,
            searchable=True,
            kind='AGENT',
            folder_key='agents',
        )
        self.splitter.setSizes([400, 1000])
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)

    # Commented out so the Agents page falls back to the automatic widget
    # walk (like Blocks/Tools) and exercises its embedded WorkflowSettings via
    # the shared WorkflowSettings.test_widget, giving uniform coverage across
    # all three pages. Defining test_page suppresses the auto-walk (XOR), so
    # this bespoke page test is disabled rather than running in addition.
    # def test_page(self, main, ui):
    #     import time
    #
    #     if self.tree.topLevelItemCount() == 0:
    #         raise AssertionError("Agents tree has no rows after bootstrap")
    #
    #     if self.config_widget is None:
    #         raise AssertionError("Agents page is missing its config_widget")
    #
    #     target_name = 'Builder'
    #     ui.click_tree_item_cell(self.tree, target_name, 'name')
    #     time.sleep(0.3)
    #
    #     assert self.tree.get_selected_item_id() is not None, f"Clicking '{target_name}' did not select an item"
    #     loaded_name = (self.config_widget.get_config() or {}).get('name')
    #     assert loaded_name == target_name, f"Config widget loaded name={loaded_name!r}, expected {target_name!r} after selecting '{target_name}'"

    def on_item_double_clicked(self, item, column):
        entity_id = self.tree.get_selected_item_id()
        if entity_id is None:
            return
        entity_uuid = sql.get_scalar(
            "SELECT uuid FROM entities WHERE id = ?", (entity_id,)
        )
        if not entity_uuid:
            return
        main = find_main()
        page_chat = main.main_pages.pages.get('chat')
        if page_chat is None:
            return
        page_chat.new_context(
            entity_id=entity_uuid,
            entity_table='entities',
            kind='CHAT',
        )
        main.main_pages.goto_page('chat')

    class Entity_Config_Widget(WorkflowSettings):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                kind='AGENT',
            )
