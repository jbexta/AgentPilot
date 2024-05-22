from src.system.vectordbs import VectorDB


class OpenAI_VectorDB(VectorDB):
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

