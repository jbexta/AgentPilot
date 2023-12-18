

class SandboxManager:
    def __init__(self):
        pass

    def load(self):
        pass


class Sandbox:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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
