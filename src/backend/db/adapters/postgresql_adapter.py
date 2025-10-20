"""
PostgreSQL database adapter implementation.
"""

import psycopg2
from psycopg2 import extras
import re
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from .base_adapter import BaseAdapter
from src.backend.db.connection_pool import get_pool


class PostgreSQLAdapter(BaseAdapter):
    """
    Database adapter for PostgreSQL.
    
    Handles PostgreSQL-specific connection management, query formatting,
    and result conversion.
    """
    
    def __init__(self):
        """
        Initialize PostgreSQL adapter.
        
        Args:
            connection_url: PostgreSQL connection URL (defaults to config value)
        """
        # The connection pool is managed by the connection_pool module.
        # This adapter simply uses the pool.
        pass
    
    def get_connection_string(self) -> str:
        """Get connection string for logging (with masked password)."""
        return self._mask_password(self.connection_url)
    
    @contextmanager
    def get_connection(self):
        """
        Gets a connection from the pool.

        This method borrows a connection from the centrally managed pool and ensures
        it is returned afterwards, even if an error occurs.
        """
        pool = get_pool()
        conn = None
        try:
            conn = pool.getconn()
            yield conn
        finally:
            if conn:
                pool.putconn(conn)
    
    def execute_query(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Execute a SELECT query and return results as list of dicts."""
        if params is None:
            params = {}
        
        # Convert :named to %(named)s placeholders
        converted_query = self.convert_query(query)
        
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cursor:
                try:
                    cursor.execute(self.convert_query(query), params or {})
                    results = cursor.fetchall()
                    return [dict(row) for row in results]
                except psycopg2.Error as e:
                    conn.rollback()
                    print(f"Error executing query: {e}")
                    raise
    
    def execute_write(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None
    ) -> int:
        """Execute an INSERT/UPDATE/DELETE query."""
        if params is None:
            params = {}
        
        converted_query = self.convert_query(query)
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                try:
                    cursor.execute(self.convert_query(query), params or {})
                    rowcount = cursor.rowcount
                    conn.commit()
                    return rowcount
                except psycopg2.Error as e:
                    conn.rollback()
                    print(f"Error executing write: {e}")
                    raise
    
    def execute_insert(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Optional[int]:
        """Execute an INSERT query and return the new row's ID."""
        if params is None:
            params = {}
        
        converted_query = self.convert_query(query)
        
        # Add RETURNING id clause if not present
        if "RETURNING id" not in query.upper():
            query += " RETURNING id"
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                try:
                    cursor.execute(self.convert_query(query), params or {})
                    inserted_id = cursor.fetchone()[0] if cursor.rowcount > 0 else None
                    conn.commit()
                    return inserted_id
                except psycopg2.Error as e:
                    conn.rollback()
                    print(f"Error executing insert: {e}")
                    raise
    
    def convert_query(self, query: str) -> str:
        """
        Convert query with :named placeholders to PostgreSQL format.
        
        Converts :name to %(name)s for psycopg2 compatibility.
        
        Args:
            query: SQL query with :named placeholders
            
        Returns:
            Query with %(named)s placeholders
            
        Example:
            Input:  "SELECT * FROM players WHERE discord_uid = :uid"
            Output: "SELECT * FROM players WHERE discord_uid = %(uid)s"
        """
        # Convert :name to %(name)s
        # Use regex to match :word_boundary
        converted = re.sub(r':([a-zA-Z_][a-zA-Z0-9_]*)', r'%(\1)s', query)
        return converted
    
    def dict_from_row(self, row: Any) -> Dict[str, Any]:
        """
        Convert a PostgreSQL row to a dictionary.
        
        Args:
            row: RealDictRow object from psycopg2
            
        Returns:
            Dictionary with column names as keys
        """
        return dict(row)
    
    def execute_many(
        self,
        query: str,
        params_list: List[Dict[str, Any]]
    ) -> int:
        """
        Execute a query multiple times with different parameters.
        
        Optimized for PostgreSQL using execute_batch.
        """
        if not params_list:
            return 0
        
        import psycopg2.extras
        
        converted_query = self.convert_query(query)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Use execute_batch for better performance
            psycopg2.extras.execute_batch(cursor, converted_query, params_list)
            
            return cursor.rowcount
    
    def _mask_password(self, connection_string: str) -> str:
        """
        Mask the password in a connection string for safe logging.
        
        Args:
            connection_string: Database connection string
            
        Returns:
            Connection string with password masked
        """
        if not connection_string:
            return connection_string
        
        # Pattern: postgresql://user:password@host:port/db
        # Replace everything between : and @ with ***
        pattern = r'://([^:]+):([^@]+)@'
        masked = re.sub(pattern, r'://\1:***@', connection_string)
        return masked

