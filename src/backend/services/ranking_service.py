"""
Ranking service for MMR-based player rankings.

This module defines the RankingService class, which manages MMR-based rankings
for all player-race combinations. Rankings are calculated using fixed allocation
to ensure mathematical balance across all population sizes.

Distribution:
- S-Rank: 1% of population
- A-Rank: 7% of population  
- B-Rank: 21% of population
- C-Rank: 21% of population
- D-Rank: 21% of population
- E-Rank: 21% of population
- F-Rank: 8% of population
- U-Rank: unranked (no games played or insufficient data)

The adaptive allocation method ensures S+A = F balance and equal middle ranks
by:
1. Rounding down ideal allocations
2. Distributing middle ranks (D-C-E-B) first for equality
3. Adaptively choosing F-A-S or A-F-S order based on current S+A vs F balance

Intended usage:
    from src.backend.services.app_context import ranking_service
    
    # Refresh rankings (call this when leaderboard cache is refreshed)
    ranking_service.refresh_rankings()
    
    # Get rank for a player-race combination
    rank = ranking_service.get_rank(discord_uid, race)
"""

import asyncio
from threading import Lock
from typing import Dict, List, Optional, Tuple
from src.backend.services.data_access_service import DataAccessService


class RankingService:
    """Service for managing MMR-based rankings with fixed allocation distribution."""

    # Rank distribution percentages
    RANK_PERCENTAGES = {
        "s_rank": 0.01,    # 1%
        "a_rank": 0.07,    # 7%
        "b_rank": 0.21,    # 21%
        "c_rank": 0.21,    # 21%
        "d_rank": 0.21,    # 21%
        "e_rank": 0.21,    # 21%
        "f_rank": 0.08,    # 8%
    }
    
    # Distribution order for extras (D-C-E-B-A-F-S)
    DISTRIBUTION_ORDER = ["d_rank", "c_rank", "e_rank", "b_rank", "a_rank", "f_rank", "s_rank"]

    def __init__(self, data_service: Optional[DataAccessService] = None) -> None:
        """
        Initialize the ranking service.
        
        Args:
            data_service: Optional DataAccessService instance for dependency injection.
                         If None, will be obtained via get_instance() when needed.
        """
        self.data_service = data_service
        self._rankings: Dict[Tuple[int, str], str] = {}
        self._total_entries: int = 0
        self._refresh_lock = Lock()
        # _background_task removed - DataAccessService handles this now
    
    async def _ensure_data_service(self) -> DataAccessService:
        """Ensure data_service is initialized, lazily obtaining it if needed."""
        if self.data_service is None:
            self.data_service = await DataAccessService.get_instance()
        return self.data_service

    def refresh_rankings(self) -> None:
        """
        Refresh rankings by loading all MMR data and calculating fixed allocation ranks.
        
        This method is synchronous and blocking. It should be called from an executor.
        """
        with self._refresh_lock:
            print("[Ranking Service] Starting ranking refresh...")
            
            all_mmr_data = self._load_all_mmr_data()
            
            print(f"[Ranking Service] Loaded {len(all_mmr_data)} MMR entries from database")
            
            # Use a temporary dict to build new rankings
            new_rankings = {}
            total_entries = len(all_mmr_data)
            
            if total_entries == 0:
                print("[Ranking Service] No MMR data found - all players will be unranked")
            else:
                # Calculate fixed allocation for each rank
                rank_allocations = self._calculate_fixed_allocations(total_entries)
                
                # Assign ranks based on position in sorted list
                rank_counts = {}
                current_position = 0
                
                for rank_name, allocation_size in rank_allocations.items():
                    for i in range(allocation_size):
                        if current_position < len(all_mmr_data):
                            entry = all_mmr_data[current_position]
                            discord_uid = entry.get("discord_uid")
                            race = entry.get("race")
                            
                            if discord_uid is not None and race is not None:
                                new_rankings[(discord_uid, race)] = rank_name
                                rank_counts[rank_name] = rank_counts.get(rank_name, 0) + 1
                            
                            current_position += 1
            
            # Atomically update the instance variables
            self._rankings = new_rankings
            self._total_entries = total_entries
            
            print(f"[Ranking Service] Refreshed rankings for {len(self._rankings)} player-race combinations")
            if 'rank_counts' in locals():
                print(f"[Ranking Service] Rank distribution: {rank_counts}")

    async def trigger_refresh(self) -> None:
        """
        Trigger an asynchronous refresh of the rankings in an executor.
        This is the preferred way to refresh from an async context.
        """
        await self._ensure_data_service()
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.refresh_rankings)

    # start_background_refresh() and stop_background_refresh() removed - DataAccessService handles this now

    def get_rank(self, discord_uid: int, race: str) -> str:
        """
        Get the rank for a specific player-race combination.
        
        Args:
            discord_uid: Discord user ID of the player.
            race: Race code (e.g., 'sc2_terran', 'bw_zerg').
        
        Returns:
            Rank code (e.g., 's_rank', 'a_rank', 'u_rank' for unranked).
        """
        return self._rankings.get((discord_uid, race), "u_rank")

    def _load_all_mmr_data(self) -> List[Dict]:
        """
        Load all MMR data from DataAccessService (in-memory), sorted by MMR DESC, last_played DESC, id DESC.
        
        In case of MMR ties, more recently active players get higher ranks.
        
        Returns:
            List of dictionaries containing discord_uid, race, mmr, last_played, and id.
        """
        try:
            # Get MMR data from DataAccessService (in-memory, instant)
            mmr_df = self.data_service.get_leaderboard_dataframe()
            
            # Convert to list of dicts, already sorted by MMR DESC, last_played DESC, id DESC
            return mmr_df.to_dicts()
            
        except Exception as e:
            print(f"[Ranking Service] Error loading MMR data: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _calculate_fixed_allocations(self, total_players: int) -> Dict[str, int]:
        """
        Calculate fixed allocations for each rank using adaptive distribution method.
        
        This method:
        1. Rounds down ideal allocations
        2. Distributes middle ranks (D-C-E-B) first
        3. Checks S+A vs F balance
        4. Adaptively chooses F-A-S or A-F-S order based on current balance
        
        Args:
            total_players: Total number of players to distribute.
        
        Returns:
            Dictionary mapping rank names to their allocation sizes.
        """
        if total_players == 0:
            return {rank: 0 for rank in self.RANK_PERCENTAGES.keys()}
        
        # Calculate ideal allocations (floats)
        ideal_allocations = {}
        for rank, percentage in self.RANK_PERCENTAGES.items():
            ideal_allocations[rank] = total_players * percentage
        
        # Round down to get initial allocations
        allocations = {}
        for rank, ideal in ideal_allocations.items():
            allocations[rank] = int(ideal)
        
        # Calculate remaining players to distribute
        allocated_so_far = sum(allocations.values())
        remaining_players = total_players - allocated_so_far
        
        # First, distribute to middle ranks (D-C-E-B) to ensure equality
        middle_ranks = ["d_rank", "c_rank", "e_rank", "b_rank"]
        for rank in middle_ranks:
            if remaining_players <= 0:
                break
            allocations[rank] += 1
            remaining_players -= 1
        
        # Now check S+A vs F balance and choose adaptive order
        s_a_total = allocations.get("s_rank", 0) + allocations.get("a_rank", 0)
        f_total = allocations.get("f_rank", 0)
        
        if f_total > s_a_total:
            # F is bigger, give to A first: A-F-S
            adaptive_order = ["a_rank", "f_rank", "s_rank"]
        else:
            # F <= S+A, give to F first: F-A-S
            adaptive_order = ["f_rank", "a_rank", "s_rank"]
        
        # Distribute remaining extras using adaptive order
        for rank in adaptive_order:
            if remaining_players <= 0:
                break
            allocations[rank] += 1
            remaining_players -= 1
        
        return allocations

    def get_total_ranked_entries(self) -> int:
        """
        Get the total number of ranked player-race combinations.
        
        Returns:
            Total count of ranked entries.
        """
        return self._total_entries

    def clear_rankings(self) -> None:
        """Clear all rankings from memory."""
        self._rankings.clear()
        self._total_entries = 0
        print("[Ranking Service] Rankings cleared")

