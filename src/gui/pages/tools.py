from PySide6.QtWidgets import QVBoxLayout

from src.gui.config import ConfigFields, ConfigJsonTree, ConfigTabs, ConfigJoined, ConfigDBTree
from src.gui.widgets import PythonHighlighter, find_main_widget


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
                    'type': ('Function call', 'Prompt based',),
                    'is_config_field': True,
                    'width': 125,
                },
                {
                    'text': 'Environment',
                    'key': 'environment',
                    'type': 'SandboxComboBox',
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

    def on_edited(self):
        self.main.system.tools.load()

    class Tool_Config_Widget(ConfigJoined):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.widgets = [
                self.Tool_Info_Widget(parent=self),
                self.Tool_Tab_Widget(parent=self),
            ]

        class Tool_Info_Widget(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.schema = [
                    {
                        'text': 'Description',
                        'type': str,
                        'num_lines': 3,
                        'label_position': 'top',
                        'width': 520,
                        'tooltip': 'A description of the tool, this is required and used by the LLM',
                        'default': '',
                    },
                    # {
                    #     'text': 'Method',
                    #     'type': ('Function call', 'Prompt based',),
                    #     'tooltip': 'The method to use for the tool decision. `Function call` will use a function calling LLM. `Prompt based` is cheaper and will use any LLM to decide to use tools.',
                    #     'default': 'Native',
                    # },
                ]

        class Tool_Tab_Widget(ConfigTabs):
            def __init__(self, parent):
                super().__init__(parent=parent)

                self.pages = {
                    'Code': self.Tab_Code(parent=self),
                    'Parameters': self.Tab_Parameters(parent=self),
                    'Bubble': self.Tab_Bubble(parent=self),
                    # 'Prompt': self.Tab_Prompt(parent=self),
                }

            class Tab_Code(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.conf_namespace = 'code'
                    self.schema = [
                        {
                            'text': 'Type',
                            'type': ('Native', 'Imported',),
                            'width': 100,
                            'tooltip': 'The type of code to execute. `Native` executes the code within a predefined function. `Script` will execute the code in a python script (Not implented yet). `Imported` will use an externally imported tool.',
                            'row_key': 'A',
                            'default': 'Native',
                        },
                        # {
                        #     'text': 'Function',
                        # }
                        {
                            'text': 'Language',
                            'type': ('AppleScript', 'HTML', 'JavaScript', 'Python', 'PowerShell', 'R', 'React', 'Ruby', 'Shell',),
                            'width': 100,
                            'tooltip': 'The language of the code, to be passed to open interpreter',
                            'label_position': None,
                            'row_key': 'A',
                            'default': 'Python',
                        },
                        # {
                        #     'text': 'Environment',
                        #     'type': 'SandboxComboBox',
                        #     'tooltip': 'The sandbox to execute the tool',
                        #     'label_position': None,
                        #     'width': 100,
                        #     'default': 'Local',
                        #     'row_key': 'A',
                        # },
                        # {
                        #     'text': 'Delay seconds',
                        #     'type': int,
                        #     'minimum': 1,
                        #     'maximum': 30,
                        #     'step': 1,
                        #     'tooltip': 'The delay in seconds before the tool is executed',
                        #     'has_toggle': True,
                        #     'row_key': 'A',
                        #     'default': 5,
                        # },
                        {
                            'text': 'Code',
                            'key': 'data',
                            'type': str,
                            'width': 520,
                            'num_lines': 10,
                            'label_position': None,
                            'highlighter': PythonHighlighter,
                            'encrypt': True,
                            'default': '',
                        },
                    ]

            class Tab_Parameters(ConfigJsonTree):
                def __init__(self, parent):
                    super().__init__(parent=parent,
                                     add_item_prompt=('NA', 'NA'),
                                     del_item_prompt=('NA', 'NA'))
                    self.parent = parent
                    self.conf_namespace = 'parameters'
                    self.schema = [
                        {
                            'text': 'Name',
                            'type': str,
                            'width': 120,
                            'default': '< Enter a parameter name >',
                        },
                        {
                            'text': 'Description',
                            'type': str,
                            'stretch': True,
                            'default': '< Enter a parameter name >',
                        },
                        {
                            'text': 'Type',
                            'type': ('String', 'Integer', 'Float', 'Bool', 'List',),
                            'width': 100,
                            'default': 'String',
                        },
                        {
                            'text': 'Req',
                            'type': bool,
                            'default': True,
                        },
                        {
                            'text': 'Default',
                            'type': str,
                            'default': '',
                        },
                    ]

            class Tab_Bubble(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.conf_namespace = 'bubble'
                    self.label_width = 130
                    self.schema = [
                        {
                            'text': 'Auto run',
                            'type': int,
                            'minimum': 0,
                            'maximum': 30,
                            'step': 1,
                            'label_width': 150,
                            'default': 5,
                            'has_toggle': True,
                        },
                        # {
                        #     'text': 'Show tool bubble',
                        #     'type': bool,
                        #     'default': True,
                        # },
                        {
                            'text': 'Show result bubble',
                            'type': bool,
                            'default': False,
                        },
                    ]
