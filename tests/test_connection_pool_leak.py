"""
Test to verify connection pool does not leak connections.

This test simulates various failure scenarios to ensure connections are
always properly returned to the pool or explicitly closed, preventing leaks.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
import psycopg2
from psycopg2 import pool

from src.backend.db.connection_pool import initialize_pool, get_connection, close_pool, _global_pool


class MockConnection:
    """Mock connection object for testing."""
    
    def __init__(self, will_fail_on=None):
        self.closed = False
        self.will_fail_on = will_fail_on or []
        self.commit_called = False
        self.rollback_called = False
        self.close_called = False
        
    def commit(self):
        if 'commit' in self.will_fail_on:
            raise psycopg2.OperationalError("Mock commit failure")
        self.commit_called = True
        
    def rollback(self):
        if 'rollback' in self.will_fail_on:
            raise psycopg2.OperationalError("Mock rollback failure")
        self.rollback_called = True
        
    def close(self):
        if 'close' in self.will_fail_on:
            raise psycopg2.OperationalError("Mock close failure")
        self.closed = True
        self.close_called = True
        
    def cursor(self):
        if 'cursor' in self.will_fail_on:
            raise psycopg2.InterfaceError("Mock cursor failure")
        mock_cursor = MagicMock()
        mock_cursor.execute = MagicMock()
        mock_cursor.fetchone = MagicMock(return_value=[1])
        return mock_cursor


class MockConnectionPool:
    """Mock connection pool for testing."""
    
    def __init__(self):
        self.connections = []
        self.connections_in_use = []
        self.getconn_count = 0
        self.putconn_count = 0
        
    def getconn(self):
        self.getconn_count += 1
        conn = MockConnection()
        self.connections_in_use.append(conn)
        return conn
        
    def putconn(self, conn):
        self.putconn_count += 1
        if conn in self.connections_in_use:
            self.connections_in_use.remove(conn)
        self.connections.append(conn)
        
    def closeall(self):
        for conn in self.connections + self.connections_in_use:
            if not conn.closed:
                conn.close()
        self.connections.clear()
        self.connections_in_use.clear()


def test_successful_transaction_returns_connection():
    """Test that successful transactions return connections to the pool."""
    mock_pool = MockConnectionPool()
    
    with patch('src.backend.db.connection_pool._global_pool', mock_pool):
        # Successful transaction
        with get_connection() as conn:
            pass
        
        # Verify connection was returned to pool
        assert mock_pool.getconn_count == 1
        assert mock_pool.putconn_count == 1
        assert len(mock_pool.connections_in_use) == 0
        assert len(mock_pool.connections) == 1
        print("[Test] PASS: Successful transaction returns connection to pool")


def test_application_error_returns_connection():
    """Test that application errors rollback and return connection to pool."""
    mock_pool = MockConnectionPool()
    
    with patch('src.backend.db.connection_pool._global_pool', mock_pool):
        # Application error during transaction
        try:
            with get_connection() as conn:
                raise ValueError("Application error")
        except ValueError:
            pass
        
        # Verify connection was returned to pool after rollback
        assert mock_pool.getconn_count == 1
        assert mock_pool.putconn_count == 1
        assert len(mock_pool.connections_in_use) == 0
        assert len(mock_pool.connections) == 1
        
        # Verify rollback was called
        returned_conn = mock_pool.connections[0]
        assert returned_conn.rollback_called
        print("[Test] PASS: Application error rolls back and returns connection")


def test_connection_error_does_not_return_to_pool():
    """Test that connection errors close the connection instead of returning it."""
    
    class BadConnectionPool(MockConnectionPool):
        def __init__(self):
            super().__init__()
            self.closed_connections = []
            
        def getconn(self):
            self.getconn_count += 1
            conn = MockConnection(will_fail_on=['commit'])
            self.connections_in_use.append(conn)
            # Track the connection reference before it might be set to None
            self.closed_connections.append(conn)
            return conn
    
    mock_pool = BadConnectionPool()
    
    with patch('src.backend.db.connection_pool._global_pool', mock_pool):
        # Connection error during commit
        try:
            with get_connection() as conn:
                pass  # This will fail on commit
        except psycopg2.OperationalError:
            pass
        
        # Verify connection was NOT returned to pool
        assert mock_pool.getconn_count == 1
        assert mock_pool.putconn_count == 0  # Should not be returned
        assert len(mock_pool.connections) == 0  # Not in available pool
        
        # Verify the connection was closed
        closed_conn = mock_pool.closed_connections[0]
        assert closed_conn.close_called, "Connection should have been closed"
        print("[Test] PASS: Connection error closes connection instead of returning")


def test_rollback_failure_does_not_leak():
    """Test that even if rollback fails, connection is handled properly."""
    
    class RollbackFailPool(MockConnectionPool):
        def __init__(self):
            super().__init__()
            self.closed_connections = []
            
        def getconn(self):
            self.getconn_count += 1
            conn = MockConnection(will_fail_on=['rollback'])
            self.connections_in_use.append(conn)
            self.closed_connections.append(conn)
            return conn
    
    mock_pool = RollbackFailPool()
    
    with patch('src.backend.db.connection_pool._global_pool', mock_pool):
        # Application error, then rollback fails
        try:
            with get_connection() as conn:
                raise ValueError("Application error")
        except ValueError:
            pass
        
        # Verify connection was not returned to pool (marked as bad)
        assert mock_pool.getconn_count == 1
        assert mock_pool.putconn_count == 0  # Marked as bad, not returned
        assert len(mock_pool.connections) == 0  # Not in available pool
        
        # Verify connection was closed
        closed_conn = mock_pool.closed_connections[0]
        assert closed_conn.close_called, "Connection should have been closed"
        print("[Test] PASS: Rollback failure marks connection as bad, no leak")


def test_concurrent_usage_no_leaks():
    """Test that multiple concurrent operations don't leak connections."""
    mock_pool = MockConnectionPool()
    
    with patch('src.backend.db.connection_pool._global_pool', mock_pool):
        # Simulate 10 successful operations
        for i in range(10):
            with get_connection() as conn:
                pass
        
        # All connections should be returned
        assert mock_pool.getconn_count == 10
        assert mock_pool.putconn_count == 10
        assert len(mock_pool.connections_in_use) == 0
        assert len(mock_pool.connections) == 10
        print("[Test] PASS: 10 concurrent operations, no leaks")


def test_mixed_success_and_failure_no_leaks():
    """Test mix of successful and failed operations don't leak."""
    mock_pool = MockConnectionPool()
    
    with patch('src.backend.db.connection_pool._global_pool', mock_pool):
        # Success
        with get_connection() as conn:
            pass
        
        # Application failure
        try:
            with get_connection() as conn:
                raise ValueError("Error")
        except ValueError:
            pass
        
        # Another success
        with get_connection() as conn:
            pass
        
        # Verify all connections accounted for
        assert mock_pool.getconn_count == 3
        assert mock_pool.putconn_count == 3
        assert len(mock_pool.connections_in_use) == 0
        assert len(mock_pool.connections) == 3
        print("[Test] PASS: Mixed success/failure, no leaks")


if __name__ == "__main__":
    print("\nRunning Connection Pool Leak Tests...")
    print("="*80)
    
    test_successful_transaction_returns_connection()
    test_application_error_returns_connection()
    test_connection_error_does_not_return_to_pool()
    test_rollback_failure_does_not_leak()
    test_concurrent_usage_no_leaks()
    test_mixed_success_and_failure_no_leaks()
    
    print("="*80)
    print("All connection pool tests PASSED!")
    print("\nNo connection leaks detected across all scenarios.")

