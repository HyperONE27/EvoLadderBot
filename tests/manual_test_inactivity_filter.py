"""
Manual test script to demonstrate the inactivity filter in action.
This creates a realistic scenario with various player activity states.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
import polars as pl

from src.backend.services.ranking_service import RankingService
from src.backend.services.data_access_service import DataAccessService


def main():
    print("=" * 80)
    print("INACTIVITY FILTER DEMONSTRATION")
    print("=" * 80)
    print()
    
    # Setup mock data service
    mock_data_service = Mock(spec=DataAccessService)
    
    now = datetime.now(timezone.utc)
    
    # Create diverse test data
    players = [
        # Active players (will be ranked)
        {"id": 1, "name": "AlphaWarrior", "race": "sc2_terran", "mmr": 2400, "games": 150, 
         "last_played": (now - timedelta(hours=6)).isoformat(), "activity": "6 hours ago"},
        {"id": 2, "name": "BetaCommander", "race": "sc2_zerg", "mmr": 2300, "games": 120,
         "last_played": (now - timedelta(days=3)).isoformat(), "activity": "3 days ago"},
        {"id": 3, "name": "GammaStrategist", "race": "sc2_protoss", "mmr": 2200, "games": 100,
         "last_played": (now - timedelta(days=7)).isoformat(), "activity": "7 days ago"},
        {"id": 4, "name": "DeltaElite", "race": "bw_terran", "mmr": 2100, "games": 90,
         "last_played": (now - timedelta(days=10)).isoformat(), "activity": "10 days ago"},
        {"id": 5, "name": "EpsilonMaster", "race": "bw_zerg", "mmr": 2000, "games": 80,
         "last_played": (now - timedelta(days=13)).isoformat(), "activity": "13 days ago"},
        
        # Inactive players (will be unranked)
        {"id": 6, "name": "ZetaVeteran", "race": "bw_protoss", "mmr": 1900, "games": 200,
         "last_played": (now - timedelta(days=15)).isoformat(), "activity": "15 days ago"},
        {"id": 7, "name": "EtaLegend", "race": "sc2_terran", "mmr": 1800, "games": 180,
         "last_played": (now - timedelta(days=21)).isoformat(), "activity": "21 days ago"},
        {"id": 8, "name": "ThetaPro", "race": "sc2_zerg", "mmr": 1700, "games": 160,
         "last_played": (now - timedelta(days=30)).isoformat(), "activity": "30 days ago"},
        {"id": 9, "name": "IotaChampion", "race": "sc2_protoss", "mmr": 1600, "games": 140,
         "last_played": (now - timedelta(days=60)).isoformat(), "activity": "60 days ago"},
        
        # Edge cases
        {"id": 10, "name": "KappaNewbie", "race": "bw_terran", "mmr": 1000, "games": 0,
         "last_played": None, "activity": "Never played"},
        {"id": 11, "name": "LambdaGhost", "race": "bw_zerg", "mmr": 1500, "games": 50,
         "last_played": None, "activity": "No timestamp (data issue)"},
    ]
    
    # Convert to DataFrame format
    mock_mmr_data = []
    for p in players:
        mock_mmr_data.append({
            "discord_uid": p["id"],
            "race": p["race"],
            "mmr": p["mmr"],
            "games_played": p["games"],
            "last_played": p["last_played"],
            "games_won": p["games"] // 2,
            "games_lost": p["games"] // 2,
            "games_drawn": 0,
            "player_name": p["name"]
        })
    
    mock_df = pl.DataFrame(mock_mmr_data)
    mock_data_service.get_leaderboard_dataframe.return_value = mock_df
    
    # Create and refresh rankings
    print("Creating ranking service and calculating ranks...")
    print()
    ranking_service = RankingService(data_service=mock_data_service)
    ranking_service.refresh_rankings()
    
    print()
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print()
    
    # Display results in a nice table
    print(f"{'Player':<20} {'Race':<15} {'MMR':<6} {'Games':<7} {'Activity':<25} {'Rank':<10} {'Global':<8}")
    print("-" * 100)
    
    for p in players:
        rank_info = ranking_service.get_rank(p["id"], p["race"])
        rank_display = rank_info["letter_rank"].replace("_rank", "").upper()
        global_rank = rank_info["global_rank"]
        global_display = str(global_rank) if global_rank > 0 else "N/A"
        
        # Color coding (text only, no ANSI codes for Windows compatibility)
        status = "✓ RANKED" if rank_info["letter_rank"] != "u_rank" else "✗ UNRANKED"
        
        print(f"{p['name']:<20} {p['race']:<15} {p['mmr']:<6} {p['games']:<7} {p['activity']:<25} "
              f"{rank_display:<10} {global_display:<8}")
    
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print()
    
    total_ranked = ranking_service.get_total_ranked_entries()
    total_unranked = len(players) - total_ranked
    
    print(f"Total Players: {len(players)}")
    print(f"Ranked Players (active within 2 weeks): {total_ranked}")
    print(f"Unranked Players (inactive or new): {total_unranked}")
    print()
    print("Inactivity Threshold: 2 weeks (14 days)")
    print()
    
    print("Key Observations:")
    print("  • Players who played within the last 13 days are RANKED")
    print("  • Players who haven't played in 15+ days are UNRANKED")
    print("  • Players with 0 games or missing timestamps are UNRANKED")
    print("  • The 2-week threshold successfully filters out inactive players")
    print()
    print("=" * 80)


if __name__ == "__main__":
    main()

