from pynput.keyboard import Key

from openagent.operations.action import BaseAction, ActionResult
from openagent.toolkits.filesystem import press_keys


class Copy_To_Clipboard(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='copy this')
        self.desc_prefix = 'requires me to'
        self.desc = 'Copy something to the clipboard'

    def run_action(self):
        press_keys([Key.ctrl.value, 'c'])
        yield ActionResult('[SAY] "Copied to clipboard"')


class Paste_From_Clipboard(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='paste here')
        self.desc_prefix = 'requires me to'
        self.desc = 'Paste something from the clipboard'

    def run_action(self):
        press_keys([Key.ctrl.value, 'v'])
        yield ActionResult('')


class Cut_To_Clipboard(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='cut this')
        self.desc_prefix = 'requires me to'
        self.desc = 'Cut something to the clipboard'

    def run_action(self):
        press_keys([Key.ctrl.value, 'x'])
        yield ActionResult('')