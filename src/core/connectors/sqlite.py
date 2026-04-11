##
import json
import sqlite3
import threading
from decimal import Decimal

# Register adapter to allow Decimal values in query parameters
sqlite3.register_adapter(Decimal, str)

sql_thread_lock = threading.Lock()


class SqliteConnector:
    def __init__(self, db_path=None):
        self._db_path = db_path

    @property
    def db_path(self):
        if self._db_path:
            return self._db_path
        from utils.sql import get_db_path
        return get_db_path()

    def execute(self, query, params=None):
        with sql_thread_lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)

                cursor.close()
                return cursor.lastrowid

    def get_results(self, query, params=None, return_type='rows', incl_column_names=False):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            if isinstance(params, (list, tuple)):
                param_list = [
                    p() if callable(p) else p
                    for p in params
                ]
                cursor.execute(query, param_list)
            elif isinstance(params, dict):
                param_dict = {
                    k: v() if callable(v) else v
                    for k, v in params.items()
                }
                cursor.execute(query, param_dict)
            else:
                cursor.execute(query)

            rows = cursor.fetchall()
            cursor.close()

        col_names = [description[0] for description in cursor.description]

        if return_type == 'list':
            ret_val = [row[0] for row in rows]
        elif return_type == 'dict':
            ret_val = {row[0]: row[1] for row in rows}
        elif return_type == 'hdict':
            # use col names as keys and first row as values
            if len(rows) == 0:
                return None
            ret_val = {col_names[i]: rows[0][i] for i in range(len(col_names))}
        elif return_type == 'tuple':
            if len(rows) == 0:
                return None
            ret_val = rows[0]
        else:
            ret_val = rows

        if incl_column_names:
            return ret_val, col_names
        else:
            return ret_val

    def get_scalar(self, query, params=None, return_type='single', load_json=False):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            row = cursor.fetchone()
            cursor.close()

            if row is None:
                return None

            if return_type == 'single':
                return row[0] if not load_json else json.loads(row[0])
            elif return_type == 'tuple':
                return row
            else:
                raise Exception(f"Unknown return type: {return_type}")

    def define_table(self, table_name, relations=None):
        from utils.helpers import convert_to_safe_case
        if not table_name:
            return
        exists = self.get_scalar(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        if exists:
            return
        create_schema = f"""
            CREATE TABLE IF NOT EXISTS "{convert_to_safe_case(table_name)}" (
                "id"	INTEGER,
                "uuid"	TEXT DEFAULT (
                    lower(hex(randomblob(4))) || '-' ||
                    lower(hex(randomblob(2))) || '-' ||
                    '4' || substr(lower(hex(randomblob(2))), 2) || '-' ||
                    substr('89ab', abs(random()) % 4 + 1, 1) || substr(lower(hex(randomblob(2))), 2) || '-' ||
                    lower(hex(randomblob(6)))
                ) UNIQUE,
                {' '.join([f'"{rel}" INTEGER,' for rel in relations]) if relations else ''}
                "name"	TEXT NOT NULL DEFAULT '',
                "kind"	TEXT NOT NULL DEFAULT '',
                "config"	TEXT NOT NULL DEFAULT '{{}}',
                "metadata"	TEXT NOT NULL DEFAULT '{{}}',
                "parent_id"	INTEGER DEFAULT NULL,
                "folder_id"	INTEGER DEFAULT NULL,
                "pinned"	INTEGER DEFAULT 0,
                "baked"	INTEGER DEFAULT 0,
                "ordr"	INTEGER DEFAULT 0,
                PRIMARY KEY("id" AUTOINCREMENT)
            )
        """
        # print(create_schema)
        self.execute(create_schema)