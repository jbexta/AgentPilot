from agentpilot.utils import sql


class BlockManager:
    def __init__(self):
        self.blocks = {}

    def load(self):
        self.blocks = sql.get_results("""
            SELECT
                name,
                text
            FROM blocks""", return_type='dict')

    def to_dict(self):
        return self.blocks
