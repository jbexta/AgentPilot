import json
import os.path
import re
import sqlite3
import threading
from contextlib import contextmanager

from numpy.core.defchararray import upper
from packaging import version

from src.utils.helpers import convert_to_safe_case

sql_thread_lock = threading.Lock()

DB_FILEPATH = None  # None will use default
WRITE_TO_COPY = False


@contextmanager
def write_to_copy():
    """Context manager to write to db copy."""
    global WRITE_TO_COPY
    try:
        WRITE_TO_COPY = True
        yield
    finally:
        WRITE_TO_COPY = False


def set_db_filepath(path: str):
    global DB_FILEPATH
    DB_FILEPATH = path


def get_db_path():
    from src.utils.filesystem import get_application_path
    # Check if we're running as a script or a frozen exe
    if DB_FILEPATH:
        application_path = DB_FILEPATH
    # elif getattr(sys, 'frozen', False):
    #     application_path = get_application_path()
    else:
        # application_path = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir))
        application_path = get_application_path()

    path = os.path.join(application_path, 'data.db')
    if WRITE_TO_COPY:
        path = path + '.copy'
    return path


def execute(query, params=None):
    with sql_thread_lock:
        db_path = get_db_path()
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            cursor.close()
            return cursor.lastrowid


def get_results(query, params=None, return_type='rows', incl_column_names=False):
    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        if params:
            param_list = [
                p() if callable(p) else p
                for p in params
            ]
            cursor.execute(query, param_list)
        else:
            cursor.execute(query)

        rows = cursor.fetchall()
        cursor.close()

    col_names = [description[0] for description in cursor.description]

    # Return the rows
    if return_type == 'list':
        ret_val = [row[0] for row in rows]
    elif return_type == 'dict':
        ret_val = {row[0]: row[1] for row in rows}
    elif return_type == 'hdict':
        # use col names as keys and first row as values
        if len(rows) == 0:
            return None
        ret_val = {col_names[i]: rows[0][i] for i in range(len(col_names))}
    elif return_type == 'htuple':
        if len(rows) == 0:
            return None
        ret_val = rows[0]
    else:
        ret_val = rows

    if incl_column_names:
        return ret_val, col_names
    else:
        return ret_val


def get_scalar(query, params=None, return_type='single', load_json=False):
    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
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


def check_database_upgrade():
    from src.utils.sql_upgrade import upgrade_script
    db_path = get_db_path()
    if not os.path.isfile(db_path):
        raise Exception(f'No database found in {db_path}. Please make sure `data.db` is located in the same directory as this executable.')

    db_version_str = get_scalar("SELECT value as app_version FROM settings WHERE `field` = 'app_version'")
    db_version = version.parse(db_version_str)
    source_version = list(upgrade_script.versions.keys())[-1]
    source_version = version.parse(source_version)
    if db_version > source_version:
        raise Exception('The database originates from a newer version of Agent Pilot. Please download the latest version from github.')
    elif db_version < source_version:
        return db_version
    else:
        return None


def execute_multiple(queries, params_list):
    with sql_thread_lock:
        db_path = get_db_path()
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            try:
                for query, params in zip(queries, params_list):
                    cursor.execute(query, params)
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise
            finally:
                cursor.close()


def define_table(table_name):
    if not table_name:
        return
    exists = get_scalar(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
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
                "name"	TEXT NOT NULL DEFAULT '',
                "kind"	TEXT NOT NULL DEFAULT '',
                "config"	TEXT NOT NULL DEFAULT '{{}}',
                "metadata"	TEXT NOT NULL DEFAULT '{{}}',
                "folder_id"	INTEGER DEFAULT NULL,
                "pinned"	INTEGER DEFAULT 0,
                "ordr"	INTEGER DEFAULT 0,
                PRIMARY KEY("id" AUTOINCREMENT)
        )
    """
    execute(create_schema)


def ensure_column_in_tables(tables, column_name, column_type, default_value=None, not_null=False, unique=False, force_tables=None):
    for table in tables:
        table_exists = get_scalar(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
        if not table_exists:
            continue

        column_cnt = get_scalar(f"SELECT COUNT(*) FROM pragma_table_info('{table}') WHERE name = ?", (column_name,))
        column_exists = column_cnt > 0
        if column_exists and table not in (force_tables or []):
            continue

        def_value = default_value
        if isinstance(default_value, str) and default_value != 'NULL' and not default_value.startswith('('):
            def_value = f'"{default_value}"'
        default_str = f'DEFAULT {def_value}' if def_value else ''
        not_null_str = 'NOT NULL' if not_null else ''
        unique_str = 'UNIQUE' if unique else ''

        try:
            if unique:
                raise Exception("Unique constraint can't be added like this")
            execute(f"ALTER TABLE {table} ADD COLUMN `{column_name}` {column_type} {not_null_str} {default_str}")
            continue
        except Exception as e:
            pass

        old_table_create_stmt = get_scalar(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}'")  # todo dirty

        rebuilt_create_stmt_without_column = ''
        for line in old_table_create_stmt.split('\n'):
            if f'"{column_name}"' in line:
                continue
            rebuilt_create_stmt_without_column += line + '\n'

        new_create_stmt = rebuilt_create_stmt_without_column.replace('PRIMARY KEY', f'"{column_name}" {column_type} {default_str} {unique_str},\n\t\t\t\tPRIMARY KEY')
        execute(new_create_stmt.replace(f'CREATE TABLE "{table}"', f'CREATE TABLE "{table}_new"'))

        # insert all data except for the new column
        old_table_columns = get_results(f"PRAGMA table_info({table})")
        old_table_columns = [col[1] for col in old_table_columns if (col[1] != column_name or column_exists)]
        insert_stmt = f"INSERT INTO `{table}_new` (`{'`, `'.join(old_table_columns)}`) SELECT `{'`, `'.join(old_table_columns)}` FROM `{table}`"
        execute(insert_stmt)
        execute(f"DROP TABLE `{table}`")
        execute(f"ALTER TABLE `{table}_new` RENAME TO `{table}`")
        # execute(f"""
        #     CREATE TABLE IF NOT EXISTS "{convert_to_safe_case(new_table_name)}" AS SELECT * FROM "{table}"
        # """)