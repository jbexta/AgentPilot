from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_tabs import ConfigTabs
from gui.widgets.config_joined import ConfigJoined
from gui.widgets.config_json_tree import ConfigJsonTree
from plugins.workflows.widgets.agent_tools import AgentTools
from utils.helpers import set_module_type


@set_module_type(module_type='Widgets')
class ClaudeCodeSettings(ConfigJoined):
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
                    'default': False,
                    'tooltip': 'Ignore API keys and bill your own Claude '
                               'subscription login instead.',
                    'row_key': 0,
                },
                {
                    'text': 'Ignore user MCP servers',
                    'key': 'strict_mcp',
                    'type': bool,
                    'default': False,
                    'tooltip': "Skip the user's .mcp.json and global MCP "
                               'servers; only use servers from this app.',
                    'row_key': 0,
                },
            ]

    class Settings_Tabs(ConfigTabs):
        stretch = 1

        def __init__(self, parent):
            super().__init__(parent=parent)
            self.pages = {
                'Messages': ClaudeCodeSettings.Page_Messages(parent=self),
                'Tools': ClaudeCodeSettings.Page_Tools(parent=self),
                'Hooks': ClaudeCodeSettings.Page_Hooks(parent=self),
                'Voice': ClaudeCodeSettings.Page_Voice(parent=self),
            }

    class Page_Messages(ConfigFields):
        schema = [
            {
                'text': 'Model',
                'key': 'claude_model',
                'type': 'combo',
                'query': """
                    SELECT name, model_id FROM (
                        SELECT 'Default' AS name, '' AS model_id, 0 AS grp
                        UNION ALL
                        SELECT m.name, json_extract(m.config, '$._model_name'), 1
                        FROM models m
                        JOIN apis a ON a.id = m.api_id
                        WHERE a.name = 'Anthropic' AND m.kind = 'CHAT'
                    )
                    ORDER BY grp, name""",
                'fetch_keys': ('name', 'model_id'),
                'default': '',
                'width': 200,
                'row_key': 0,
            },
            {
                'text': 'Mode',
                'key': 'permission_mode',
                'type': (
                    'default', 'acceptEdits', 'plan',
                    'bypassPermissions', 'dontAsk', 'auto',
                ),
                'default': 'default',
                'width': 130,
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
                'row_key': 1,
            },
            {
                'text': 'Effort',
                'type': ('low', 'medium', 'high', 'xhigh', 'max'),
                'default': 'high',
                'width': 80,
                'has_toggle': True,
                'row_key': 1,
            },
            {
                'text': 'Max budget',
                'type': float,
                'minimum': 0.0,
                'maximum': 1000.0,
                'step': 0.5,
                'default': 1.0,
                'width': 70,
                'has_toggle': True,
                'tooltip': 'Stop the turn once it costs this many USD.',
                'row_key': 2,
            },
            {
                'text': 'Verbatim prompts',
                'type': bool,
                'default': False,
                'tooltip': 'Send prompts as written: no @path file '
                           'expansion or slash commands.',
                'row_key': 2,
            },
            {
                'text': 'System message',
                'key': 'sys_msg_mode',
                'type': ('APPEND', 'REPLACE'),
                'default': 'APPEND',
                'width': 90,
                'tooltip': "Append to Claude Code's default system prompt, "
                           'or replace it.',
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
    chat_bar_keys = ('claude_model', 'permission_mode', 'effort')

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
                            'PostToolUseFailure', 'PermissionRequest',
                            'UserPromptSubmit', 'Stop',
                            'SubagentStart', 'SubagentStop',
                            'PreCompact', 'Notification',
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
                            'event', '') in (
                                'PreToolUse', 'PostToolUse',
                                'PostToolUseFailure', 'PermissionRequest',
                            ),
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
                AgentTools(parent=self),
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
                        'default': True,
                        'row_key': 0,
                    },
                    {
                        'text': 'Edit',
                        'type': bool,
                        'default': True,
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
