"""
Database connection configuration.

Supports both SQLite (for development) and PostgreSQL (for production).
Switch between them using the DATABASE_TYPE environment variable.

All environment variables are loaded from src.bot.config to ensure proper initialization order.
"""

from typing import Optional
from src.bot.config import DATABASE_TYPE, DATABASE_URL, SQLITE_DB_PATH


def get_database_connection_string() -> str:
    """
    Get the appropriate database connection string based on environment configuration.

    Supports:
    - SQLite: For local development (DATABASE_TYPE=sqlite)
    - PostgreSQL: For production (DATABASE_TYPE=postgresql)

    Returns:
        Connection string suitable for SQLAlchemy or psycopg2

    Examples:
        SQLite: "sqlite:///evoladder.db"
        PostgreSQL: "postgresql://user:pass@host.supabase.com:5432/postgres"
    """
    db_type = DATABASE_TYPE.lower()

    if db_type == "sqlite":
        # SQLite connection
        conn_str = f"sqlite:///{SQLITE_DB_PATH}"
        print(f"[Database] Using SQLite: {SQLITE_DB_PATH}")
        return conn_str

    elif db_type == "postgresql":
        # PostgreSQL: Use DATABASE_URL
        database_url = DATABASE_URL

        # Fix for Railway/Supabase: Replace postgres:// with postgresql://
        # (Some tools use the old postgres:// scheme)
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)

        print(f"[Database] Using PostgreSQL: {_mask_password(database_url)}")
        return database_url

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
    return DATABASE_TYPE.lower()


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
        return {"type": "sqlite", "path": SQLITE_DB_PATH}
    else:  # postgresql
        return {"type": "postgresql", "url": _mask_password(DATABASE_URL)}


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

    pattern = r"://([^:]+):([^@]+)@"
    masked = re.sub(pattern, r"://\1:***@", connection_string)
    return masked


# Example usage and testing
if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("DATABASE CONNECTION CONFIGURATION")
    print("=" * 70 + "\n")

    config = get_database_config()
    print("Configuration:")
    for key, value in config.items():
        print(f"  {key}: {value}")

    print(f"\nConnection String:\n  {get_database_connection_string()}")

    print(f"\nDatabase Type: {get_database_type()}")
    print(f"Is PostgreSQL: {is_postgresql()}")
    print(f"Is SQLite: {is_sqlite()}")

    print("\n" + "=" * 70 + "\n")
