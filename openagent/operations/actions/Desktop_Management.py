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


class Set_Desktop_Background(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='set desktop background to an image of a dog')
        self.desc_prefix = 'requires me to'
        self.desc = 'Change the desktop background.'
        self.inputs.add('image-to-set-the-background-to', fvalue=ImageFValue)

    def run_action(self):
        try:
            image_path = self.inputs.get('image')
            # other set desktop settings

            # Change desktop background on Windows
            sys_platform = platform.system()
            if sys_platform == 'Windows':
                import ctypes
                SPI_SETDESKWALLPAPER = 20
                ctypes.windll.user32.SystemParametersInfoW(SPI_SETDESKWALLPAPER, 0, image_path, 3)

            # Change desktop background on macOS
            elif sys_platform == 'Darwin':
                script = f"""osascript -e 'tell application "Finder" to set desktop picture to POSIX file "{image_path}"'"""
                os.system(script)

            # Change desktop background on Linux
            elif sys_platform == 'Linux':
                dektop_env = os.environ.get('XDG_CURRENT_DESKTOP').upper()
                if dektop_env == 'GNOME':
                    # The code below uses the method for GNOME desktop environment.
                    os.system(f"gsettings set org.gnome.desktop.background picture-uri file://{image_path}")
                elif dektop_env == 'KDE':
                    # The code below uses the method for KDE desktop environment.
                    os.system(f"""qdbus org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript 'string: var Desktops = desktops(); \
                    for (i=0;i<Desktops.length;i++) \
                    {{" \
                    d = Desktops[i]; \
                    d.wallpaperPlugin = "org.kde.image"; \
                    d.currentConfigGroup = Array("Wallpaper", "org.kde.image", "General"); \
                    d.writeConfig("Image", "file://{image_path}"); \
                    }}'""")
                elif dektop_env == 'MATE':
                    # The code below uses the method for MATE desktop environment.
                    os.system(f"""gsettings set org.mate.background picture-filename {image_path}""")
                elif dektop_env == 'XFCE':
                    # The code below uses the method for XFCE desktop environment.
                    os.system(f"""xfconf-query -c xfce4-desktop -p /backdrop/screen0/monitor0/workspace0/last-image -s {image_path}""")

            else:
                yield ActionResult("[SAY] The desktop background couldn't be changed because the OS is unknown, speaking as {char_name}.")

            yield ActionResult("[SAY] The desktop background has been changed to an image of a dog, speaking as {char_name}.")
        except Exception as e:
            yield ActionResult("[SAY] There was an error changing the desktop background.")
