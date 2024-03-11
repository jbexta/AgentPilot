from src.utils import sql


class BlockManager:
    def __init__(self):
        self.blocks = {}

    def load(self):
        self.blocks = sql.get_results("""
            SELECT
                name,
                json_extract(config, '$.data')
            FROM blocks""", return_type='dict')
        pass

    def to_dict(self):
        return self.blocks

    def new_block(self, name, text):
        pass
        # sql.execute("""
        #     INSERT INTO blocks (name, text)
        #     VALUES (?, ?)""", (name, text))

    def delete_block(self, name):
        pass
        # sql.execute("""
        #     DELETE FROM blocks
        #     WHERE name = ?""", (name,))