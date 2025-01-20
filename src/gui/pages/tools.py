
from src.gui.config import ConfigFields, ConfigJoined, ConfigDBTree, ConfigTabs
from src.gui.widgets import find_main_widget
from src.members.workflow import WorkflowSettings


class Page_Tool_Settings(ConfigDBTree):
    def __init__(self, parent):
        super().__init__(
            parent=parent,
            table_name='tools',
            query="""
                SELECT
                    name,
                    id,
                    uuid,
                    COALESCE(json_extract(config, '$.method'), 'Function call'),
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
                    'text': 'Method',
                    'key': 'method',
                    'type': ('Function call',),  # , 'Prompt based',),
                    'is_config_field': True,
                    'width': 125,
                },
            ],
            add_item_options={'title': 'Add Tool', 'prompt': 'Enter a name for the tool:'},
            del_item_options={'title': 'Delete Tool', 'prompt': 'Are you sure you want to delete this tool?'},
            readonly=False,
            layout_type='vertical',
            folder_key='tools',
            config_widget=self.Tool_Config_Widget(parent=self),
            default_item_icon=':/resources/icon-tool-small.png',
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

        class Tool_Info_Widget(ConfigTabs):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.provider = None
                self.pages = {
                    'Description': self.Tab_Description(parent=self),
                    # 'Prompt': self.Tab_System_Prompt(parent=self),
                }

            class Tab_Description(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.setFixedHeight(90)
                    self.schema = [
                        {
                            'text': 'Description',
                            'type': str,
                            'num_lines': 4,
                            'label_position': None,
                            'stretch_x': True,
                            'tooltip': 'A description of the tool, this is required and used by the LLM',
                            'default': '',
                        },
                    ]

            class Tab_System_Prompt(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.setFixedHeight(90)
                    self.schema = [
                        {
                            'text': 'System prompt',
                            'type': str,
                            'num_lines': 4,
                            'label_position': None,
                            'stretch_x': True,
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
                self.save_config()

            def save_config(self):
                self.parent.update_config()
