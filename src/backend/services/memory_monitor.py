"""
Memory monitoring service for tracking memory usage and detecting leaks.

Provides comprehensive memory tracking for both main and worker processes.
"""

import gc
import logging
import os
import psutil
import tracemalloc
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class MemoryMonitor:
    """
    Monitor memory usage and track allocations.
    
    Uses both psutil for process-level monitoring and tracemalloc for
    detailed allocation tracking.
    """
    
    def __init__(self, enable_tracemalloc: bool = True):
        """
        Initialize memory monitor.
        
        Args:
            enable_tracemalloc: Whether to enable detailed allocation tracking
        """
        self.process = psutil.Process(os.getpid())
        self.baseline_memory = None
        self.tracemalloc_enabled = False
        
        if enable_tracemalloc:
            try:
                tracemalloc.start()
                self.tracemalloc_enabled = True
                logger.info("[Memory Monitor] tracemalloc started")
            except Exception as e:
                logger.warning(f"[Memory Monitor] Failed to start tracemalloc: {e}")
        
        # Record baseline
        self.baseline_memory = self.get_memory_usage()
        logger.info(f"[Memory Monitor] Baseline memory: {self.baseline_memory:.2f} MB")
    
    def get_memory_usage(self) -> float:
        """
        Get current memory usage in MB.
        
        Returns:
            Memory usage in megabytes
        """
        try:
            # Get resident set size (actual physical memory used)
            memory_info = self.process.memory_info()
            return memory_info.rss / 1024 / 1024  # Convert to MB
        except Exception as e:
            logger.error(f"[Memory Monitor] Failed to get memory usage: {e}")
            return 0.0
    
    def get_memory_details(self) -> Dict[str, float]:
        """
        Get detailed memory information.
        
        Returns:
            Dictionary with memory details (all values in MB)
        """
        try:
            memory_info = self.process.memory_info()
            
            details = {
                'rss': memory_info.rss / 1024 / 1024,  # Resident Set Size
                'vms': memory_info.vms / 1024 / 1024,  # Virtual Memory Size
                'percent': self.process.memory_percent(),
            }
            
            # Add shared memory if available (Unix-like systems)
            if hasattr(memory_info, 'shared'):
                details['shared'] = memory_info.shared / 1024 / 1024
            
            return details
        except Exception as e:
            logger.error(f"[Memory Monitor] Failed to get memory details: {e}")
            return {}
    
    def get_memory_delta(self) -> float:
        """
        Get change in memory since baseline.
        
        Returns:
            Memory delta in megabytes
        """
        if self.baseline_memory is None:
            return 0.0
        
        current = self.get_memory_usage()
        return current - self.baseline_memory
    
    def get_top_allocations(self, limit: int = 10) -> Optional[list]:
        """
        Get top memory allocations using tracemalloc.
        
        Args:
            limit: Number of top allocations to return
            
        Returns:
            List of (filename, lineno, size_mb) tuples or None if tracemalloc disabled
        """
        if not self.tracemalloc_enabled:
            return None
        
        try:
            snapshot = tracemalloc.take_snapshot()
            top_stats = snapshot.statistics('lineno')
            
            allocations = []
            for stat in top_stats[:limit]:
                size_mb = stat.size / 1024 / 1024
                allocations.append((stat.traceback.format()[0], size_mb))
            
            return allocations
        except Exception as e:
            logger.error(f"[Memory Monitor] Failed to get top allocations: {e}")
            return None
    
    def force_garbage_collection(self) -> Tuple[int, float]:
        """
        Force garbage collection and report freed memory.
        
        Returns:
            Tuple of (objects_collected, memory_freed_mb)
        """
        before = self.get_memory_usage()
        collected = gc.collect()
        after = self.get_memory_usage()
        freed = before - after
        
        logger.info(f"[Memory Monitor] GC: Collected {collected} objects, "
                   f"freed {freed:.2f} MB")
        
        return collected, freed
    
    def generate_report(self, include_allocations: bool = False) -> str:
        """
        Generate a comprehensive memory report.
        
        Args:
            include_allocations: Whether to include top allocations
            
        Returns:
            Formatted memory report string
        """
        details = self.get_memory_details()
        delta = self.get_memory_delta()
        
        report_lines = [
            "=" * 60,
            "MEMORY USAGE REPORT",
            "=" * 60,
            f"Current RSS:     {details.get('rss', 0):.2f} MB",
            f"Virtual Memory:  {details.get('vms', 0):.2f} MB",
            f"Memory Percent:  {details.get('percent', 0):.2f}%",
        ]
        
        if 'shared' in details:
            report_lines.append(f"Shared Memory:   {details['shared']:.2f} MB")
        
        if self.baseline_memory is not None:
            report_lines.append(f"Baseline:        {self.baseline_memory:.2f} MB")
            report_lines.append(f"Delta:           {delta:+.2f} MB")
        
        if include_allocations and self.tracemalloc_enabled:
            allocations = self.get_top_allocations(5)
            if allocations:
                report_lines.append("")
                report_lines.append("Top 5 Allocations:")
                report_lines.append("-" * 60)
                for location, size_mb in allocations:
                    report_lines.append(f"  {size_mb:.2f} MB: {location}")
        
        report_lines.append("=" * 60)
        
        return "\n".join(report_lines)
    
    def log_memory_usage(self, context: str = ""):
        """
        Log current memory usage with optional context.
        
        Args:
            context: Context string to identify where the log is from
        """
        memory = self.get_memory_usage()
        delta = self.get_memory_delta()
        
        log_msg = f"[Memory Monitor] {memory:.2f} MB"
        if delta != 0:
            log_msg += f" (Delta {delta:+.2f} MB)"
        if context:
            log_msg += f" - {context}"
        
        logger.info(log_msg)
        print(log_msg)
    
    def check_memory_leak(self, threshold_mb: float = 50.0) -> bool:
        """
        Check if memory usage has grown beyond threshold.
        
        Args:
            threshold_mb: Threshold in MB for leak detection
            
        Returns:
            True if potential leak detected
        """
        delta = self.get_memory_delta()
        
        if delta > threshold_mb:
            logger.warning(f"[Memory Monitor] Potential memory leak detected! "
                          f"Growth: {delta:.2f} MB (threshold: {threshold_mb:.2f} MB)")
            return True
        
        return False


# Global memory monitor instance
_memory_monitor: Optional[MemoryMonitor] = None


def initialize_memory_monitor(enable_tracemalloc: bool = True) -> MemoryMonitor:
    """
    Initialize the global memory monitor.
    
    Args:
        enable_tracemalloc: Whether to enable detailed allocation tracking
        
    Returns:
        Initialized MemoryMonitor instance
    """
    global _memory_monitor
    _memory_monitor = MemoryMonitor(enable_tracemalloc=enable_tracemalloc)
    return _memory_monitor


def get_memory_monitor() -> Optional[MemoryMonitor]:
    """Get the global memory monitor instance."""
    return _memory_monitor


def log_memory(context: str = ""):
    """Quick helper to log memory usage."""
    if _memory_monitor:
        _memory_monitor.log_memory_usage(context)
