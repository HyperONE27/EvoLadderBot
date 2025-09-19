"""Matchmaking service for ladder queue management."""
import asyncio
import random
import string
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Dict, Set
from sqlalchemy import select, and_, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from ..db.models import User, QueueEntry, MapPool, Match, Race, MatchResult
from .ratings import RatingCalculator
from .region_mapping import RegionMappingService


class MatchmakingService:
    """Service for managing the matchmaking queue and creating matches."""
    
    # Queue timeout in seconds (5 minutes)
    QUEUE_TIMEOUT = 300
    
    # MMR difference thresholds
    STRICT_MMR_THRESHOLD = 200   # Initial strict matching
    LOOSE_MMR_THRESHOLD = 500    # After 2 minutes
    MAX_MMR_THRESHOLD = 1000     # After 4 minutes
    
    # Time thresholds for relaxing MMR requirements
    STRICT_TIME = 0              # 0-2 minutes
    LOOSE_TIME = 120            # 2-4 minutes  
    MAX_TIME = 240              # 4+ minutes
    
    def __init__(self):
        """Initialize the matchmaking service."""
        self.region_service = RegionMappingService()
    
    @staticmethod
    async def add_to_queue(
        session: AsyncSession,
        user: User,
        races: List[str],
        map_vetoes: List[str]
    ) -> QueueEntry:
        """Add a player to the matchmaking queue."""
        # Remove any existing queue entries for this user
        await session.execute(
            delete(QueueEntry).where(
                and_(
                    QueueEntry.user_id == user.id,
                    QueueEntry.is_active == True
                )
            )
        )
        
        # Create new queue entry
        queue_entry = QueueEntry(
            user_id=user.id,
            discord_id=user.discord_id,
            races=races,
            map_vetoes=map_vetoes,
            expires_at=datetime.utcnow() + timedelta(seconds=MatchmakingService.QUEUE_TIMEOUT),
            is_active=True
        )
        
        session.add(queue_entry)
        await session.flush()
        return queue_entry
    
    @staticmethod
    async def remove_from_queue(session: AsyncSession, discord_id: int) -> bool:
        """Remove a player from the queue."""
        result = await session.execute(
            select(QueueEntry).where(
                and_(
                    QueueEntry.discord_id == discord_id,
                    QueueEntry.is_active == True
                )
            )
        )
        queue_entry = result.scalar_one_or_none()
        
        if queue_entry:
            queue_entry.is_active = False
            await session.flush()
            return True
        return False
    
    @staticmethod
    async def get_queue_position(session: AsyncSession, discord_id: int) -> Optional[Tuple[int, int]]:
        """Get a player's position in queue. Returns (position, total_in_queue)."""
        # Get all active queue entries ordered by join time
        result = await session.execute(
            select(QueueEntry).where(QueueEntry.is_active == True).order_by(QueueEntry.joined_at)
        )
        entries = result.scalars().all()
        
        position = None
        for i, entry in enumerate(entries):
            if entry.discord_id == discord_id:
                position = i + 1
                break
        
        if position is None:
            return None
            
        return position, len(entries)
    
    @staticmethod
    async def find_matches(session: AsyncSession) -> List[Tuple[QueueEntry, QueueEntry, Dict]]:
        """Find all possible matches in the current queue."""
        # Clean up expired entries
        await session.execute(
            delete(QueueEntry).where(
                or_(
                    QueueEntry.expires_at < datetime.utcnow(),
                    QueueEntry.is_active == False
                )
            )
        )
        
        # Get all active queue entries with their users
        result = await session.execute(
            select(QueueEntry).where(QueueEntry.is_active == True)
            .options(selectinload(QueueEntry.user))
            .order_by(QueueEntry.joined_at)
        )
        entries = list(result.scalars().all())
        
        matches = []
        used_entries = set()
        
        # Try to match players
        for i, entry1 in enumerate(entries):
            if entry1.id in used_entries:
                continue
                
            for entry2 in entries[i+1:]:
                if entry2.id in used_entries:
                    continue
                
                # Check if match is valid
                match_info = await MatchmakingService._evaluate_match(
                    session, entry1, entry2
                )
                
                if match_info:
                    matches.append((entry1, entry2, match_info))
                    used_entries.add(entry1.id)
                    used_entries.add(entry2.id)
                    break
        
        return matches
    
    @staticmethod
    async def _evaluate_match(
        session: AsyncSession,
        entry1: QueueEntry,
        entry2: QueueEntry
    ) -> Optional[Dict]:
        """Evaluate if two queue entries can be matched."""
        user1 = entry1.user
        user2 = entry2.user
        
        # Check if one player has BW races and the other has SC2 races
        entry1_bw = any(race.startswith("bw_") for race in entry1.races)
        entry1_sc2 = any(race.startswith("sc2_") for race in entry1.races)
        entry2_bw = any(race.startswith("bw_") for race in entry2.races)
        entry2_sc2 = any(race.startswith("sc2_") for race in entry2.races)
        
        # Valid match requires one BW and one SC2 player
        if not ((entry1_bw and entry2_sc2) or (entry1_sc2 and entry2_bw)):
            return None
        
        # Calculate time in queue
        now = datetime.utcnow()
        time1 = (now - entry1.joined_at).total_seconds()
        time2 = (now - entry2.joined_at).total_seconds()
        max_wait = max(time1, time2)
        
        # Determine MMR threshold based on wait time
        if max_wait < MatchmakingService.LOOSE_TIME:
            mmr_threshold = MatchmakingService.STRICT_MMR_THRESHOLD
        elif max_wait < MatchmakingService.MAX_TIME:
            mmr_threshold = MatchmakingService.LOOSE_MMR_THRESHOLD
        else:
            mmr_threshold = MatchmakingService.MAX_MMR_THRESHOLD
        
        # Find best race matchup based on MMR
        best_matchup = None
        best_mmr_diff = float('inf')
        
        for race1 in entry1.races:
            race1_enum = Race(race1)
            mmr1 = user1.get_mmr(race1_enum)
            
            for race2 in entry2.races:
                race2_enum = Race(race2)
                mmr2 = user2.get_mmr(race2_enum)
                
                # Check if valid BW vs SC2
                if not ((race1.startswith("bw_") and race2.startswith("sc2_")) or 
                       (race1.startswith("sc2_") and race2.startswith("bw_"))):
                    continue
                
                mmr_diff = abs(mmr1 - mmr2)
                
                if mmr_diff <= mmr_threshold and mmr_diff < best_mmr_diff:
                    best_mmr_diff = mmr_diff
                    best_matchup = (race1_enum, race2_enum, mmr1, mmr2)
        
        if not best_matchup:
            return None
        
        race1, race2, mmr1, mmr2 = best_matchup
        
        # Select map (excluding vetoes)
        all_vetoes = set(entry1.map_vetoes + entry2.map_vetoes)
        map_name = await MatchmakingService._select_map(session, all_vetoes)
        
        if not map_name:
            return None
        
        # Get best server
        server = MatchmakingService._get_best_server(user1, user2)
        
        # Generate channel name
        channel = MatchmakingService._generate_channel_name()
        
        return {
            "player1_race": race1,
            "player2_race": race2,
            "player1_mmr": mmr1,
            "player2_mmr": mmr2,
            "map_name": map_name,
            "server_region": server,
            "channel_name": channel,
            "mmr_difference": best_mmr_diff,
            "wait_time": max_wait,
        }
    
    @staticmethod
    async def _select_map(session: AsyncSession, vetoes: Set[str]) -> Optional[str]:
        """Select a random map excluding vetoes."""
        result = await session.execute(
            select(MapPool).where(
                and_(
                    MapPool.is_active == True,
                    ~MapPool.map_name.in_(vetoes) if vetoes else True
                )
            )
        )
        available_maps = result.scalars().all()
        
        if not available_maps:
            # If all maps are vetoed, ignore vetoes
            result = await session.execute(
                select(MapPool).where(MapPool.is_active == True)
            )
            available_maps = result.scalars().all()
        
        if not available_maps:
            return None
        
        return random.choice(available_maps).map_name
    
    @staticmethod
    def _get_best_server(user1: User, user2: User) -> str:
        """Get the best server for two users based on their regions."""
        # If either user has no region, default to NAC
        if not user1.region_code or not user2.region_code:
            return "NAC"
        
        service = RegionMappingService()
        return service.get_best_server(user1.region_code, user2.region_code)
    
    @staticmethod
    def _generate_channel_name() -> str:
        """Generate a unique channel name like 'scevo123'."""
        digits = ''.join(random.choices(string.digits, k=3))
        return f"scevo{digits}"
    
    @staticmethod
    async def create_match(
        session: AsyncSession,
        entry1: QueueEntry,
        entry2: QueueEntry,
        match_info: Dict
    ) -> Match:
        """Create a match from two queue entries."""
        match = Match(
            player1_id=entry1.user_id,
            player2_id=entry2.user_id,
            player1_race=match_info["player1_race"],
            player2_race=match_info["player2_race"],
            map_name=match_info["map_name"],
            server_region=match_info["server_region"],
            channel_name=match_info["channel_name"],
            player1_mmr_before=match_info["player1_mmr"],
            player2_mmr_before=match_info["player2_mmr"],
        )
        
        session.add(match)
        
        # Remove both players from queue
        entry1.is_active = False
        entry2.is_active = False
        
        await session.flush()
        return match
    
    @staticmethod
    async def report_match_result(
        session: AsyncSession,
        match_id: int,
        result: MatchResult,
        duration_seconds: Optional[int] = None
    ) -> Match:
        """Report the result of a match and update ratings."""
        match = await session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} not found")
        
        if match.result is not None:
            raise ValueError(f"Match {match_id} already has a result")
        
        # Get both users
        user1 = await session.get(User, match.player1_id)
        user2 = await session.get(User, match.player2_id)
        
        # Calculate games played for K-factor
        games1 = user1.wins_1v1 + user1.losses_1v1 + user1.draws_1v1
        games2 = user2.wins_1v1 + user2.losses_1v1 + user2.draws_1v1
        
        # Calculate new ratings
        new_rating1, new_rating2, change1, change2 = RatingCalculator.calculate_match_ratings(
            match.player1_mmr_before,
            match.player2_mmr_before,
            games1,
            games2,
            result
        )
        
        # Update match
        match.result = result
        match.ended_at = datetime.utcnow()
        match.duration_seconds = duration_seconds
        match.player1_mmr_after = new_rating1
        match.player2_mmr_after = new_rating2
        match.player1_mmr_change = change1
        match.player2_mmr_change = change2
        
        # Update user ratings
        user1.set_mmr(match.player1_race, new_rating1)
        user2.set_mmr(match.player2_race, new_rating2)
        
        # Update stats
        if result == MatchResult.PLAYER1_WIN:
            user1.wins_1v1 += 1
            user2.losses_1v1 += 1
        elif result == MatchResult.PLAYER2_WIN:
            user1.losses_1v1 += 1
            user2.wins_1v1 += 1
        elif result == MatchResult.DRAW:
            user1.draws_1v1 += 1
            user2.draws_1v1 += 1
        
        # Update last active
        user1.last_active_at = datetime.utcnow()
        user2.last_active_at = datetime.utcnow()
        
        await session.flush()
        return match