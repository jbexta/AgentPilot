import json
import sqlite3

from PySide6.QtWidgets import QHBoxLayout, QMessageBox

from src.gui.config import ConfigDBTree
from src.members.workflow import WorkflowSettings
from src.utils import sql
from src.utils.helpers import display_messagebox


class Page_Block_Settings(ConfigDBTree):
    def __init__(self, parent):
        super().__init__(
            parent=parent,
            db_table='blocks',
            propagate=False,
            query="""
                SELECT
                    name,
                    id,
                    folder_id
                FROM blocks""",
            schema=[
                {
                    'text': 'Blocks',
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
            ],
            add_item_prompt=('Add Block', 'Enter a name for the block:'),
            del_item_prompt=('Delete Block', 'Are you sure you want to delete this block?'),
            folder_key='blocks',
            readonly=False,
            layout_type=QHBoxLayout,
            tree_header_hidden=True,
            config_widget=self.Block_Config_Widget(parent=self),
            default_item_icon=':/resources/icon-block.png',
        )
        self.icon_path = ":/resources/icon-blocks.png"
        self.try_add_breadcrumb_widget(root_title='Blocks')

    def on_edited(self):
        self.parent.main.system.blocks.load()

    class Block_Config_Widget(WorkflowSettings):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.setFixedWidth(450)
            pass

        def save_config(self):
            """Saves the config to database when modified"""
            json_config_dict = self.get_config()
            json_config = json.dumps(json_config_dict)

            entity_id = self.parent.get_selected_item_id()
            if not entity_id:
                raise NotImplementedError()

            try:
                sql.execute("UPDATE blocks SET config = ? WHERE id = ?", (json_config, entity_id))
            except sqlite3.IntegrityError as e:
                display_messagebox(
                    icon=QMessageBox.Warning,
                    title='Error',
                    text='Name already exists',
                )  # todo

            self.load_config(json_config)  # reload config
            self.parent.reload_current_row()
