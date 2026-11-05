
import os.path
from contextlib import contextmanager
from packaging import version

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


@contextmanager
def write_to_file(filepath):
    """Context manager to write to db copy."""
    global DB_FILEPATH
    current_filepath = DB_FILEPATH
    try:
        DB_FILEPATH = filepath
        yield
    finally:
        DB_FILEPATH = current_filepath


def set_db_filepath(path: str):
    global DB_FILEPATH
    DB_FILEPATH = path


def get_db_path():
    from utils.filesystem import get_application_path
    global DB_FILEPATH
    # Check if we're running as a script or a frozen exe
    if DB_FILEPATH:
        return DB_FILEPATH
    # elif getattr(sys, 'frozen', False):
    #     application_path = get_application_path()
    else:
        # application_path = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir))
        application_path = get_application_path()

    path = os.path.join(application_path, 'data.db')
    if WRITE_TO_COPY:
        path = path + '.copy'
    return path


# POINT TO sqlite.py
def execute(query, params=None, connector=None):
    if connector is None:
        from core.connectors.sqlite import SqliteConnector
        connector = SqliteConnector(db_path=get_db_path())
    return connector.execute(query, params)


def execute_many(statements, connector=None):
    if connector is None:
        from core.connectors.sqlite import SqliteConnector
        connector = SqliteConnector(db_path=get_db_path())
    return connector.execute_many(statements)


def get_results(query, params=None, return_type='rows', incl_column_names=False, connector=None):
    if connector is None:
        from core.connectors.sqlite import SqliteConnector
        connector = SqliteConnector(db_path=get_db_path())
    return connector.get_results(query, params, return_type, incl_column_names)


def get_scalar(query, params=None, return_type='single', load_json=False, connector=None):
    if connector is None:
        from core.connectors.sqlite import SqliteConnector
        connector = SqliteConnector(db_path=get_db_path())
    return connector.get_scalar(query, params, return_type, load_json)


def check_database_upgrade():
    from utils.sql_upgrade import upgrade_script
    db_path = get_db_path()
    blank_db_path = os.path.join(os.path.dirname(db_path), 'blank.db')
    if not os.path.isfile(db_path) and os.path.isfile(blank_db_path):
        os.rename(blank_db_path, db_path)
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


def define_table(table_name, relations=None, connector=None):
    if connector is None:
        from core.connectors.sqlite import SqliteConnector
        connector = SqliteConnector(db_path=get_db_path())
    return connector.define_table(table_name, relations)


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

        old_table_create_stmt = get_scalar(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}'")

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