"""Database models for EvoLadderBot."""
from datetime import datetime
from typing import List, Optional
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Float, ForeignKey, 
    Integer, String, Table, Text, JSON, Enum as SQLEnum, 
    UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.postgresql import ARRAY
import enum

Base = declarative_base()


class Race(enum.Enum):
    """Enum for available races."""
    BW_TERRAN = "bw_terran"
    BW_ZERG = "bw_zerg" 
    BW_PROTOSS = "bw_protoss"
    SC2_TERRAN = "sc2_terran"
    SC2_ZERG = "sc2_zerg"
    SC2_PROTOSS = "sc2_protoss"


class MatchResult(enum.Enum):
    """Enum for match results."""
    PLAYER1_WIN = "player1_win"
    PLAYER2_WIN = "player2_win"
    DRAW = "draw"
    CANCELLED = "cancelled"


class User(Base):
    """User model storing player information and statistics."""
    __tablename__ = "users"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Discord integration
    discord_id = Column(BigInteger, unique=True, nullable=False, index=True)
    
    # User identification
    main_id = Column(String(12), nullable=True)  # 3-12 alphanumeric chars
    alt_ids = Column(ARRAY(String(12)), default=[])  # Array of alternate IDs
    battle_tag = Column(String(25), nullable=True)  # Format: Name#1234
    
    # Demographics
    country_code = Column(String(2), nullable=True)  # ISO country code
    region_code = Column(String(3), nullable=True)  # Region code from regions.json
    
    # Account status
    terms_accepted = Column(Boolean, default=False, nullable=False)
    terms_accepted_at = Column(DateTime, nullable=True)
    setup_completed = Column(Boolean, default=False, nullable=False)
    setup_completed_at = Column(DateTime, nullable=True)
    
    # Game preferences
    map_vetoes = Column(ARRAY(String), default=[])  # Current map vetoes
    last_queue_races = Column(ARRAY(String), default=[])  # Last races queued with
    
    # MMR for each race (starting at 1500)
    mmr_bw_terran = Column(Float, default=1500.0, nullable=False)
    mmr_bw_zerg = Column(Float, default=1500.0, nullable=False)
    mmr_bw_protoss = Column(Float, default=1500.0, nullable=False)
    mmr_sc2_terran = Column(Float, default=1500.0, nullable=False)
    mmr_sc2_zerg = Column(Float, default=1500.0, nullable=False)
    mmr_sc2_protoss = Column(Float, default=1500.0, nullable=False)
    
    # Statistics
    wins_1v1 = Column(Integer, default=0, nullable=False)
    losses_1v1 = Column(Integer, default=0, nullable=False)
    draws_1v1 = Column(Integer, default=0, nullable=False)
    
    # Account management
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_active_at = Column(DateTime, nullable=True)
    
    # Moderation
    is_banned = Column(Boolean, default=False, nullable=False)
    ban_reason = Column(Text, nullable=True)
    ban_expires_at = Column(DateTime, nullable=True)
    
    # Relationships
    matches_as_player1 = relationship("Match", foreign_keys="Match.player1_id", back_populates="player1")
    matches_as_player2 = relationship("Match", foreign_keys="Match.player2_id", back_populates="player2")
    
    def get_mmr(self, race: Race) -> float:
        """Get MMR for a specific race."""
        mmr_map = {
            Race.BW_TERRAN: self.mmr_bw_terran,
            Race.BW_ZERG: self.mmr_bw_zerg,
            Race.BW_PROTOSS: self.mmr_bw_protoss,
            Race.SC2_TERRAN: self.mmr_sc2_terran,
            Race.SC2_ZERG: self.mmr_sc2_zerg,
            Race.SC2_PROTOSS: self.mmr_sc2_protoss,
        }
        return mmr_map.get(race, 1500.0)
    
    def set_mmr(self, race: Race, value: float):
        """Set MMR for a specific race."""
        if race == Race.BW_TERRAN:
            self.mmr_bw_terran = value
        elif race == Race.BW_ZERG:
            self.mmr_bw_zerg = value
        elif race == Race.BW_PROTOSS:
            self.mmr_bw_protoss = value
        elif race == Race.SC2_TERRAN:
            self.mmr_sc2_terran = value
        elif race == Race.SC2_ZERG:
            self.mmr_sc2_zerg = value
        elif race == Race.SC2_PROTOSS:
            self.mmr_sc2_protoss = value


class Match(Base):
    """Match model storing game information."""
    __tablename__ = "matches"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Players
    player1_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    player2_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Races played
    player1_race = Column(SQLEnum(Race), nullable=False)
    player2_race = Column(SQLEnum(Race), nullable=False)
    
    # Match details
    map_name = Column(String(100), nullable=False)
    server_region = Column(String(3), nullable=False)  # Region code
    channel_name = Column(String(20), nullable=True)  # e.g., "scevo123"
    
    # Timing
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    
    # Result
    result = Column(SQLEnum(MatchResult), nullable=True)
    
    # MMR changes
    player1_mmr_before = Column(Float, nullable=False)
    player2_mmr_before = Column(Float, nullable=False)
    player1_mmr_after = Column(Float, nullable=True)
    player2_mmr_after = Column(Float, nullable=True)
    player1_mmr_change = Column(Float, nullable=True)
    player2_mmr_change = Column(Float, nullable=True)
    
    # Replay data (for future use)
    replay_url = Column(Text, nullable=True)
    replay_data = Column(JSON, nullable=True)  # Can store parsed replay info
    
    # Relationships
    player1 = relationship("User", foreign_keys=[player1_id], back_populates="matches_as_player1")
    player2 = relationship("User", foreign_keys=[player2_id], back_populates="matches_as_player2")
    
    # Constraints
    __table_args__ = (
        CheckConstraint("player1_id != player2_id", name="different_players"),
    )


class MapPool(Base):
    """Current map pool for the ladder."""
    __tablename__ = "map_pool"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    map_name = Column(String(100), unique=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    added_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    removed_at = Column(DateTime, nullable=True)
    order_index = Column(Integer, nullable=False)  # For consistent ordering


class QueueEntry(Base):
    """Tracks players currently in queue."""
    __tablename__ = "queue_entries"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    discord_id = Column(BigInteger, nullable=False)  # For quick lookup
    
    # Queue preferences
    races = Column(ARRAY(String), nullable=False)  # Races they're queuing with
    map_vetoes = Column(ARRAY(String), default=[])  # Maps they've vetoed
    
    # Timing
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)  # Auto-remove after timeout
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Relationships
    user = relationship("User", backref="queue_entries")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("user_id", "is_active", name="one_active_queue_per_user"),
    )
