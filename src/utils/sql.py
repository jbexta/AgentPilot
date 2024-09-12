import os.path
import sqlite3
import sys
import threading
from contextlib import contextmanager

from packaging import version

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


def get_scalar(query, params=None):
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
        return row[0]


def check_database_upgrade():
    from src.utils.sql_upgrade import upgrade_script
    db_path = get_db_path()
    if not os.path.isfile(db_path):
        print("Db path not found: ", db_path)
        raise Exception('NO_DB')

    db_version_str = get_scalar("SELECT value as app_version FROM settings WHERE field = 'app_version'")
    db_version = version.parse(db_version_str)
    source_version = list(upgrade_script.versions.keys())[-1]
    source_version = version.parse(source_version)
    if db_version > source_version:
        raise Exception('OUTDATED_APP')
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
