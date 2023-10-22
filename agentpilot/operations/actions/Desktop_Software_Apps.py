import difflib
import os
import platform
import re
import subprocess

from utils.apis import llm
from operations.action import BaseAction, ActionSuccess


class Open_Desktop_Software(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='what time does eastenders start')
        self.desc_prefix = 'requires me to'
        self.desc = 'Open a desktop software application on the users machine'
        self.inputs.add('name-of-software-that-was-requested-to-be-opened')

    def run_action(self):
        try:
            # GET INSTALLED APPS
            sys_platform = platform.system()
            if sys_platform == 'Windows':
                command = 'Get-WmiObject -Class Win32_Product | Select-Object Name'
                result = subprocess.run(['powershell', '-Command', command], capture_output=True, text=True)
                installed_apps = {app: '' for app in result.stdout.split('\n')}

            elif sys_platform == 'Linux':
                folder_paths = [
                    "/usr/share/applications/",
                    os.path.expanduser("~/.local/share/applications/")
                ]
                installed_apps = {
                    filename.replace('.desktop', ''): os.path.join(path, filename)
                    for path in folder_paths
                    if os.path.exists(path)
                    for filename in os.listdir(path)
                    if filename.endswith(".desktop")
                }
                # # user_home = os.path.expanduser("~")
                # # cache_dir = os.path.join(user_home, ".cache")
                # #
                # # if os.path.exists(cache_dir):
                # #     command = 'grep -r "Package:" {}/apt/pkgcache.bin | cut -d: -f2'.format(cache_dir)
                # command = 'dpkg-query -W -f=\'${Package}\n\''
                # result = subprocess.run(command, shell=True, capture_output=True, text=True)
                # installed_apps = result.stdout.split('\n')
                # # else:
                # #     installed_apps = []

            else:
                raise NotImplementedError('Platform is not yet supported for this action')

            open_software_name = self.inputs.get('name-of-software-that-was-requested-to-be-opened').value
            closest_apps = difflib.get_close_matches(open_software_name, installed_apps.keys(), cutoff=0.5, n=15)
            app_str = ',\n'.join(f'{closest_apps.index(app) + 1}: {app}' for app in closest_apps)
            conversation_str = self.agent.context.message_history.get_conversation_str(msg_limit=2)
            response = llm.get_scalar(f"""
Input = `{open_software_name}`
Analyze the provided software list and conversation and return the most relevant ID that most closely matches the input `{open_software_name}`.

SOFTWARE LIST:
ID: Description
____________________
0: No software is relevant to the input
{app_str}

Use the following conversation to guide your analysis. The last user message (denoted with arrows ">> ... <<") is the message you will use to determine the appropriate ID.

{conversation_str}

TASK:
Examine the conversation in detail, applying logic and reasoning to ascertain the most fitting ID based on the latest user message. 
If no software from the list is even slightly relevant to the conversation and not based on the last user message, simply output "0". 

The detected ID is:
""").lower()
            response = re.sub(r'[^0-9,]', '', response)
            found_ids = [int(x) for x in response.split(',') if x != '' and int(x) > 0]
            found_apps = [closest_apps[x - 1] for x in found_ids if x <= len(closest_apps)]

            open_app_name = str(found_apps[0])

            if sys_platform == 'Windows':
                os.system(f'start {open_app_name}')

            elif sys_platform == 'Linux':
                # files_command = f"dpkg-query -L {open_app_name}"
                # files_result = subprocess.run(files_command, shell=True, capture_output=True, text=True)
                # files_list = files_result.stdout.strip().split('\n')
                #
                # # Filter for executable files
                # executable_paths = [file_path for file_path in files_list if file_path.startswith('/usr/bin/')]
                app_path = installed_apps[open_app_name]

                with open(app_path, 'r') as file:
                    for line in file:
                        if line.startswith("Exec="):
                            # Get the command after "Exec="
                            command = line.split("=", 1)[1].strip()

                            # Handle possible arguments in the Exec line like %U, %f, etc.
                            command = command.split(' ')[0]

                            # os.system(command)
                            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
                # desktop_env = os.environ.get('XDG_CURRENT_DESKTOP').upper()
                # if desktop_env == 'GNOME':
                #     os.system(f'gnome-open "{app_path}"')
                # elif desktop_env == 'KDE':
                #     os.system(f'{app_path.lower().replace(" ", "-")}')
                # elif desktop_env == 'MATE':
                #     os.system(f'{app_path}')
                #     # os.system(f'xdg-open "{app_path}"')
                # else:
                #     raise NotImplementedError(f'Platform is not yet supported for this action: {desktop_env}')
            else:
                yield ActionSuccess(f'[SAY] "Sorry, I cannot open software programs on {sys_platform}."')

            yield ActionSuccess(f'[SAY] "Opening {open_app_name}".')

        except Exception as e:
            yield ActionSuccess('[SAY] "There was an error starting the app"')
