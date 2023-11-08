import os.path
import sqlite3
import sys
import threading


sql_thread_lock = threading.Lock()


def get_db_path():
    from agentpilot.utils.filesystem import get_application_path
    # Check if we're running as a script or a frozen exe
    if getattr(sys, 'frozen', False):
        application_path = get_application_path()
    else:
        application_path = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir))

    ret = os.path.join(application_path, 'data.db')
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
        with sqlite3.connect(db_path) as conn:
            # Create a cursor object
            cursor = conn.cursor()

            # Execute the query
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            # Commit the changes
            # conn.commit()

            # Close the cursor and connection
            cursor.close()
            # conn.close()
            return cursor.lastrowid


def get_results(query, params=None, return_type='rows', incl_column_names=False):
    # Connect to the database
    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
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
        # conn.close()

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
    # Connect to the database
    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
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
        # conn.close()

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


def execute_multiple(queries, params_list):
    with sql_thread_lock:
        # Connect to the database
        db_path = get_db_path()
        with sqlite3.connect(db_path) as conn:
            # try:
                # Create a cursor object
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
                # # Execute the query
                # cursor.executemany(query, params_list)

                # # Get the last row id if needed (might not be useful with executemany)
                # lastrowid = cursor.lastrowid

                # Commit the changes
                # conn.commit()

            # finally:
            #     # Close the cursor and connection
            #     cursor.close()
            #     # conn.close()

            # # Return the last row id
            # return lastrowid


def deactivate_all_branches_with_msg(msg_id):  # todo - get these into a transaction
    execute("""
        UPDATE contexts
        SET active = 0
        WHERE branch_msg_id = (
            SELECT branch_msg_id
            FROM contexts
            WHERE id = (
                SELECT context_id
                FROM contexts_messages
                WHERE id = ?
            )
        );""", (msg_id,))

def activate_branch_with_msg(msg_id):
    execute("""
        UPDATE contexts
        SET active = 1
        WHERE id = (
            SELECT context_id
            FROM contexts_messages
            WHERE id = ?
        );""", (msg_id,))
