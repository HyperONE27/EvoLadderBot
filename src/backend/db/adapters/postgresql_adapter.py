"""
PostgreSQL database adapter implementation.
"""

import re
from typing import Any, Dict, List, Optional
from contextlib import contextmanager

from src.backend.db.adapters.base_adapter import DatabaseAdapter
from src.bot.config import DATABASE_URL
from src.backend.db.connection_pool import get_connection_from_pool, return_connection_to_pool


class PostgreSQLAdapter(DatabaseAdapter):
    """
    Database adapter for PostgreSQL.
    
    Handles PostgreSQL-specific connection management, query formatting,
    and result conversion.
    """
    
    def __init__(self):
        """Initialize PostgreSQL adapter. The connection pool is managed globally."""
        pass
    
    def get_connection_string(self) -> str:
        """Get connection string for logging (with masked password)."""
        # Fix postgres:// scheme to postgresql:// for display
        conn_str = DATABASE_URL
        if conn_str.startswith("postgres://"):
            conn_str = conn_str.replace("postgres://", "postgresql://", 1)
        return self._mask_password(conn_str)
    
    @contextmanager
    def get_connection(self):
        """
        Get a PostgreSQL database connection from the global pool.
        
        Yields:
            psycopg2 connection with RealDictCursor
        """
        import psycopg2.extras
        
        conn = None
        try:
            conn = get_connection_from_pool()
            # The cursor factory should be set when the connection is made,
            # but we can also set it here if needed, though it's less efficient.
            # For simplicity, we'll assume RealDictCursor is handled by the pool
            # or we set it on each cursor. A better approach is to create a
            # custom connection factory for the pool. For now, we'll create
            # cursors with the factory.
            yield conn
            conn.commit()
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                return_connection_to_pool(conn)
    
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
            # Create a cursor with RealDictCursor for this query
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(converted_query, params)
                rows = cursor.fetchall()
            
            # RealDictCursor returns RealDictRow objects, convert to plain dicts
            return [dict(row) for row in rows]
    
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
                cursor.execute(converted_query, params)
                return cursor.rowcount
    
    def execute_insert(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None
    ) -> int:
        """Execute an INSERT query and return the new row's ID."""
        if params is None:
            params = {}
        
        converted_query = self.convert_query(query)
        
        # Add RETURNING id clause if not present
        if "RETURNING" not in converted_query.upper():
            converted_query = converted_query.rstrip(";") + " RETURNING id"
        
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(converted_query, params)
                result = cursor.fetchone()
            
            if result and "id" in result:
                return result["id"]
            
            # Fallback: if no id returned, return 0
            return 0
    
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
        converted = re.sub(r':(\w+)', r'%(\1)s', query)
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
            # Use a RealDictCursor to fetch results if needed, though execute_batch doesn't return results
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
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

