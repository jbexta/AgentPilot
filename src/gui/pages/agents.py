from typing_extensions import override
from gui.widgets.config_db_tree import ConfigDBTree
from gui.widgets.workflow_settings import WorkflowSettings
from utils import sql


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
                    '' AS chat_button,
                    folder_id
                FROM entities
                WHERE kind = :kind
                ORDER BY pinned DESC, ordr, name""",
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
                    'type': 'button',
                    'icon_path': ':/resources/icon-chat.png',
                    'target': self.on_chat_btn_clicked,
                    'width': 45,
                },
            ],
            layout_type='vertical',
            config_widget=self.Entity_Config_Widget(parent=self),
            tree_header_hidden=True,
            readonly=True,
            searchable=True,
            filterable=True,
            kind='AGENT',
            kind_list=['AGENT', 'CONTACT'],
            folder_key={'AGENT': 'agents', 'CONTACT': 'contacts'},
        )
        self.tree.itemDoubleClicked.connect(self.on_chat_btn_clicked)
        self.splitter.setSizes([500, 500])

    @override
    def load(self, select_id=None, silent_select_id=None, append=False):
        self.config_widget.set_edit_mode(False)
        super().load(select_id, silent_select_id, append)

    # def save_config(self):
    #     item_id = self.tree.get_selected_item_id()
    #     config = self.config_widget.get_config()
    #
    #     name = config.get('name', 'Assistant')
    #     existing_names = sql.get_results(  # where name like  f'{name}%' and id != {item_id}
    #         "SELECT name FROM entities WHERE name LIKE ? AND id != ?",
    #         (f'{name}%', item_id,), return_type='list'
    #     )
    #     # append _n until name not in existing_names
    #     row_name = name
    #     n = 0
    #     while row_name in existing_names:
    #         n += 1
    #         row_name = f"{name}_{n}"
    #
    #     sql.execute("""
    #         UPDATE entities
    #         SET name = ?
    #         WHERE id = ?
    #     """, (row_name, item_id))
    #     super().save_config()  # todo

    def on_chat_btn_clicked(self):
        run_btn = getattr(self.tree_buttons, 'btn_run', None)
        if run_btn:
            run_btn.click()

    class Entity_Config_Widget(WorkflowSettings):
        def __init__(self, parent):
            super().__init__(parent=parent, compact_mode=True)
