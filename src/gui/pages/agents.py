
from src.members.workflow import WorkflowSettings
from src.gui.config import ConfigDBTree
from src.gui.widgets import find_main_widget

from PySide6.QtWidgets import QPushButton, QVBoxLayout

class Page_Entities(ConfigDBTree):
    def __init__(self, parent):
        super().__init__(
            parent=parent,
            db_table='entities',
            query="""
                SELECT
                    COALESCE(json_extract(config, '$."info.name"'), name) AS name,
                    id,
                    config,
                    '' AS chat_button,
                    folder_id
                FROM entities
                WHERE kind = "{{kind}}"
                ORDER BY ordr""",
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
            kind='AGENT',
            # kind_list=['AGENT', 'CONTACT'],
            add_item_prompt=('Add Agent', 'Enter a name for the agent:'),
            del_item_prompt=('Delete Agent', 'Are you sure you want to delete this agent?'),
            layout_type='vertical',
            config_widget=self.Entity_Config_Widget(parent=self),
            tree_header_hidden=True,
            folder_key='agents',
            filterable=True,
            searchable=True
        )
        self.icon_path = ":/resources/icon-agent.png"
        self.tree.itemDoubleClicked.connect(self.on_row_double_clicked)
        self.try_add_breadcrumb_widget(root_title='Agents')
        self.splitter.setSizes([500, 500])

    def load(self, select_id=None, silent_select_id=None, append=False):
        self.config_widget.set_edit_mode(False)
        super().load(select_id, silent_select_id, append)

    def on_row_double_clicked(self):
        agent_id = self.get_selected_item_id()
        if not agent_id:
            return

        self.chat_with_agent(agent_id)

    def on_chat_btn_clicked(self, row_data):
        agent_id = self.get_selected_item_id()
        if not agent_id:
            return
        self.chat_with_agent(agent_id)

    def chat_with_agent(self, agent_id):
        main = find_main_widget(self)
        if main.page_chat.workflow.responding:
            return
        main.page_chat.new_context(entity_id=agent_id)
        main.page_chat.ensure_visible()

    class Entity_Config_Widget(WorkflowSettings):
        def __init__(self, parent):
            super().__init__(parent=parent,
                             compact_mode=True,
                             db_table='entities')
