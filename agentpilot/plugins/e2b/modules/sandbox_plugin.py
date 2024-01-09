from agentpilot.system.sandboxes import Sandbox


class E2bSandbox(Sandbox):
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
