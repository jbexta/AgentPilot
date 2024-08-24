from src.gui.config import ConfigTabs, ConfigFields, ConfigJsonTree
from src.system.sandboxes import Sandbox


class E2BSandbox(Sandbox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.languages = [
            'shell',
            'python',
        ]

    # region Filesystem
    def set_cwd(self, *args, **kwargs):
        raise NotImplementedError

    def list_directory(self, *args, **kwargs):
        raise NotImplementedError

    def create_directory(self, *args, **kwargs):
        raise NotImplementedError

    def write_file(self, *args, **kwargs):
        raise NotImplementedError

    def read_file(self, *args, **kwargs):
        raise NotImplementedError

    def upload_file(self, *args, **kwargs):
        raise NotImplementedError

    def download_file(self, *args, **kwargs):
        raise NotImplementedError
    # endregion

    # region Processes
    def start_process(self, *args, **kwargs):
        raise NotImplementedError

    def stop_process(self, *args, **kwargs):
        raise NotImplementedError
    # endregion


class E2BSandboxSettings(ConfigTabs):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pages = {
            'Messages': self.Page_Chat_Messages(parent=self),
            'Env vars': self.Page_Env_Vars(parent=self),
        }

    class Page_Env_Vars(ConfigJsonTree):
        def __init__(self, parent):
            super().__init__(parent=parent,
                             add_item_prompt=('NA', 'NA'),
                             del_item_prompt=('NA', 'NA'))
            self.parent = parent
            self.conf_namespace = 'env_vars'
            self.schema = [
                {
                    'text': 'Variable',
                    'type': str,
                    'width': 120,
                    'default': 'Variable name',
                },
                {
                    'text': 'Value',
                    'type': str,
                    'stretch': True,
                    'default': '',
                },
            ]

    class Page_Chat_Messages(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.conf_namespace = 'chat'
            self.schema = [
                {
                    'text': 'Model',
                    'type': 'ModelComboBox',
                    'default': 'mistral/mistral-large-latest',
                    'row_key': 0,
                },
                {
                    'text': 'Display markdown',
                    'type': bool,
                    'default': True,
                    'row_key': 0,
                },
                {
                    'text': 'System message',
                    'key': 'sys_msg',
                    'type': str,
                    'num_lines': 8,
                    'default': '',
                    'width': 520,
                    'label_position': 'top',
                },
                {
                    'text': 'Max messages',
                    'type': int,
                    'minimum': 1,
                    'maximum': 99,
                    'default': 10,
                    'width': 60,
                    'has_toggle': True,
                    'row_key': 1,
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
                    'text': 'Consecutive responses',
                    'key': 'on_consecutive_response',
                    'type': ('PAD', 'REPLACE', 'NOTHING'),
                    'default': 'REPLACE',
                    'width': 90,
                    'row_key': 2,
                },
                {
                    'text': 'User message',
                    'key': 'user_msg',
                    'type': str,
                    'num_lines': 2,
                    'default': '',
                    'width': 520,
                    'label_position': 'top',
                    'tooltip': 'Text to override the user/input message. When empty, the default user/input message is used.',
                },
            ]