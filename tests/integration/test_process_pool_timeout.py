"""
Integration tests for replay parsing timeout and process pool management.

These tests verify that the timeout mechanism works correctly with a real
ProcessPoolExecutor, and that fallback mechanisms are triggered appropriately.
"""

import pytest
import asyncio
import time
from concurrent.futures import ProcessPoolExecutor

from src.backend.services.replay_parsing_timeout import parse_replay_with_timeout


# Module-level functions (required for ProcessPoolExecutor pickling)

def slow_parse_function(replay_bytes: bytes) -> dict:
    """A parse function that intentionally times out."""
    time.sleep(2.5)
    return {"result": "completed"}


def fast_parse_function(replay_bytes: bytes) -> dict:
    """A fast parse function that completes quickly."""
    return {"result": "completed", "bytes_parsed": len(replay_bytes)}


@pytest.fixture
def process_pool():
    """Provide a ProcessPoolExecutor that is properly cleaned up."""
    executor = ProcessPoolExecutor(max_workers=2)
    yield executor
    executor.shutdown(wait=True)


class TestReplayParsingTimeout:
    """Test replay parsing timeout behavior with a real process pool."""
    
    @pytest.mark.asyncio
    async def test_stuck_job_triggers_timeout_and_fallback(self, process_pool):
        """
        Verify that a job exceeding the timeout is correctly aborted and
        the timeout return value is signaled.
        
        This test uses fault injection by submitting a job that intentionally
        takes longer than the timeout period.
        
        The flow is:
        1. Job is submitted to process pool
        2. After 1.0 second, asyncio timeout triggers
        3. Fallback to synchronous parsing runs (which completes the 2.5s sleep)
        4. Function returns with was_timeout=True
        
        So total time is ~3.5 seconds (1.0s timeout + 2.5s fallback).
        """
        # Arrange
        mock_replay_bytes = b"mock_replay_data_" * 100
        timeout_seconds = 1.0  # Timeout after 1 second
        
        start_time = time.monotonic()
        
        # Act
        result, was_timeout = await parse_replay_with_timeout(
            process_pool,
            slow_parse_function,
            mock_replay_bytes,
            timeout=timeout_seconds
        )
        
        elapsed = time.monotonic() - start_time
        
        # Assert
        # The timeout should trigger after ~1 second, then fallback completes the 2.5s parse
        # Total time should be around 3.5 seconds (timeout + fallback execution)
        assert 2.0 < elapsed < 4.5, \
            f"Should take ~3.5s (1s timeout + 2.5s fallback parse), but took {elapsed:.2f}s"
        assert was_timeout is True, \
            "was_timeout should be True when timeout occurs"
        assert isinstance(result, dict), \
            "Result should be a dictionary even with timeout"
    
    @pytest.mark.asyncio
    async def test_quick_job_completes_without_timeout(self, process_pool):
        """
        Verify that a job completing quickly does not trigger the timeout.
        
        This test ensures the timeout mechanism doesn't interfere with
        normal, fast-executing jobs.
        """
        # Arrange
        mock_replay_bytes = b"mock_replay_data"
        timeout_seconds = 2.5
        
        start_time = time.monotonic()
        
        # Act
        result, was_timeout = await parse_replay_with_timeout(
            process_pool,
            fast_parse_function,
            mock_replay_bytes,
            timeout=timeout_seconds
        )
        
        elapsed = time.monotonic() - start_time
        
        # Assert
        assert elapsed < 1.0, \
            f"Quick job should complete in <1s, but took {elapsed:.2f}s"
        assert was_timeout is False, \
            "was_timeout should be False when job completes normally"
        assert result.get("result") == "completed", \
            "Result should contain the expected output"
