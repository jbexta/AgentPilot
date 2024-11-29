
from src.gui.config import ConfigDBTree, ConfigFields
from src.gui.widgets import PythonHighlighter
from src.members.workflow import WorkflowSettings

from PySide6.QtWidgets import QHBoxLayout


class Page_Module_Settings(ConfigDBTree):
    def __init__(self, parent):
        super().__init__(
            parent=parent,
            db_table='modules',
            propagate=False,
            query="""
                SELECT
                    name,
                    id,
                    folder_id
                FROM modules""",
            schema=[
                {
                    'text': 'Modules',
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
            add_item_prompt=('Add module', 'Enter a name for the module:'),
            del_item_prompt=('Delete module', 'Are you sure you want to delete this module?'),
            folder_key='modules',
            readonly=False,
            layout_type=QHBoxLayout,
            tree_header_hidden=True,
            config_widget=self.Module_Config_Widget(parent=self),
            searchable=True,
            default_item_icon=':/resources/icon-jigsaw.png',
        )
        self.icon_path = ":/resources/icon-jigsaw.png"
        self.try_add_breadcrumb_widget(root_title='Modules')
        # set first splitter width to 200
        self.splitter.setSizes([400, 1000])

    def on_edited(self):
        self.parent.main.system.modules.load()

    class Module_Config_Widget(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.schema = [
                {
                    'text': 'Data',
                    'type': str,
                    'default': '',
                    'num_lines': 2,
                    'stretch_x': True,
                    'stretch_y': True,
                    'highlighter': PythonHighlighter,
                    'label_position': None,
                },
            ]
