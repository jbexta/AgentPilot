import platform
import subprocess
import time
import os
from openagent.toolkits.filesystem import type_string
from openagent.operations.action import BaseAction, ActionInput, ActionResult
from openagent.operations.fvalues import *
import pyautogui


# SPLIT SCREEN
# SWITCH WINDOW
group_id = 'desktop'


class MinimizeWindow(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='minimize window')
        self.desc_prefix = 'requires me to'
        self.desc = 'Minimize the active window'

    def run_action(self):
        try:
            # minimise on win
            if platform.platform().startswith('Windows'):
                pyautogui.hotkey('win', 'down')
            # minimise on mac
            elif platform.platform().startswith('Darwin'):
                pyautogui.hotkey('command', 'm')
            # minimise on linux
            elif platform.platform().startswith('Linux'):
                pyautogui.hotkey('alt', 'space')
                pyautogui.press('n')
            else:
                yield ActionResult("[SAY] the window couldn't be minimized because the OS is unknown, speaking as {char_name}.")

            yield ActionResult("[SAY] The window has been minimized, speaking as {char_name}.")
        except Exception as e:
            yield ActionResult("[SAY] There was an error minimizing the window.")


class CloseWindow(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='close window')
        self.desc_prefix = 'requires me to'
        self.desc = 'Close the active window'

    def run_action(self):
        try:
            # minimise on win
            pyautogui.hotkey('alt', 'f4')
            # if self.agent.platform == 'debian':
            # elif self.agent.platform == 'win':
            #     pyautogui.hotkey('alt', 'f4')
            # else:
            #     yield ActionResult("[SAY] the window couldn't be closed because the OS is unknown, in the style of {char_name}.")
            yield ActionResult("[SAY] The window has been closed, in the style of {char_name}.")
        except Exception as e:
            yield ActionResult("[SAY] There was an error closing the window.")


class Type_Text(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='type hello here')
        self.desc_prefix = 'requires me to'
        self.desc = "Type text on the screen"
        self.inputs.add('what_to_type', required=True)

    def run_action(self):
        time.sleep(2)
        type_string(self.inputs.get(0).value)
        return True
