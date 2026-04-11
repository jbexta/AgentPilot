
import json
import os
import threading
import time
import psycopg2
import psycopg2.pool
from psycopg2 import Error, InterfaceError, DatabaseError, OperationalError
import logging
from typing import Optional, Union, List, Dict, Any
from contextlib import contextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PostgresConnector:
    """Thread-safe PostgreSQL connector with connection pooling
    and auto-reconnect."""

    def __init__(self, **kwargs):
        self.db_config = {
            'host': kwargs.get('host', os.getenv('DB_HOST', 'localhost')),
            'database': kwargs.get(
                'database', os.getenv('DB_NAME')
            ),
            'user': kwargs.get('user', os.getenv('DB_USER')),
            'password': kwargs.get(
                'password', os.getenv('DB_PASSWORD')
            ),
            'port': kwargs.get(
                'port', int(os.getenv('DB_PORT', '5432'))
            ),
            'connect_timeout': kwargs.get('connection_timeout', 10),
        }

        # Remove None values
        self.db_config = {
            k: v for k, v in self.db_config.items() if v is not None
        }

        self._pool_size = kwargs.get('pool_size', 30)
        self._pool: Optional[
            psycopg2.pool.SimpleConnectionPool
        ] = None
        self._lock = threading.RLock()
        self._max_retries = kwargs.get('max_retries', 3)
        self._retry_delay = kwargs.get('retry_delay', 1.0)

    def _init_pool(self) -> bool:
        """Initialize connection pool."""
        try:
            if not self._pool:
                logger.info(
                    "Initializing PostgreSQL connection pool"
                )
                self._pool = psycopg2.pool.SimpleConnectionPool(
                    minconn=1,
                    maxconn=self._pool_size,
                    **self.db_config,
                )
            return True
        except (Error, DatabaseError, OperationalError) as e:
            logger.error(
                f"Failed to initialize connection pool: {e}"
            )
            return False

    @contextmanager
    def get_connection(self):
        """Context manager for database connections with retry
        logic."""
        connection = None
        for attempt in range(self._max_retries):
            try:
                with self._lock:
                    if not self._init_pool():
                        raise DatabaseError(
                            "Failed to initialize connection pool"
                        )
                    connection = self._pool.getconn()

                connection.autocommit = True
                yield connection
                return

            except (
                InterfaceError,
                DatabaseError,
                OperationalError,
            ) as e:
                logger.warning(
                    f"Connection attempt {attempt + 1} failed: {e}"
                )
                if connection:
                    try:
                        with self._lock:
                            self._pool.putconn(
                                connection, close=True
                            )
                    except (Error, AttributeError):
                        pass
                    connection = None

                if attempt < self._max_retries - 1:
                    time.sleep(
                        self._retry_delay * (2 ** attempt)
                    )
                else:
                    raise

            finally:
                if connection:
                    try:
                        with self._lock:
                            self._pool.putconn(connection)
                    except (Error, AttributeError):
                        pass

    def disconnect(self):
        """Close all connections in pool."""
        with self._lock:
            if self._pool:
                try:
                    self._pool.closeall()
                except (Error, AttributeError):
                    pass
                finally:
                    self._pool = None

    def execute(self, query, params=None):
        """Execute query and return last inserted id for INSERT,
        or rowcount otherwise.

        For INSERT queries, appends RETURNING id to retrieve the
        inserted row id (matching SQLite's lastrowid behavior).
        """
        params = params or ()

        with self.get_connection() as connection:
            cursor = None
            try:
                cursor = connection.cursor()

                is_insert = query.strip().upper().startswith(
                    'INSERT'
                )
                if is_insert and 'RETURNING' not in query.upper():
                    query = query.rstrip().rstrip(';')
                    query += ' RETURNING id'

                cursor.execute(query, params)

                if is_insert:
                    row = cursor.fetchone()
                    return row[0] if row else None

                return cursor.rowcount

            except (Error, DatabaseError, OperationalError) as e:
                logger.error(
                    f"Query execution error: {e}\n"
                    f"Query: {query}\nParams: {params}"
                )
                raise
            finally:
                if cursor:
                    cursor.close()

    def get_results(
        self,
        query,
        params=None,
        return_type='rows',
        incl_column_names=False,
    ):
        """Execute query and return results.

        Parameters
        ----------
        query : str
            SQL query to execute.
        params : tuple, list, or dict, optional
            Query parameters.
        return_type : str
            One of 'rows', 'list', 'dict', 'hdict', 'tuple'.
        incl_column_names : bool
            If True, return (results, column_names).
        """
        params = params or ()

        with self.get_connection() as connection:
            cursor = None
            try:
                cursor = connection.cursor()
                cursor.execute(query, params)
                rows = cursor.fetchall()

                col_names = [
                    desc[0] for desc in cursor.description
                ]

                if return_type == 'list':
                    ret_val = (
                        [row[0] for row in rows]
                        if rows
                        else []
                    )
                elif return_type == 'dict':
                    ret_val = (
                        {row[0]: row[1] for row in rows}
                        if rows
                        else {}
                    )
                elif return_type == 'hdict':
                    if len(rows) == 0:
                        return None
                    ret_val = {
                        col_names[i]: rows[0][i]
                        for i in range(len(col_names))
                    }
                elif return_type == 'tuple':
                    if len(rows) == 0:
                        return None
                    ret_val = rows[0]
                else:
                    ret_val = rows

                if incl_column_names:
                    return ret_val, col_names
                return ret_val

            except (Error, DatabaseError, OperationalError) as e:
                logger.error(
                    f"Query execution error: {e}\n"
                    f"Query: {query}\nParams: {params}"
                )
                raise
            finally:
                if cursor:
                    cursor.close()

    def get_scalar(
        self,
        query,
        params=None,
        return_type='single',
        load_json=False,
    ):
        """Execute query and return a scalar result.

        Parameters
        ----------
        query : str
            SQL query to execute.
        params : tuple, list, or dict, optional
            Query parameters.
        return_type : str
            'single' returns first column of first row,
            'tuple' returns the full first row.
        load_json : bool
            If True, parse the result as JSON.
        """
        params = params or ()

        with self.get_connection() as connection:
            cursor = None
            try:
                cursor = connection.cursor()
                cursor.execute(query, params)
                row = cursor.fetchone()

                if row is None:
                    return None

                if return_type == 'single':
                    val = row[0]
                    return (
                        json.loads(val) if load_json else val
                    )
                elif return_type == 'tuple':
                    return row
                else:
                    raise ValueError(
                        f"Unknown return type: {return_type}"
                    )

            except (Error, DatabaseError, OperationalError) as e:
                logger.error(
                    f"Query execution error: {e}\n"
                    f"Query: {query}\nParams: {params}"
                )
                raise
            finally:
                if cursor:
                    cursor.close()

    def define_table(self, table_name, relations=None):
        pass
