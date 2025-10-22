"""
Ranking service for MMR-based player rankings.

This module defines the RankingService class, which manages MMR-based rankings
for all player-race combinations. Rankings are calculated based on percentile
distribution and kept in memory for fast access.

Distribution:
- S-Rank: top 1%
- A-Rank: next 7%
- B-Rank: next 21%
- C-Rank: next 21%
- D-Rank: next 21%
- E-Rank: next 21%
- F-Rank: bottom 8%
- U-Rank: unranked (no games played or insufficient data)

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
    """Service for managing MMR-based rankings with percentile distribution."""

    # Rank distribution percentiles (cumulative from top)
    RANK_THRESHOLDS = [
        ("s_rank", 1.0),    # Top 1%
        ("a_rank", 8.0),    # Top 1-8% (next 7%)
        ("b_rank", 29.0),   # Top 8-29% (next 21%)
        ("c_rank", 50.0),   # Top 29-50% (next 21%)
        ("d_rank", 71.0),   # Top 50-71% (next 21%)
        ("e_rank", 92.0),   # Top 71-92% (next 21%)
        ("f_rank", 100.0),  # Top 92-100% (next 8%)
    ]

    def __init__(self, data_service: Optional[DataAccessService] = None) -> None:
        """
        Initialize the ranking service.
        
        Args:
            data_service: Optional DataAccessService instance for dependency injection.
        """
        self.data_service = data_service or DataAccessService()
        self._rankings: Dict[Tuple[int, str], str] = {}
        self._total_entries: int = 0
        self._refresh_lock = Lock()
        # _background_task removed - DataAccessService handles this now

    def refresh_rankings(self) -> None:
        """
        Refresh rankings by loading all MMR data and calculating percentile ranks.
        
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
                rank_counts = {}
                for index, entry in enumerate(all_mmr_data):
                    discord_uid = entry.get("discord_uid")
                    race = entry.get("race")
                    
                    if discord_uid is None or race is None:
                        continue
                    
                    percentile = (index / total_entries) * 100
                    rank = self._get_rank_from_percentile(percentile)
                    
                    new_rankings[(discord_uid, race)] = rank
                    rank_counts[rank] = rank_counts.get(rank, 0) + 1
            
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

    def _get_rank_from_percentile(self, percentile: float) -> str:
        """
        Determine rank based on percentile.
        
        Args:
            percentile: Percentile value (0-100, where 0 is best).
        
        Returns:
            Rank code (e.g., 's_rank', 'a_rank', etc.).
        """
        for rank_name, threshold in self.RANK_THRESHOLDS:
            if percentile < threshold:
                return rank_name
        
        # Default to unranked if something goes wrong
        return "u_rank"

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

