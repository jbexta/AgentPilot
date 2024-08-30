from src.gui.config import ConfigTabs, ConfigFields, ConfigJsonTree
from src.system.environments import Environment
from src.utils.helpers import convert_model_json_to_obj


class E2BEnvironment(Environment):
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
            # 'Messages': self.Page_Chat_Messages(parent=self),
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
