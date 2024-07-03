import json
from src.utils import sql


class VectorDBManager:
    def __init__(self, parent):
        self.parent = parent
        self.vec_dbs = {}

    def load(self):
        self.vec_dbs = sql.get_results("""
            SELECT
                name,
                config -- json_extract(config, '$.data')
            FROM vectordbs""", return_type='dict')
        self.vec_dbs = {k: json.loads(v) for k, v in self.vec_dbs.items()}

    def to_dict(self):
        return self.vec_dbs


class VectorDB:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def create_vec_store(self, *args, **kwargs):
        raise NotImplementedError

    def list_vec_stores(self, *args, **kwargs):
        raise NotImplementedError

    def get_vec_store(self, *args, **kwargs):
        raise NotImplementedError

    def delete_vec_store(self, *args, **kwargs):
        raise NotImplementedError

