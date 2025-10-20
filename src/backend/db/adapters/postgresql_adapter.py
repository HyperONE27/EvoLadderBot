"""
PostgreSQL database adapter implementation.
"""

import re
from typing import Any, Dict, List, Optional
from contextlib import contextmanager

from src.backend.db.adapters.base_adapter import DatabaseAdapter
from src.bot.config import DATABASE_URL


class PostgreSQLAdapter(DatabaseAdapter):
    """
    Database adapter for PostgreSQL.
    
    Handles PostgreSQL-specific connection management, query formatting,
    and result conversion.
    """
    
    def __init__(self, connection_url: Optional[str] = None):
        """
        Initialize PostgreSQL adapter.
        
        Args:
            connection_url: PostgreSQL connection URL (defaults to config value)
        """
        self.connection_url = connection_url or DATABASE_URL
        
        # Fix postgres:// scheme to postgresql://
        if self.connection_url.startswith("postgres://"):
            self.connection_url = self.connection_url.replace(
                "postgres://", "postgresql://", 1
            )
    
    def get_connection_string(self) -> str:
        """Get connection string for logging (with masked password)."""
        return self._mask_password(self.connection_url)
    
    @contextmanager
    def get_connection(self):
        """
        Get a PostgreSQL database connection from the pool.
        
        Uses connection pooling to eliminate TCP/SSL/auth overhead.
        Falls back to direct connection if pool is not initialized.
        
        Yields:
            psycopg2 connection with RealDictCursor
        """
        import psycopg2
        import psycopg2.extras
        
        # Try to use connection pool if available
        try:
            from src.backend.db.connection_pool import get_global_pool
            
            pool = get_global_pool()
            # Get connection from pool (reuses existing connection - fast!)
            with pool.get_connection() as conn:
                # Set cursor factory for dict results
                conn.cursor_factory = psycopg2.extras.RealDictCursor
                yield conn
                # Pool handles commit/rollback/return automatically
            return
        except RuntimeError:
            # Pool not initialized - fall back to direct connection
            pass
        
        # Fallback: Direct connection (slow, but works)
        conn = psycopg2.connect(
            self.connection_url,
            cursor_factory=psycopg2.extras.RealDictCursor
        )
        
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
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
            cursor = conn.cursor()
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
            cursor = conn.cursor()
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
            cursor = conn.cursor()
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

