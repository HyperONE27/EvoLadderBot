"""
Write job data structures for the DataAccessService.

These are separated into their own module to avoid circular import issues
between data_access_service.py and write_log.py.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class WriteJobType(Enum):
    """Types of database write operations."""
    UPDATE_PLAYER = "update_player"
    CREATE_PLAYER = "create_player"
    UPDATE_MMR = "update_mmr"
    CREATE_MMR = "create_mmr"
    UPDATE_PREFERENCES = "update_preferences"
    CREATE_MATCH = "create_match"
    UPDATE_MATCH = "update_match"
    UPDATE_MATCH_REPORT = "update_match_report"
    UPDATE_MATCH_MMR_CHANGE = "update_match_mmr_change"
    INSERT_REPLAY = "insert_replay"
    LOG_PLAYER_ACTION = "log_player_action"
    INSERT_COMMAND_CALL = "insert_command_call"
    ABORT_MATCH = "abort_match"


@dataclass
class WriteJob:
    """
    Represents a single database write operation.
    
    Attributes:
        job_type: Type of write operation
        data: Dictionary of data to write
        timestamp: Unix timestamp of when job was created
        retry_count: Number of times this job has been retried
    """
    job_type: WriteJobType
    data: Dict[str, Any]
    timestamp: float
    retry_count: int = field(default=0)

