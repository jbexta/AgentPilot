from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_tabs import ConfigTabs
from gui.widgets.config_joined import ConfigJoined
from gui.widgets.config_json_db_tree import ConfigJsonDBTree
from gui.widgets.config_json_tree import ConfigJsonTree
from utils.helpers import set_module_type


@set_module_type(module_type='Widgets')
class ClaudeCodeSettings(ConfigTabs):
    def __init__(self, parent):
        super().__init__(parent=parent)

        self.pages = {
            'Messages': self.Page_Messages(parent=self),
            'Tools': self.Page_Tools(parent=self),
            'Hooks': self.Page_Hooks(parent=self),
            'Voice': self.Page_Voice(parent=self),
        }

    class Page_Messages(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.conf_namespace = 'chat'
            self.schema = [
                {
                    'text': 'Model',
                    'type': 'model',
                    'model_kind': 'CHAT',
                    'popup_params': True,
                    'default': '',
                    'width': 200,
                    'row_key': 0,
                },
                {
                    'text': 'Max turns',
                    'type': int,
                    'minimum': 1,
                    'maximum': 99,
                    'default': 7,
                    'width': 60,
                    'has_toggle': True,
                    'row_key': 0,
                },
                {
                    'text': 'Fast',
                    'type': bool,
                    'default': False,
                    'row_key': 0,
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
                    'label_position': 'top',
                },
            ]

    class Page_Voice(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.conf_namespace = 'voice'
            self.schema = [
                {
                    'text': 'Model',
                    'type': 'model',
                    'model_kind': 'AUDIO',
                    'width': 200,
                    'default': '',
                },
            ]

    class Page_Hooks(ConfigJsonTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                conf_namespace='hooks',
                schema=[
                    {
                        'text': 'Event',
                        'key': 'event',
                        'type': (
                            'PreToolUse', 'PostToolUse',
                            'UserPromptSubmit', 'Stop',
                            'SubagentStop', 'PreCompact',
                        ),
                        'default': 'PreToolUse',
                        'width': 120,
                    },
                    {
                        'text': 'Matcher',
                        'key': 'matcher',
                        'type': (
                            'All', 'Bash', 'Read', 'Write', 'Edit',
                            'Glob', 'Grep', 'WebFetch', 'WebSearch',
                        ),
                        'default': 'All',
                        'width': 100,
                        'visibility_predicate': lambda row: row.get(
                            'event', '') in ('PreToolUse', 'PostToolUse'),
                    },
                    {
                        'text': 'Entity',
                        'key': 'entity',
                        'type': 'entity',
                        'stretch': True,
                    },
                ],
            )

    class Page_Tools(ConfigJoined):
        def __init__(self, parent):
            super().__init__(parent=parent, layout_type='vertical')
            self.widgets = [
                self.Builtin_Tools(parent=self),
                self.Custom_Tools(parent=self),
            ]

        class Builtin_Tools(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.conf_namespace = 'builtin_tools'
                self.setMaximumHeight(80)
                self.label_width = 90
                self.schema = [
                    {
                        'text': 'Bash',
                        'type': bool,
                        'default': True,
                        'row_key': 0,
                    },
                    {
                        'text': 'Read',
                        'type': bool,
                        'default': True,
                        'row_key': 0,
                    },
                    {
                        'text': 'Write',
                        'type': bool,
                        'default': False,
                        'row_key': 0,
                    },
                    {
                        'text': 'Edit',
                        'type': bool,
                        'default': False,
                        'row_key': 0,
                    },
                    {
                        'text': 'Glob',
                        'type': bool,
                        'default': True,
                        'row_key': 1,
                    },
                    {
                        'text': 'Grep',
                        'type': bool,
                        'default': True,
                        'row_key': 1,
                    },
                    {
                        'text': 'WebFetch',
                        'type': bool,
                        'default': False,
                        'row_key': 1,
                    },
                    {
                        'text': 'WebSearch',
                        'type': bool,
                        'default': False,
                        'row_key': 1,
                    },
                ]

        class Custom_Tools(ConfigJsonDBTree):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    add_item_options={'title': 'NA', 'prompt': 'NA'},
                    del_item_options={'title': 'NA', 'prompt': 'NA'},
                    tree_header_hidden=True,
                    table_name='tools',
                    key_field='uuid',
                    item_icon_path=':/resources/icon-tool-small.png',
                    show_fields=[
                        'name',
                        'uuid',
                    ],
                    readonly=True
                )
                self.conf_namespace = 'custom_tools'
                self.schema = [
                    {
                        'text': 'Tool',
                        'type': str,
                        'width': 175,
                        'default': '',
                    },
                    {
                        'text': 'id',
                        'visible': False,
                        'default': '',
                    },
                ]