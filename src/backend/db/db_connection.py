"""
Database connection configuration.

Supports both SQLite (for development) and PostgreSQL (for production).
Switch between them using the DATABASE_TYPE environment variable.
"""

import os
from typing import Optional


def get_database_connection_string() -> str:
    """
    Get the appropriate database connection string based on environment configuration.
    
    Supports:
    - SQLite: For local development (DATABASE_TYPE=sqlite)
    - PostgreSQL: For local development and production (DATABASE_TYPE=postgresql)
      - Local: Uses individual env vars (POSTGRES_HOST, POSTGRES_PORT, etc.)
      - Production: Uses DATABASE_URL from Railway/Supabase
    
    Returns:
        Connection string suitable for SQLAlchemy or psycopg2
        
    Examples:
        SQLite: "sqlite:///evoladder.db"
        PostgreSQL (local): "postgresql://user:pass@localhost:5432/evoladder"
        PostgreSQL (prod): "postgresql://user:pass@host.supabase.com:6543/postgres"
    """
    db_type = os.getenv("DATABASE_TYPE", "sqlite").lower()
    
    if db_type == "sqlite":
        # SQLite connection
        db_path = os.getenv("SQLITE_DB_PATH", "evoladder.db")
        conn_str = f"sqlite:///{db_path}"
        print(f"[Database] Using SQLite: {db_path}")
        return conn_str
    
    elif db_type == "postgresql":
        # Check if using production DATABASE_URL (Supabase/Railway)
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            # Production: Use the full DATABASE_URL
            # Fix for Railway/Supabase: Replace postgres:// with postgresql://
            # (Some tools use the old postgres:// scheme)
            if database_url.startswith("postgres://"):
                database_url = database_url.replace("postgres://", "postgresql://", 1)
            print(f"[Database] Using PostgreSQL (Production): {_mask_password(database_url)}")
            return database_url
        
        # Local development: Build connection string from individual env vars
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        database = os.getenv("POSTGRES_DB", "evoladder")
        user = os.getenv("POSTGRES_USER", "evoladder_user")
        password = os.getenv("POSTGRES_PASSWORD", "")
        
        conn_str = f"postgresql://{user}:{password}@{host}:{port}/{database}"
        print(f"[Database] Using PostgreSQL (Local): {_mask_password(conn_str)}")
        return conn_str
    
    else:
        raise ValueError(
            f"Unknown DATABASE_TYPE: '{db_type}'. Must be 'sqlite' or 'postgresql'. "
            f"Check your .env file."
        )


def get_database_type() -> str:
    """
    Get the current database type.
    
    Returns:
        'sqlite' or 'postgresql'
    """
    return os.getenv("DATABASE_TYPE", "sqlite").lower()


def is_postgresql() -> bool:
    """Check if currently using PostgreSQL."""
    return get_database_type() == "postgresql"


def is_sqlite() -> bool:
    """Check if currently using SQLite."""
    return get_database_type() == "sqlite"


def get_database_config() -> dict:
    """
    Get all database configuration as a dictionary.
    
    Useful for logging and debugging.
    
    Returns:
        Dictionary with database configuration (passwords masked)
    """
    db_type = get_database_type()
    
    if db_type == "sqlite":
        return {
            "type": "sqlite",
            "path": os.getenv("SQLITE_DB_PATH", "evoladder.db")
        }
    else:  # postgresql
        if os.getenv("DATABASE_URL"):
            return {
                "type": "postgresql",
                "source": "production (DATABASE_URL)",
                "url": _mask_password(os.getenv("DATABASE_URL"))
            }
        else:
            return {
                "type": "postgresql",
                "source": "local (env vars)",
                "host": os.getenv("POSTGRES_HOST", "localhost"),
                "port": os.getenv("POSTGRES_PORT", "5432"),
                "database": os.getenv("POSTGRES_DB", "evoladder"),
                "user": os.getenv("POSTGRES_USER", "evoladder_user"),
                "password": "***masked***"
            }


def _mask_password(connection_string: str) -> str:
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
    import re
    pattern = r'://([^:]+):([^@]+)@'
    masked = re.sub(pattern, r'://\1:***@', connection_string)
    return masked


# Example usage and testing
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    print("\n" + "="*70)
    print("DATABASE CONNECTION CONFIGURATION")
    print("="*70 + "\n")
    
    config = get_database_config()
    print("Configuration:")
    for key, value in config.items():
        print(f"  {key}: {value}")
    
    print(f"\nConnection String:\n  {get_database_connection_string()}")
    
    print(f"\nDatabase Type: {get_database_type()}")
    print(f"Is PostgreSQL: {is_postgresql()}")
    print(f"Is SQLite: {is_sqlite()}")
    
    print("\n" + "="*70 + "\n")

