from typing_extensions import override
from PySide6.QtWidgets import QPushButton

from src.gui.widgets.config_db_tree import ConfigDBTree
from src.gui.widgets.workflow_settings import WorkflowSettings


class Page_Entities(ConfigDBTree):
    display_name = 'Agents'
    icon_path = ":/resources/icon-agent.png"
    page_type = 'main'  # either 'settings', 'main', or 'any' ('any' means it can be pinned between main and settings)

    def __init__(self, parent):
        super().__init__(
            parent=parent,
            manager='agents',
            query="""
                SELECT
                    COALESCE(json_extract(config, '$."info.name"'), name) AS name,
                    id,
                    config,
                    '' AS chat_button,
                    folder_id
                FROM entities
                WHERE kind = :kind
                ORDER BY pinned DESC, ordr, name""",
            # table_name='entities',  # todo rename back to agents
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
                    'text': '',
                    'type': QPushButton,
                    'icon': ':/resources/icon-chat.png',
                    'func': self.on_chat_btn_clicked,
                    'width': 45,
                },
            ],
            layout_type='vertical',
            config_widget=self.Entity_Config_Widget(parent=self),
            tree_header_hidden=True,
            searchable=True,
            # button_schema=[
            #     {
            #         'key': 'btn_add',
            #         'icon_path': ':/resources/icon-new.png',
            #         'tooltip': 'Add',
            #     },
            #     {
            #         'key': 'btn_del',
            #         'icon_path': ':/resources/icon-minus.png',
            #         'tooltip': 'Delete',
            #     },
            # ],
            # # kind='AGENT',
            # # # kind_list=['AGENT', 'CONTACT'],
            # # add_item_options={'title': 'Add Agent', 'prompt': 'Enter a name for the agent:'},
            # # del_item_options={'title': 'Delete Agent', 'prompt': 'Are you sure you want to delete this agent?'},
            # # folder_key='agents',
            # # filterable=True,
        )
        self.tree.itemDoubleClicked.connect(self.on_chat_btn_clicked)
        self.splitter.setSizes([500, 500])

    @override
    def load(self, select_id=None, silent_select_id=None, append=False):
        self.config_widget.set_edit_mode(False)
        super().load(select_id, silent_select_id, append)

    def on_chat_btn_clicked(self, _):
        run_btn = getattr(self.tree_buttons, 'btn_run', None)
        if run_btn:
            run_btn.click()

    class Entity_Config_Widget(WorkflowSettings):
        def __init__(self, parent):
            super().__init__(parent=parent, compact_mode=True)
