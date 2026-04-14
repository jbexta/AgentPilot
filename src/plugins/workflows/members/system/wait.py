from typing import Dict, Any, Union

from plugins.workflows.members import Member
from utils.helpers import set_module_type
import asyncio


@set_module_type(module_type='Members', settings='wait_settings')
class Wait(Member):
    default_avatar = ':/resources/icon-wait.png'
    default_name = 'Wait'
    workflow_insert_mode = 'single'
    OUTPUT = None

    @property
    def INPUTS(self):
        return {
            'CONFIG': {
                'duration': float,  # seconds
                'unit': str,        # 'seconds', 'minutes', etc. (optional)
            },
        }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    async def run(self):
        duration = self.config.get('duration', 1)
        unit = self.config.get('unit', 'seconds')
        # Convert to seconds if needed
        if unit == 'minutes':
            duration = duration * 60
        elif unit == 'hours':
            duration = duration * 3600
        # else assume seconds
        print(f'Waiting for {duration} {unit}')
        await asyncio.sleep(duration)
        print(f'Waited for {duration} {unit}')
        self.workflow.save_message('sys', f'Waited for {duration} {unit}', self.full_member_id())
        yield 'SYS', 'SKIP'

    # async def run(self):