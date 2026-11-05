from typing import Dict, Any

from gui import system
from plugins.workflows.members import Member
from utils.helpers import set_module_type


@set_module_type(module_type='Members', settings='set_variable_settings')
class SetVariable(Member):
    """Saves a global variable, usable as `{{ variable }}` in any template,
    in this and later runs."""
    default_avatar = ':/resources/icon-notif.png'
    default_name = 'Set Variable'
    workflow_insert_mode = 'single'
    OUTPUT = None

    @property
    def INPUTS(self):
        return {
            'CONFIG': {
                'variable': str,
                'value': str,
            },
        }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.receivable_function = None

    async def run(self):
        name = self.config.get('variable', '').strip()
        if not name:
            raise ValueError('Set Variable needs a variable name')
        value = await self.format_config_value('value')
        system.manager.variables[name] = value
        self.workflow.save_message('sys', f'Set `{name}` to: {value}', self.full_member_id())
        yield 'SYS', 'SKIP'  # todo not needed anymore
