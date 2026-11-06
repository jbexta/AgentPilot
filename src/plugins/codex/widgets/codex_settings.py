from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_joined import ConfigJoined
from gui.widgets.config_tabs import ConfigTabs
from plugins.workflows.widgets.agent_tools import AgentTools
from utils.helpers import set_module_type


@set_module_type(module_type='Widgets')
class CodexSettings(ConfigJoined):
    def __init__(self, parent):
        super().__init__(parent=parent, layout_type='vertical')
        self.widgets = [
            self.Working_Dir(parent=self),
            self.Options(parent=self),
            self.Settings_Tabs(parent=self),
        ]

    class Working_Dir(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.schema = [
                {
                    'text': 'Working dir',
                    'key': 'working_dir',
                    'type': 'file_picker',
                    'mode': 'directory',
                    'default': '{{ cwd }}',
                    'stretch_x': True,
                    'tooltip': '{{ cwd }} is the working dir of the '
                               "chat's project.",
                },
            ]

    class Options(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.conf_namespace = 'chat'
            self.schema = [
                {
                    'text': 'Force subscription login',
                    'key': 'force_subscription',
                    'type': bool,
                    'default': True,
                    'tooltip': 'Ignore API keys and bill your ChatGPT '
                               'subscription login instead.',
                },
            ]

    class Settings_Tabs(ConfigTabs):
        stretch = 1

        def __init__(self, parent):
            super().__init__(parent=parent)
            self.pages = {
                'Messages': CodexSettings.Page_Messages(parent=self),
                'Tools': AgentTools(parent=self),
            }

    class Page_Messages(ConfigFields):
        schema = [
            {
                'text': 'Model',
                'key': 'codex_model',
                'type': str,
                'default': '',
                'width': 160,
                'tooltip': "Empty uses your Codex default.",
                'row_key': 0,
            },
            {
                'text': 'Effort',
                'type': ('minimal', 'low', 'medium', 'high', 'xhigh'),
                'default': 'medium',
                'width': 80,
                'has_toggle': True,
                'row_key': 0,
            },
            {
                'text': 'Approval',
                'key': 'approval_policy',
                'type': ('untrusted', 'on-request', 'never'),
                'default': 'on-request',
                'width': 100,
                'tooltip': 'When Codex asks before running a command.',
                'row_key': 1,
            },
            {
                'text': 'Sandbox',
                'key': 'sandbox',
                'type': ('read-only', 'workspace-write', 'danger-full-access'),
                'default': 'workspace-write',
                'width': 140,
                'row_key': 1,
            },
            {
                'text': 'System message',
                'key': 'sys_msg',
                'type': str,
                'num_lines': 12,
                'default': '',
                'stretch_x': True,
                'stretch_y': True,
                'wrap_text': True,
                'highlighter': 'xml',
                'fold_mode': 'xml',
                'format_blocks': True,
                'enhancement_key': 'system_message',
                'label_position': None,
            },
        ]

        def __init__(self, parent):
            super().__init__(parent=parent)
            self.conf_namespace = 'chat'
            self.schema = [dict(f) for f in self.__class__.schema]

    chat_bar_page = Page_Messages
    chat_bar_keys = ('codex_model', 'approval_policy', 'effort')
