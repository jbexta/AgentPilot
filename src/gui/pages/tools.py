import json

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


            # def load_config(self, json_config=None):
            #     if json_config is None:
            #         json_config = '{}'  # todo
            #     if isinstance(json_config, str):
            #         json_config = json.loads(json_config)
            #     if json_config.get('_TYPE', 'agent') != 'workflow':
            #         json_config = merge_config_into_workflow_config(json_config)
            #
            #     json_wf_config = json_config.get('config', {})
            #     json_wf_params = json_config.get('params', [])
            #     self.workflow_config.load_config(json_wf_config)
            #     self.workflow_params.load_config({'data': json_wf_params})  # !55! #
            #     super().load_config(json_config)

            # def load_config(self, json_config=None):
            #     if json_config is not None:
            #         if isinstance(json_config, str):
            #             json_config = json.loads(json_config)
            #         self.config = json_config if json_config else {}
            #
            #     else:
            #         parent_config = getattr(self.parent, 'config', {})
            #
            #         if self.conf_namespace is None and not isinstance(self, ConfigDBTree):
            #             self.config = parent_config
            #         else:
            #             self.config = {k: v for k, v in parent_config.items() if k.startswith(f'{self.conf_namespace}.')}
            #
            #     self.member_config_widget.load(temp_only_config=True)

            def update_config(self):
                # self.parent.update_config()
                self.save_config()

            def save_config(self):
                # conf = self.get_config()
                # self.parent.members_in_view[self.member_id].member_config = conf
                self.parent.update_config()

            # def update_config(self):
            #     self.save_config()

            # def save_config(self):
            #     """Block the save_config method"""
            #     pass
                # conf = self.get_config()
                # self.parent.members_in_view[self.member_id].member_config = conf
                # self.parent.save_config()

        # class Tool_Tab_Widget(ConfigTabs):
        #     def __init__(self, parent):
        #         super().__init__(parent=parent)
        #
        #         self.pages = {
        #             'Code': self.Tab_Code(parent=self),
        #             'Parameters': self.Tab_Parameters(parent=self),
        #             'Bubble': self.Tab_Bubble(parent=self),
        #         }
        #
        #     class Tab_Code(ConfigFields):
        #         def __init__(self, parent):
        #             super().__init__(parent=parent)
        #             self.conf_namespace = 'code'
        #             self.schema = [
        #                 {
        #                     'text': 'Type',
        #                     'type': ('Native',),
        #                     'width': 100,
        #                     'tooltip': 'The type of code to execute. `Native` executes the code within a predefined function. `Script` will execute the code in a python script (Not implented yet). `Imported` will use an externally imported tool.',
        #                     'row_key': 'A',
        #                     'default': 'Native',
        #                 },
        #                 {
        #                     'text': 'Language',
        #                     'type': ('AppleScript', 'HTML', 'JavaScript', 'Python', 'PowerShell', 'R', 'React', 'Ruby', 'Shell',),
        #                     'width': 100,
        #                     'tooltip': 'The language of the code, to be passed to open interpreter',
        #                     'label_position': None,
        #                     'row_key': 'A',
        #                     'default': 'Python',
        #                 },
        #                 {
        #                     'text': 'Code',
        #                     'key': 'data',
        #                     'type': str,
        #                     'stretch_x': True,
        #                     'stretch_y': True,
        #                     'num_lines': 2,
        #                     'label_position': None,
        #                     # 'highlighter_field': 'language',
        #                     'highlighter': PythonHighlighter,
        #                     'encrypt': True,
        #                     'default': '',
        #                 },
        #             ]
        #             # self.btn_goto_env_vars = IconButton(
        #             #     parent=self,
        #
        #     class Tab_Parameters(ConfigJsonTree):
        #         def __init__(self, parent):
        #             super().__init__(parent=parent,
        #                              add_item_prompt=('NA', 'NA'),
        #                              del_item_prompt=('NA', 'NA'))
        #             self.parent = parent
        #             self.conf_namespace = 'parameters'
        #             self.schema = [
        #                 {
        #                     'text': 'Name',
        #                     'type': str,
        #                     'width': 120,
        #                     'default': '< Enter a parameter name >',
        #                 },
        #                 {
        #                     'text': 'Description',
        #                     'type': str,
        #                     'stretch': True,
        #                     'default': '< Enter a description >',
        #                 },
        #                 {
        #                     'text': 'Type',
        #                     'type': ('String', 'Int', 'Float', 'Bool', 'List',),
        #                     'width': 100,
        #                     'on_edit_reload': True,
        #                     'default': 'String',
        #                 },
        #                 {
        #                     'text': 'Req',
        #                     'type': bool,
        #                     'default': True,
        #                 },
        #             ]
        #
        #     class Tab_Bubble(ConfigFields):
        #         def __init__(self, parent):
        #             super().__init__(parent=parent)
        #             self.conf_namespace = 'bubble'
        #             self.label_width = 130
        #             self.schema = [
        #                 {
        #                     'text': 'Auto run',
        #                     'type': int,
        #                     'minimum': 0,
        #                     'maximum': 30,
        #                     'step': 1,
        #                     'label_width': 150,
        #                     'default': 5,
        #                     'has_toggle': True,
        #                 },
        #                 # {
        #                 #     'text': 'Show tool bubble',
        #                 #     'type': bool,
        #                 #     'default': True,
        #                 # },
        #                 {
        #                     'text': 'Show result bubble',
        #                     'type': bool,
        #                     'default': False,
        #                 },
        #             ]
