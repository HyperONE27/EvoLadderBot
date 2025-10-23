"""
Performance monitoring and tracking service.

This module provides utilities for measuring and logging bot operation times,
enabling performance optimization and bottleneck identification.
"""

import time
import sys
from contextlib import contextmanager
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime

from src.bot.logging_config import log_performance, LogLevel

# Check if we can use emojis (not Windows console)
USE_EMOJIS = sys.stdout.encoding.lower() not in ('cp1252', 'windows-1252')


@dataclass
class PerformanceMetric:
    """Single performance measurement."""
    
    name: str
    duration_ms: float
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    parent: Optional[str] = None


@dataclass
class PerformanceCheckpoint:
    """Checkpoint within a flow."""
    
    name: str
    elapsed_ms: float
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


class FlowTracker:
    """
    Track complete user interaction flows with checkpoints.
    
    Usage:
        flow = FlowTracker("queue_command", user_id=123456)
        flow.checkpoint("guard_checks")
        # ... do work ...
        flow.checkpoint("load_preferences")
        # ... more work ...
        flow.complete("success")
    """
    
    def __init__(self, flow_name: str, user_id: Optional[int] = None):
        self.flow_name = flow_name
        self.user_id = user_id
        self.start_time = time.perf_counter()
        self.checkpoints: List[PerformanceCheckpoint] = []
        self.metadata: Dict[str, Any] = {}
        self._completed = False
        
    def checkpoint(self, name: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Record a checkpoint in the flow."""
        if self._completed:
            log_performance(LogLevel.WARNING, f"Checkpoint '{name}' called after flow completion")
            return
            
        current_time = time.perf_counter()
        elapsed_ms = (current_time - self.start_time) * 1000
        
        checkpoint = PerformanceCheckpoint(
            name=name,
            elapsed_ms=elapsed_ms,
            timestamp=datetime.utcnow(),
            metadata=metadata or {}
        )
        self.checkpoints.append(checkpoint)
        
        # Log checkpoint if it's notably slow
        if len(self.checkpoints) > 1:
            prev_checkpoint = self.checkpoints[-2]
            duration = elapsed_ms - prev_checkpoint.elapsed_ms
            
            if duration > 100:  # Log if operation took >100ms
                log_performance(
                    LogLevel.WARNING,
                    f"{self.flow_name}.{name}",
                    duration_ms=duration,
                    extra={"total_ms": elapsed_ms}
                )
                warning_emoji = "⚠️" if USE_EMOJIS else "[W]"
                print(f"  {warning_emoji} {self.flow_name}.{name}: {duration:.1f}ms")
        
    def add_metadata(self, key: str, value: Any) -> None:
        """Add metadata to the flow."""
        self.metadata[key] = value
        
    def complete(self, status: str = "success") -> float:
        """
        Mark flow as complete and log results.
        
        Returns:
            Total duration in milliseconds
        """
        if self._completed:
            log_performance(LogLevel.WARNING, f"Flow '{self.flow_name}' completed multiple times")
            return 0.0
            
        self._completed = True
        total_duration_ms = (time.perf_counter() - self.start_time) * 1000
        
        # Log completion
        self._log_completion(total_duration_ms, status)
        
        return total_duration_ms
    
    def _log_completion(self, total_duration_ms: float, status: str) -> None:
        """Log flow completion with all checkpoints."""
        # Determine log level and prefix based on duration
        if total_duration_ms > 3000:
            log_level = logging.ERROR
            emoji = "🔴" if USE_EMOJIS else "[!]"
            label = "CRITICAL"
        elif total_duration_ms > 1000:
            log_level = logging.WARNING
            emoji = "🟡" if USE_EMOJIS else "[*]"
            label = "SLOW"
        elif total_duration_ms > 500:
            log_level = logging.INFO
            emoji = "🟢" if USE_EMOJIS else "[+]"
            label = "OK"
        else:
            log_level = logging.INFO  # Changed from DEBUG to INFO so we always see it
            emoji = "⚡" if USE_EMOJIS else "[>]"
            label = "FAST"
        
        log_prefix = f"{emoji} {label}"
        
        # Build checkpoint summary - only show meaningful checkpoints (>0.1ms)
        checkpoint_summary = ""
        if self.checkpoints:
            checkpoint_lines = []
            prev_elapsed = 0.0
            
            for cp in self.checkpoints:
                duration = cp.elapsed_ms - prev_elapsed
                # Only show checkpoints that took meaningful time
                if duration > 0.1:
                    checkpoint_lines.append(f"  • {cp.name}: {duration:.2f}ms")
                prev_elapsed = cp.elapsed_ms
            
            if checkpoint_lines:
                checkpoint_summary = "\n" + "\n".join(checkpoint_lines)
        
        # Log the complete flow
        log_performance(
            LogLevel.INFO,
            f"{self.flow_name} completed",
            duration_ms=total_duration_ms,
            extra={"status": status, "checkpoints": len(self.checkpoints)}
        )
        
        # Also print to console for visibility
        print(
            f"\n{log_prefix} [{self.flow_name}] {total_duration_ms:.2f}ms ({status})"
            f"{checkpoint_summary}\n"
        )
        
        # Also log structured data for potential database storage
        log_performance(
            LogLevel.DEBUG,
            "Flow completed",
            duration_ms=total_duration_ms,
            extra={
                    "flow_name": self.flow_name,
                    "user_id": self.user_id,
                    "duration_ms": total_duration_ms,
                    "status": status,
                    "checkpoints": [
                        {
                            "name": cp.name,
                            "elapsed_ms": cp.elapsed_ms,
                            "metadata": cp.metadata
                        }
                        for cp in self.checkpoints
                    ],
                    "metadata": self.metadata
                }
            )


@contextmanager
def measure_time(operation_name: str, metadata: Optional[Dict[str, Any]] = None):
    """
    Context manager to measure operation time.
    
    Usage:
        with measure_time("database_query", {"query": "SELECT * FROM players"}):
            result = db.query(...)
    
    Args:
        operation_name: Name of the operation being measured
        metadata: Optional metadata about the operation
    """
    start_time = time.perf_counter()
    
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        # Log if operation is slow
        if duration_ms > 100:
            log_performance(
                LogLevel.WARNING,
                operation_name,
                duration_ms=duration_ms,
                extra={"operation": operation_name, "duration_ms": duration_ms, **(metadata or {})}
            )
        elif duration_ms > 10:
            log_performance(
                LogLevel.DEBUG,
                operation_name,
                duration_ms=duration_ms,
                extra={"operation": operation_name, "duration_ms": duration_ms, **(metadata or {})}
            )


class PerformanceMonitor:
    """
    Real-time performance monitoring with alerting.
    
    Tracks recent metrics and alerts on slow operations.
    """
    
    def __init__(self):
        self.alert_thresholds = {
            "queue_command": 500,
            "setup_command": 1000,
            "profile_command": 300,
            "leaderboard_command": 500,
            "activate_command": 200,
            "setcountry_command": 150,
            "termsofservice_command": 100,
        }
        self.default_threshold = 1000
        
    def check_threshold(self, flow_name: str, duration_ms: float) -> bool:
        """
        Check if a flow exceeded its performance threshold.
        
        Returns:
            True if threshold exceeded, False otherwise
        """
        threshold = self.alert_thresholds.get(flow_name, self.default_threshold)
        
        if duration_ms > threshold:
            self.alert_slow_operation(flow_name, duration_ms, threshold)
            return True
        
        return False
    
    def alert_slow_operation(
        self, 
        flow_name: str, 
        duration_ms: float, 
        threshold: float
    ) -> None:
        """Alert on slow operations."""
        log_performance(
            LogLevel.WARNING,
            f"SLOW: {flow_name}",
            duration_ms=duration_ms,
            extra={
                "threshold_ms": threshold,
                "over_threshold_percent": ((duration_ms/threshold - 1) * 100)
            }
        )


# Global performance monitor instance
performance_monitor = PerformanceMonitor()


def get_performance_monitor() -> PerformanceMonitor:
    """Get the global performance monitor instance."""
    return performance_monitor

