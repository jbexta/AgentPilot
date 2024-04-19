import json
from src.utils import sql


class FileManager:
    def __init__(self):
        self.file_exts = {}

    def load(self):
        self.load_file_exts()

    def load_file_exts(self):
        self.file_exts = sql.get_results("""
            SELECT
                name,
                config
            FROM file_exts""", return_type='dict')
        for k, v in self.file_exts.items():
            self.file_exts[k] = json.loads(v)

    def to_dict(self):
        return self.file_exts

    def get_ext_config(self, ext):
        return self.file_exts.get(ext, {})
