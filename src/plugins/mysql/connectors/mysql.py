
import json
import os
import threading
import time
# import mysql.connector
from mysql.connector import pooling
from mysql.connector.errors import Error, InterfaceError, DatabaseError, OperationalError
import logging
from typing import Optional, Union, List, Dict, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class MysqlConnector:
    """Thread-safe MySQL connector with connection pooling and auto-reconnect"""
    
    def __init__(self, **kwargs):
        self.db_config = {
            'host': kwargs.get('host', os.getenv('DB_HOST', 'localhost')),
            'database': kwargs.get('database', os.getenv('DB_NAME')),
            'user': kwargs.get('user', os.getenv('DB_USER')),
            'password': kwargs.get('password', os.getenv('DB_PASSWORD')),
            'connection_timeout': kwargs.get('connection_timeout', 10),
            'autocommit': True,
            'charset': 'utf8mb4',
            'use_unicode': True,
            'sql_mode': 'TRADITIONAL'
        }
        
        # Remove None values
        self.db_config = {k: v for k, v in self.db_config.items() if v is not None}
        
        self.pool_config = {
            **self.db_config,
            'pool_name': 'finance_pool',
            'pool_size': kwargs.get('pool_size', 30),
            'pool_reset_session': True
        }
        
        self._pool: Optional[pooling.MySQLConnectionPool] = None
        self._lock = threading.RLock()
        self._max_retries = kwargs.get('max_retries', 3)
        self._retry_delay = kwargs.get('retry_delay', 1.0)
        
    def _init_pool(self) -> bool:
        """Initialize connection pool"""
        try:
            if not self._pool:
                logger.info("Initializing MySQL connection pool")
                self._pool = pooling.MySQLConnectionPool(**self.pool_config)
            return True
        except (Error, DatabaseError, OperationalError) as e:
            logger.error(f"Failed to initialize connection pool: {e}")
            return False
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections with retry logic"""
        connection = None
        for attempt in range(self._max_retries):
            try:
                with self._lock:
                    if not self._init_pool():
                        raise DatabaseError("Failed to initialize connection pool")
                    
                    connection = self._pool.get_connection()
                    
                if connection and connection.is_connected():
                    yield connection
                    return
                    
            except (InterfaceError, DatabaseError, OperationalError) as e:
                logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
                if connection:
                    try:
                        connection.close()
                    except (Error, AttributeError):
                        pass
                    connection = None
                
                if attempt < self._max_retries - 1:
                    time.sleep(self._retry_delay * (2 ** attempt))
                else:
                    raise
                    
            finally:
                if connection:
                    try:
                        connection.close()
                    except (Error, AttributeError):
                        pass
    
    def disconnect(self):
        """Close all connections in pool"""
        with self._lock:
            if self._pool:
                try:
                    # Close all connections in pool
                    for _ in range(self.pool_config.get('pool_size', 10)):
                        try:
                            conn = self._pool.get_connection()
                            conn.close()
                        except (Error, AttributeError):
                            break
                except (Error, AttributeError):
                    pass
                finally:
                    self._pool = None
    
    def get_results(self, query: str, params: Union[tuple, list] = None, return_type: str = 'rows') -> Union[List, Dict]:
        """Execute query and return results with proper error handling"""
        params = params or ()
        
        with self.get_connection() as connection:
            cursor = None
            try:
                cursor = connection.cursor(buffered=True)
                cursor.execute(query, params)
                results = cursor.fetchall()
                
                if return_type == 'rows':
                    return results
                elif return_type == 'list':
                    return [row[0] for row in results] if results else []
                elif return_type == 'dict':
                    return {row[0]: row[1] for row in results} if results else {}
                else:
                    raise ValueError(f"Invalid return_type: {return_type}")
                    
            except (Error, DatabaseError, OperationalError) as e:
                logger.error(f"Query execution error: {e}\nQuery: {query}\nParams: {params}")
                raise
            finally:
                if cursor:
                    cursor.close()

    def execute(self, query: str, params: Union[tuple, list] = None) -> int:
        """Execute query with proper transaction handling"""
        params = params or ()
        
        with self.get_connection() as connection:
            cursor = None
            try:
                cursor = connection.cursor()
                cursor.execute(query, params)
                
                if not connection.autocommit:
                    connection.commit()
                    
                return cursor.rowcount
                
            except (Error, DatabaseError, OperationalError) as e:
                logger.error(f"Query execution error: {e}\nQuery: {query}\nParams: {params}")
                if not connection.autocommit:
                    try:
                        connection.rollback()
                    except (Error, AttributeError):
                        pass
                raise
            finally:
                if cursor:
                    cursor.close()
    
    def get_scalar(self, query: str, params: Union[tuple, list] = None, load_json: bool = False) -> Any:
        """Execute query and return scalar result"""
        params = params or ()
        results = self.get_results(query, params, return_type='list')
        if not results:
            return None
        return results[0] if not load_json else json.loads(results[0])

    def define_table(self, table_name, relations=None):
        pass
