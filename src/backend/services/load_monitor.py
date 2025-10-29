"""
Load monitoring service for tracking system capacity and bottlenecks.

This service provides real-time metrics for:
- Process pool queue depth
- Database write queue depth
- Active match count
- Memory usage
- Discord API usage

Designed to help identify when the system is approaching capacity limits.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

import psutil


logger = logging.getLogger(__name__)


@dataclass
class LoadMetrics:
    """Snapshot of system load at a point in time."""
    timestamp: datetime
    
    # Process pool metrics
    process_pool_queue_depth: int
    process_pool_active_tasks: int
    process_pool_worker_count: int
    
    # Database write queue metrics
    db_write_queue_depth: int
    db_writes_completed: int
    db_writes_pending: int
    
    # Match metrics
    active_matches: int
    queued_players: int
    
    # System metrics
    memory_usage_mb: float
    memory_percent: float
    cpu_percent: float
    
    # Rate metrics (operations per second)
    discord_api_calls_per_second: float
    db_writes_per_second: float
    replays_parsed_per_second: float


class LoadMonitor:
    """
    Monitors system load and provides metrics for capacity planning.
    
    Usage:
        monitor = LoadMonitor()
        await monitor.start()
        
        # Later...
        metrics = monitor.get_current_metrics()
        if metrics.process_pool_queue_depth > 10:
            logger.warning("Replay parsing queue building up!")
    """
    
    def __init__(self):
        """Initialize the load monitor."""
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        
        # Metrics history (keep last 60 data points = 1 minute at 1 sample/second)
        self._metrics_history: List[LoadMetrics] = []
        self._max_history_length = 60
        
        # Rate tracking
        self._last_discord_calls = 0
        self._last_db_writes = 0
        self._last_replays_parsed = 0
        self._last_rate_check = time.time()
        
        # Peak tracking
        self._peak_queue_depth = 0
        self._peak_active_matches = 0
        self._peak_memory_mb = 0.0
        
        # Alert thresholds (from PEAK_LOAD_ANALYSIS.md)
        self.REPLAY_QUEUE_ALERT = 10
        self.REPLAY_QUEUE_CRITICAL = 20
        self.DB_QUEUE_ALERT = 100
        self.DB_QUEUE_CRITICAL = 500
        self.MEMORY_ALERT_PERCENT = 70
        self.MEMORY_CRITICAL_PERCENT = 85
        
    async def start(self):
        """Start the background monitoring task."""
        if self._running:
            logger.warning("[LoadMonitor] Already running")
            return
        
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("[LoadMonitor] Started")
    
    async def stop(self):
        """Stop the background monitoring task."""
        if not self._running:
            return
        
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        logger.info("[LoadMonitor] Stopped")
    
    async def _monitor_loop(self):
        """Main monitoring loop - runs every second."""
        try:
            while self._running:
                try:
                    metrics = await self._collect_metrics()
                    self._update_history(metrics)
                    self._check_thresholds(metrics)
                    self._update_peaks(metrics)
                except Exception as e:
                    logger.exception(f"[LoadMonitor] Error collecting metrics: {e}")
                
                await asyncio.sleep(1.0)  # Sample every second
        except asyncio.CancelledError:
            logger.info("[LoadMonitor] Monitor loop cancelled")
    
    async def _collect_metrics(self) -> LoadMetrics:
        """Collect current system metrics."""
        from src.backend.services.data_access_service import DataAccessService
        from src.backend.services.queue_service import get_queue_service
        from src.backend.services.match_completion_service import match_completion_service
        
        # Get process info
        process = psutil.Process()
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        memory_percent = process.memory_percent()
        cpu_percent = process.cpu_percent(interval=0.1)
        
        # Get DataAccessService metrics
        data_service = DataAccessService()
        db_queue_depth = data_service._write_queue.qsize() if data_service._write_queue else 0
        db_writes_completed = getattr(data_service, '_total_writes_completed', 0)
        db_writes_pending = getattr(data_service, '_total_writes_queued', 0) - db_writes_completed
        
        # Get queue service metrics
        queue_service = get_queue_service()
        queued_players = queue_service.get_queue_size() if queue_service else 0
        
        # Get match completion service metrics
        active_matches = len(match_completion_service.monitored_matches) if match_completion_service else 0
        
        # Calculate rates
        current_time = time.time()
        time_delta = current_time - self._last_rate_check
        
        # Note: These counters would need to be tracked globally
        # For now, we'll estimate from queue changes
        discord_rate = 0.0  # TODO: Add global Discord API call counter
        db_rate = (db_writes_completed - self._last_db_writes) / time_delta if time_delta > 0 else 0.0
        replay_rate = 0.0  # TODO: Add replay parse counter
        
        self._last_db_writes = db_writes_completed
        self._last_rate_check = current_time
        
        # Process pool metrics (would need to be tracked separately)
        # For now, use placeholder values
        process_pool_queue = 0  # TODO: Add process pool queue tracking
        process_pool_active = 0  # TODO: Add active task tracking
        process_pool_workers = 2  # From config
        
        return LoadMetrics(
            timestamp=datetime.now(timezone.utc),
            process_pool_queue_depth=process_pool_queue,
            process_pool_active_tasks=process_pool_active,
            process_pool_worker_count=process_pool_workers,
            db_write_queue_depth=db_queue_depth,
            db_writes_completed=db_writes_completed,
            db_writes_pending=db_writes_pending,
            active_matches=active_matches,
            queued_players=queued_players,
            memory_usage_mb=memory_mb,
            memory_percent=memory_percent,
            cpu_percent=cpu_percent,
            discord_api_calls_per_second=discord_rate,
            db_writes_per_second=db_rate,
            replays_parsed_per_second=replay_rate
        )
    
    def _update_history(self, metrics: LoadMetrics):
        """Add metrics to history and trim if needed."""
        self._metrics_history.append(metrics)
        if len(self._metrics_history) > self._max_history_length:
            self._metrics_history.pop(0)
    
    def _update_peaks(self, metrics: LoadMetrics):
        """Track peak values."""
        if metrics.process_pool_queue_depth > self._peak_queue_depth:
            self._peak_queue_depth = metrics.process_pool_queue_depth
        
        if metrics.active_matches > self._peak_active_matches:
            self._peak_active_matches = metrics.active_matches
        
        if metrics.memory_usage_mb > self._peak_memory_mb:
            self._peak_memory_mb = metrics.memory_usage_mb
    
    def _check_thresholds(self, metrics: LoadMetrics):
        """Check metrics against alert thresholds."""
        # Replay queue depth
        if metrics.process_pool_queue_depth >= self.REPLAY_QUEUE_CRITICAL:
            logger.error(
                f"[LoadMonitor] CRITICAL: Replay queue depth = {metrics.process_pool_queue_depth} "
                f"(threshold: {self.REPLAY_QUEUE_CRITICAL})"
            )
        elif metrics.process_pool_queue_depth >= self.REPLAY_QUEUE_ALERT:
            logger.warning(
                f"[LoadMonitor] WARNING: Replay queue depth = {metrics.process_pool_queue_depth} "
                f"(threshold: {self.REPLAY_QUEUE_ALERT})"
            )
        
        # Database write queue depth
        if metrics.db_write_queue_depth >= self.DB_QUEUE_CRITICAL:
            logger.error(
                f"[LoadMonitor] CRITICAL: DB write queue depth = {metrics.db_write_queue_depth} "
                f"(threshold: {self.DB_QUEUE_CRITICAL})"
            )
        elif metrics.db_write_queue_depth >= self.DB_QUEUE_ALERT:
            logger.warning(
                f"[LoadMonitor] WARNING: DB write queue depth = {metrics.db_write_queue_depth} "
                f"(threshold: {self.DB_QUEUE_ALERT})"
            )
        
        # Memory usage
        if metrics.memory_percent >= self.MEMORY_CRITICAL_PERCENT:
            logger.error(
                f"[LoadMonitor] CRITICAL: Memory usage = {metrics.memory_percent:.1f}% "
                f"({metrics.memory_usage_mb:.0f} MB, threshold: {self.MEMORY_CRITICAL_PERCENT}%)"
            )
        elif metrics.memory_percent >= self.MEMORY_ALERT_PERCENT:
            logger.warning(
                f"[LoadMonitor] WARNING: Memory usage = {metrics.memory_percent:.1f}% "
                f"({metrics.memory_usage_mb:.0f} MB, threshold: {self.MEMORY_ALERT_PERCENT}%)"
            )
    
    def get_current_metrics(self) -> Optional[LoadMetrics]:
        """Get the most recent metrics snapshot."""
        return self._metrics_history[-1] if self._metrics_history else None
    
    def get_average_metrics(self, seconds: int = 60) -> Optional[Dict[str, float]]:
        """
        Get average metrics over the last N seconds.
        
        Args:
            seconds: Number of seconds to average (max 60)
            
        Returns:
            Dictionary of averaged metrics, or None if insufficient data
        """
        if not self._metrics_history:
            return None
        
        # Get samples (1 per second)
        samples = self._metrics_history[-seconds:] if len(self._metrics_history) >= seconds else self._metrics_history
        
        if not samples:
            return None
        
        return {
            'avg_process_pool_queue_depth': sum(m.process_pool_queue_depth for m in samples) / len(samples),
            'avg_db_write_queue_depth': sum(m.db_write_queue_depth for m in samples) / len(samples),
            'avg_active_matches': sum(m.active_matches for m in samples) / len(samples),
            'avg_queued_players': sum(m.queued_players for m in samples) / len(samples),
            'avg_memory_mb': sum(m.memory_usage_mb for m in samples) / len(samples),
            'avg_cpu_percent': sum(m.cpu_percent for m in samples) / len(samples),
            'avg_discord_calls_per_sec': sum(m.discord_api_calls_per_second for m in samples) / len(samples),
            'avg_db_writes_per_sec': sum(m.db_writes_per_second for m in samples) / len(samples),
        }
    
    def get_peak_metrics(self) -> Dict[str, float]:
        """Get peak values since monitoring started."""
        return {
            'peak_queue_depth': self._peak_queue_depth,
            'peak_active_matches': self._peak_active_matches,
            'peak_memory_mb': self._peak_memory_mb,
        }
    
    def get_status_summary(self) -> str:
        """
        Get a human-readable status summary.
        
        Returns:
            Multi-line string with current system status
        """
        current = self.get_current_metrics()
        if not current:
            return "No metrics available yet"
        
        averages = self.get_average_metrics(60)
        peaks = self.get_peak_metrics()
        
        status_lines = [
            "=== System Load Status ===",
            f"Timestamp: {current.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "",
            "Current:",
            f"  Active Matches: {current.active_matches}",
            f"  Queued Players: {current.queued_players}",
            f"  Replay Queue: {current.process_pool_queue_depth}",
            f"  DB Write Queue: {current.db_write_queue_depth}",
            f"  Memory: {current.memory_usage_mb:.0f} MB ({current.memory_percent:.1f}%)",
            f"  CPU: {current.cpu_percent:.1f}%",
            "",
        ]
        
        if averages:
            status_lines.extend([
                "1-Minute Averages:",
                f"  Active Matches: {averages['avg_active_matches']:.1f}",
                f"  Replay Queue: {averages['avg_process_pool_queue_depth']:.1f}",
                f"  DB Write Queue: {averages['avg_db_write_queue_depth']:.1f}",
                f"  DB Writes/sec: {averages['avg_db_writes_per_sec']:.2f}",
                "",
            ])
        
        status_lines.extend([
            "Peaks (Since Start):",
            f"  Replay Queue: {peaks['peak_queue_depth']}",
            f"  Active Matches: {peaks['peak_active_matches']}",
            f"  Memory: {peaks['peak_memory_mb']:.0f} MB",
        ])
        
        return "\n".join(status_lines)


# Global singleton instance
_load_monitor: Optional[LoadMonitor] = None


def get_load_monitor() -> LoadMonitor:
    """Get or create the global load monitor instance."""
    global _load_monitor
    if _load_monitor is None:
        _load_monitor = LoadMonitor()
    return _load_monitor


async def initialize_load_monitor():
    """Initialize and start the load monitor."""
    monitor = get_load_monitor()
    await monitor.start()
    logger.info("[LoadMonitor] Initialized and started")
    return monitor

