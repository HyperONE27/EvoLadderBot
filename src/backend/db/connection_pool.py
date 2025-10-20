"""
Manages the PostgreSQL connection pool for the application.

This module initializes a singleton connection pool that can be imported and used
by any part of the application that needs a database connection. This approach
avoids the high overhead of establishing a new connection for every query.
"""

import os
from psycopg2 import pool
from src.bot.config import DATABASE_TYPE, DATABASE_URL

# The global connection pool instance. It will be initialized only once.
db_pool = None

def initialize_pool():
    """
    Initializes the PostgreSQL connection pool.
    
    This function should be called once at application startup.
    It checks if the database type is PostgreSQL and creates a connection pool.
    """
    global db_pool
    if DATABASE_TYPE.lower() == "postgresql":
        try:
            print("[DB Pool] Initializing PostgreSQL connection pool...")
            db_pool = pool.SimpleConnectionPool(
                minconn=1,
                maxconn=10,  # Allow up to 10 concurrent connections
                dsn=DATABASE_URL
            )
            # Test the connection pool by getting and returning a connection
            conn = db_pool.getconn()
            db_pool.putconn(conn)
            print("[DB Pool] Connection pool initialized successfully.")
        except Exception as e:
            print(f"[DB Pool] FATAL: Failed to initialize connection pool: {e}")
            db_pool = None # Ensure pool is None if initialization fails
            raise

def get_pool():
    """
    Returns the initialized connection pool.
    
    Raises:
        Exception: If the pool has not been initialized.
    """
    if db_pool is None:
        raise Exception("Database connection pool has not been initialized. Call initialize_pool() first.")
    return db_pool

def close_pool():
    """
    Closes all connections in the pool.
    
    This function should be called during application shutdown to gracefully
    close all database connections.
    """
    global db_pool
    if db_pool:
        print("[DB Pool] Closing all connections in the pool...")
        db_pool.closeall()
        db_pool = None
        print("[DB Pool] Connection pool closed.")

# Initialize the pool when this module is first imported.
# This makes it a singleton.
# initialize_pool() # We will call this explicitly at startup now.
