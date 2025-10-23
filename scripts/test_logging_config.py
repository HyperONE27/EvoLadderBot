#!/usr/bin/env python3
"""
Test script to demonstrate the new logging configuration system.

This script shows how to use the different logging macros and how
environment variables control the logging output.
"""

import os
import sys
import time

# Add the src directory to the path so we can import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from bot.logging_config import (
    log_general, log_performance, log_memory, log_database,
    log_queue, log_matchmaking, log_notifications, log_process_pool,
    LogLevel, LogCategory, set_category_level, disable_category
)


def test_logging_macros():
    """Test all the different logging macros."""
    print("Testing logging macros...")
    print("=" * 50)
    
    # General logging
    log_general(LogLevel.INFO, "Application started")
    log_general(LogLevel.WARNING, "Configuration warning")
    log_general(LogLevel.ERROR, "Something went wrong")
    
    # Performance logging
    log_performance(LogLevel.INFO, "Database query completed", duration_ms=45.2)
    log_performance(LogLevel.WARNING, "Slow operation detected", duration_ms=150.5)
    log_performance(LogLevel.DEBUG, "Quick operation", duration_ms=5.1)
    
    # Memory logging
    log_memory(LogLevel.INFO, "Memory check completed", memory_mb=245.3)
    log_memory(LogLevel.WARNING, "High memory usage detected", memory_mb=512.7)
    log_memory(LogLevel.DEBUG, "Memory allocation", memory_mb=12.4)
    
    # Database logging
    log_database(LogLevel.INFO, "User profile updated", operation="update_profile")
    log_database(LogLevel.WARNING, "Query timeout", operation="complex_query")
    log_database(LogLevel.ERROR, "Connection failed", operation="connect")
    
    # Queue logging
    log_queue(LogLevel.INFO, "Player added to queue", player_id=123456)
    log_queue(LogLevel.WARNING, "Player already in queue", player_id=123456)
    log_queue(LogLevel.INFO, "Queue cleared")
    
    # Matchmaking logging
    log_matchmaking(LogLevel.INFO, "Match found", match_id="match_123")
    log_matchmaking(LogLevel.DEBUG, "Searching for matches")
    log_matchmaking(LogLevel.WARNING, "No suitable matches found")
    
    # Notification logging
    log_notifications(LogLevel.INFO, "Player notified", player_id=123456)
    log_notifications(LogLevel.WARNING, "Player not subscribed", player_id=789012)
    log_notifications(LogLevel.DEBUG, "Notification sent")
    
    # Process pool logging
    log_process_pool(LogLevel.INFO, "Pool health check completed")
    log_process_pool(LogLevel.WARNING, "Pool restart required")
    log_process_pool(LogLevel.DEBUG, "Worker process started")


def test_category_control():
    """Test runtime category control."""
    print("\nTesting category control...")
    print("=" * 50)
    
    # Disable performance logging
    print("Disabling performance logging...")
    disable_category(LogCategory.PERFORMANCE)
    log_performance(LogLevel.INFO, "This should not appear")
    
    # Set memory logging to DEBUG
    print("Setting memory logging to DEBUG...")
    set_category_level(LogCategory.MEMORY, LogLevel.DEBUG)
    log_memory(LogLevel.DEBUG, "This should appear")
    log_memory(LogLevel.INFO, "This should also appear")
    
    # Re-enable performance logging
    print("Re-enabling performance logging...")
    set_category_level(LogCategory.PERFORMANCE, LogLevel.INFO)
    log_performance(LogLevel.INFO, "This should now appear")


def test_performance_timing():
    """Test performance logging with actual timing."""
    print("\nTesting performance timing...")
    print("=" * 50)
    
    # Simulate a fast operation
    start_time = time.perf_counter()
    time.sleep(0.01)  # 10ms
    duration_ms = (time.perf_counter() - start_time) * 1000
    log_performance(LogLevel.DEBUG, "Fast operation", duration_ms=duration_ms)
    
    # Simulate a slow operation
    start_time = time.perf_counter()
    time.sleep(0.15)  # 150ms
    duration_ms = (time.perf_counter() - start_time) * 1000
    log_performance(LogLevel.WARNING, "Slow operation", duration_ms=duration_ms)


def main():
    """Main test function."""
    print("Logging Configuration Test")
    print("=" * 50)
    
    # Import config to show current values
    from bot.config import LOG_LEVEL, LOG_PERFORMANCE, LOG_MEMORY
    print(f"Current LOG_LEVEL: {LOG_LEVEL}")
    print(f"Current LOG_PERFORMANCE: {LOG_PERFORMANCE}")
    print(f"Current LOG_MEMORY: {LOG_MEMORY}")
    print()
    
    test_logging_macros()
    test_category_control()
    test_performance_timing()
    
    print("\nTest completed!")
    print("\nTo test different configurations, modify the values in src/bot/config.py:")
    print("  LOG_PERFORMANCE = 'DEBUG'  # For verbose performance logging")
    print("  LOG_MEMORY = 'DEBUG'       # For verbose memory logging")
    print("  LOG_LEVEL = 'WARNING'      # To reduce general noise")


if __name__ == "__main__":
    main()
