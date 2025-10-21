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

from typing import Dict, List, Optional, Tuple
from src.backend.db.db_reader_writer import DatabaseReader


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

    def __init__(self, db_reader: Optional[DatabaseReader] = None) -> None:
        """
        Initialize the ranking service.
        
        Args:
            db_reader: Optional DatabaseReader instance for dependency injection.
        """
        self.db_reader = db_reader or DatabaseReader()
        # In-memory storage: (discord_uid, race) -> rank
        self._rankings: Dict[Tuple[int, str], str] = {}
        # Total count of ranked entries
        self._total_entries: int = 0

    def refresh_rankings(self) -> None:
        """
        Refresh rankings by loading all MMR data and calculating percentile ranks.
        
        This method should be called whenever the leaderboard cache is refreshed.
        It loads the entire mmrs_1v1 table, sorts by MMR, and assigns ranks based
        on percentile distribution.
        """
        print("[Ranking Service] Starting ranking refresh...")
        
        # Load all player-race combinations sorted by MMR DESC, id DESC
        all_mmr_data = self._load_all_mmr_data()
        
        print(f"[Ranking Service] Loaded {len(all_mmr_data)} MMR entries from database")
        
        # Clear existing rankings
        self._rankings.clear()
        
        # Calculate total entries
        self._total_entries = len(all_mmr_data)
        
        if self._total_entries == 0:
            print("[Ranking Service] No MMR data found - all players will be unranked")
            return
        
        # Assign ranks based on percentile distribution
        rank_counts = {}
        for index, entry in enumerate(all_mmr_data):
            discord_uid = entry.get("discord_uid")
            race = entry.get("race")
            
            if discord_uid is None or race is None:
                print(f"[Ranking Service] Warning: Entry {index} has None discord_uid or race: {entry}")
                continue
            
            # Calculate percentile (0 = best, 100 = worst)
            percentile = (index / self._total_entries) * 100
            
            # Determine rank based on percentile
            rank = self._get_rank_from_percentile(percentile)
            
            # Store in memory
            self._rankings[(discord_uid, race)] = rank
            
            # Count ranks for debugging
            rank_counts[rank] = rank_counts.get(rank, 0) + 1
        
        print(f"[Ranking Service] Refreshed rankings for {len(self._rankings)} player-race combinations")
        print(f"[Ranking Service] Rank distribution: {rank_counts}")

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
        Load all MMR data from the database, sorted by MMR DESC, last_played DESC, id DESC.
        
        In case of MMR ties, more recently active players get higher ranks.
        
        Returns:
            List of dictionaries containing discord_uid, race, mmr, last_played, and id.
        """
        try:
            # Query to get all player-race combinations sorted by MMR, then last_played
            # This matches the index: idx_mmrs_mmr_lastplayed_id_desc
            query = """
                SELECT discord_uid, race, mmr, last_played, id
                FROM mmrs_1v1
                ORDER BY mmr DESC, last_played DESC, id DESC
            """
            
            results = self.db_reader.adapter.execute_query(query, {})
            
            # Convert to list of dicts if results are tuples
            all_data = []
            for row in results:
                # Check if row is already a dict or a tuple/list
                if isinstance(row, dict):
                    all_data.append({
                        "discord_uid": row.get("discord_uid"),
                        "race": row.get("race"),
                        "mmr": row.get("mmr"),
                        "last_played": row.get("last_played"),
                        "id": row.get("id")
                    })
                else:
                    # Assume it's a tuple/list with (discord_uid, race, mmr, last_played, id)
                    all_data.append({
                        "discord_uid": row[0],
                        "race": row[1],
                        "mmr": row[2],
                        "last_played": row[3],
                        "id": row[4]
                    })
            
            return all_data
            
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

