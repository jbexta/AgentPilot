import platform
import subprocess
import time
import os
from toolkits.filesystem import type_string
from operations.action import BaseAction, ActionInput, ActionSuccess
from operations.parameters import *
import pyautogui


# SPLIT SCREEN
# SWITCH WINDOW


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
                yield ActionSuccess("[SAY] the window couldn't be minimized because the OS is unknown.")

            yield ActionSuccess("[SAY] The window has been minimized.")
        except Exception as e:
            yield ActionSuccess("[SAY] There was an error minimizing the window.")


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
            yield ActionSuccess("[SAY] The window has been closed, in the style of {char_name}.")
        except Exception as e:
            yield ActionSuccess("[SAY] There was an error closing the window.")
