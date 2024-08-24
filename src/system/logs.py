import json
from datetime import datetime

from src.utils import sql


class LogManager:
    def __init__(self, parent):
        self.parent = parent
        # self.logs = {}

    def new_log(self, log_type, additional_data=None):
        timestamp = datetime.now().isoformat()

        data = {
            'timestamp': timestamp,
            'type': log_type,
        }
        if additional_data:
            data.update(additional_data)

        sql.execute("""
            INSERT INTO logs (name, config)
            VALUES (?, ?)
        """, (log_type, json.dumps(data)))
