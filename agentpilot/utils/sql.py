import os.path
import sqlite3
import sys
import threading


sql_thread_lock = threading.Lock()


def get_db_path():
    from agentpilot.utils.filesystem import get_application_path
    # Check if we're running as a script or a frozen exe
    if getattr(sys, 'frozen', False):
        application_path = get_application_path()  # os.path.dirname(sys.executable)
    else:
        # config_file = os.path.join(cwd, '..', '..', 'configuration.yaml')
        application_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')

    ret = os.path.join(application_path, 'data.db')
    print(ret)
    return ret


# def get_db_path():
#     db_path = config.get_value('system.db_path')
#     # if db_path.startswith('.'):
#     #     filename = db_path[1:]
#     #     db_path = os.path.join(os.getcwd(), filename)
#     return db_path


def execute(query, params=None):
    with sql_thread_lock:
        # Connect to the database
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)

        # Create a cursor object
        cursor = conn.cursor()

        # Execute the query
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        # Commit the changes
        conn.commit()

        # Close the cursor and connection
        cursor.close()
        conn.close()
        return cursor.lastrowid


def get_results(query, params=None, return_type='rows', incl_column_names=False):
    # Connect to the database
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)

    # Create a cursor object
    cursor = conn.cursor()

    # Execute the query
    if params:
        cursor.execute(query, params)
    else:
        cursor.execute(query)

    # Fetch all the rows as a list of tuples
    rows = cursor.fetchall()

    # Close the cursor and connection
    cursor.close()
    conn.close()

    # Return the rows
    if return_type == 'list':
        ret_val = [row[0] for row in rows]
    elif return_type == 'dict':
        ret_val = {row[0]: row[1] for row in rows}
    elif return_type == 'rtuple':
        if len(rows) == 0:
            return None
        ret_val = rows[0]
    else:
        ret_val = rows

    if incl_column_names:
        return ret_val, [description[0] for description in cursor.description]
    else:
        return ret_val


def get_scalar(query, params=None):
    # Connect to the database
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)

    # Create a cursor object
    cursor = conn.cursor()

    # Execute the query
    if params:
        cursor.execute(query, params)
    else:
        cursor.execute(query)

    # Fetch the first row
    row = cursor.fetchone()

    # Close the cursor and connection
    cursor.close()
    conn.close()

    if row is None:
        return None
    return row[0]


def check_database():
    db_path = get_db_path()
    file_exists = os.path.isfile(db_path)
    if not file_exists:
        return False
    try:
        app_ver = get_scalar("SELECT value as app_version FROM settings WHERE field = 'app_version'")
        if app_ver is None:
            return False
        return True
    except Exception as e:
        print(e)
        return False
