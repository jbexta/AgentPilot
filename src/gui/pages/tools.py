
from PySide6.QtWidgets import QVBoxLayout

from src.gui.config import ConfigFields, ConfigJoined, ConfigDBTree
from src.gui.widgets import find_main_widget
from src.members.workflow import WorkflowSettings


class Page_Tool_Settings(ConfigDBTree):
    def __init__(self, parent):
        super().__init__(
            parent=parent,
            db_table='tools',
            propagate=False,
            query="""
                SELECT
                    name,
                    id,
                    COALESCE(json_extract(config, '$.method'), 'Function call'),
                    COALESCE(json_extract(config, '$.environment'), 'Local'),
                    folder_id
                FROM tools""",
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
                    'text': 'Method',
                    'key': 'method',
                    'type': ('Function call',),  # , 'Prompt based',),
                    'is_config_field': True,
                    'width': 125,
                },
                {
                    'text': 'Environment',
                    'key': 'environment',
                    'type': 'EnvironmentComboBox',
                    'is_config_field': True,
                    'width': 125,
                }
            ],
            add_item_prompt=('Add Tool', 'Enter a name for the tool:'),
            del_item_prompt=('Delete Tool', 'Are you sure you want to delete this tool?'),
            readonly=False,
            layout_type=QVBoxLayout,
            folder_key='tools',
            config_widget=self.Tool_Config_Widget(parent=self),
        )
        self.icon_path = ":/resources/icon-tool.png"
        self.main = find_main_widget(self)
        self.try_add_breadcrumb_widget(root_title='Tools')
        self.splitter.setSizes([500, 500])

    def on_edited(self):
        self.main.system.tools.load()

    class Tool_Config_Widget(ConfigJoined):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.widgets = [
                self.Tool_Info_Widget(parent=self),
                self.ToolWorkflowSettings(parent=self),
            ]

        class Tool_Info_Widget(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.setFixedHeight(90)
                self.schema = [
                    {
                        'text': 'Description',
                        'type': str,
                        'num_lines': 3,
                        'label_position': 'top',
                        'stretch_x': True,
                        'tooltip': 'A description of the tool, this is required and used by the LLM',
                        'default': '',
                    },
                ]

        class ToolWorkflowSettings(WorkflowSettings):
            def __init__(self, parent):
                super().__init__(parent, compact_mode=True)

            def load_config(self, json_config=None):
                if json_config is None:
                    parent_config = getattr(self.parent, 'config', {})

                    if self.conf_namespace is None and not isinstance(self, ConfigDBTree):
                        json_config = parent_config
                    else:
                        json_config = {k: v for k, v in parent_config.items() if k.startswith(f'{self.conf_namespace}.')}
                super().load_config(json_config)

            def update_config(self):
                # self.parent.update_config()
                self.save_config()

            def save_config(self):
                # conf = self.get_config()
                # self.parent.members_in_view[self.member_id].member_config = conf
                self.parent.update_config()
