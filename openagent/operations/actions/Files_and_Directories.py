import os
import platform
import subprocess
from openagent.operations.action import ActionResult, ActionInput, BaseAction, ActionInputCollection


# OPEN FILE
# CREATE FILE

class Open_Directory_Or_File(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='open the directory')
        self.desc_prefix = 'requires me to'
        self.desc = 'Open a directory or file on the system'
        self.inputs.add('full_path_to_open', examples=['/path/to/directory', 'C:\\path\\to\\directory'])

    def run_action(self):
        directory_path = self.inputs.get(0).value

        if platform.system() == 'Windows':
            # Windows
            command = 'explorer'
            args = [directory_path]
        elif platform.system() == 'Darwin':
            # macOS
            command = 'open'
            args = [directory_path]
        else:
            # Linux
            command = 'xdg-open'
            args = [directory_path]

        try:
            subprocess.run([command] + args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            yield ActionResult(f'[SAY] "Opened the directory at {directory_path}"')
        except subprocess.CalledProcessError:
            yield ActionResult(f'[SAY] "Failed to open the directory at {directory_path}"')
        except Exception as e:
            yield ActionResult(f'[SAY] "An error occurred while opening the directory: {str(e)}"')


class DeleteFile(BaseAction):
    def __init__(self, agent):
        super().__init__(agent)
        self.desc_prefix = 'requires me to'
        self.desc = "Delete a file"
        self.inputs = ActionInputCollection([
            ActionInput('path-of-file-to-delete')
        ])

    def run_action(self):
        filepath = self.inputs.get('path-of-file-to-delete').value
        if not os.path.exists(filepath):
            yield ActionResult('[SAY] "The file does not exist"')
        else:
            self.inputs.add('are-you-sure-you-want-to-delete', format='Boolean (True/False)')
            yield ActionResult(f' file "{filepath}"? [MI]')

            if self.inputs.get('are-you-sure-you-want-to-delete').value.lower() == 'true':
                try:
                    os.remove(filepath)
                    yield ActionResult(f'[SAY] "File was deleted ({filepath})"')
                except Exception as e:
                    yield ActionResult(f'[SAY] "There was an error deleting the file ({filepath})"')
            else:
                yield ActionResult('[SAY] "Deletion was cancelled"')


class AnalyseFile(BaseAction):
    def __init__(self, agent):
        super().__init__(agent)
        self.desc_prefix = 'requires me to'
        self.desc = "Analyse/Interpret a file"
        self.inputs = ActionInputCollection([
            ActionInput('path-of-file-to-analyse')
        ])

    def run_action(self):
        yield ActionResult('[SAY] "Analysing file"')
