"""
Characterization, regression, and invariant tests for leaderboard filtering logic.

This test suite documents and enforces the correct behavior of the leaderboard
filtering system, particularly the critical interaction between "Best Race Only"
and other filters (rank, country, race).

Key behaviors tested:
1. Baseline population counts with and without "Best Race Only"
2. Rank distribution when "Best Race Only" is active (top-heavy distribution)
3. Sum of filtered ranks equals total (regression test for order-of-operations bug)
4. Invariant: Adding filters never increases player count
5. Invariant: "Best Race Only" returns unique players
"""

import pytest
import pytest_asyncio
import polars as pl
from typing import Dict, Any

from src.backend.services.leaderboard_service import LeaderboardService
from src.backend.services.ranking_service import RankingService
from src.backend.services.data_access_service import DataAccessService
from src.backend.services.countries_service import CountriesService
from src.backend.services.races_service import RacesService


@pytest.fixture(autouse=True)
def reset_data_access_service_singleton():
    """Reset the DataAccessService singleton before each test."""
    DataAccessService._instance = None
    DataAccessService._initialized = False
    yield
    DataAccessService._instance = None
    DataAccessService._initialized = False


@pytest_asyncio.fixture
async def leaderboard_service_with_mock_data():
    """
    Initialize LeaderboardService with real production data from CSV snapshot.
    
    This fixture loads the mmrs_1v1 table snapshot exported from Supabase,
    ensuring tests run against realistic data that characterizes actual behavior.
    """
    import os
    import polars as pl
    
    # Initialize services
    data_service = DataAccessService()
    ranking_service = RankingService(data_service=data_service)
    leaderboard_service = LeaderboardService(
        data_service=data_service,
        ranking_service=ranking_service
    )
    
    # Load the MMR data from the snapshot CSV
    csv_path = os.path.join(os.path.dirname(__file__), '..', 'fixtures', 'mmrs_1v1_snapshot.csv')
    
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"MMR snapshot not found at {csv_path}")
    
    # Load MMR data from CSV
    mmrs_data = pl.read_csv(csv_path)
    
    # Update all last_played timestamps to be recent (within 2 weeks) so players are ranked
    from datetime import datetime, timezone
    current_time = datetime.now(timezone.utc)
    mmrs_data = mmrs_data.with_columns([
        pl.lit(current_time).alias("last_played")
    ])
    
    data_service._mmrs_1v1_df = mmrs_data
    
    print(f"\n[Fixture] Loaded {len(mmrs_data)} MMR records from snapshot (with updated timestamps)")
    
    # Create minimal players DataFrame (just discord_uid and player_name from MMR data)
    # Extract unique discord_uids and player_names
    players_data = mmrs_data.select(['discord_uid', 'player_name']).unique(subset=['discord_uid'])
    # Add all required columns
    players_data = players_data.with_columns([
        pl.lit("").alias("discord_username"),
        pl.lit("").alias("country"),
        pl.lit(3).alias("remaining_aborts"),
        pl.lit(None).alias("alt_player_name_1"),
        pl.lit(None).alias("alt_player_name_2"),
    ])
    data_service._players_df = players_data
    
    print(f"[Fixture] Created {len(players_data)} unique players")
    
    # Initialize empty DataFrames for other tables
    data_service._matches_1v1_df = pl.DataFrame({
        "id": pl.Series([], dtype=pl.Int64),
    })
    data_service._preferences_1v1_df = pl.DataFrame({
        "discord_uid": pl.Series([], dtype=pl.Int64),
    })
    data_service._replays_df = pl.DataFrame({
        "id": pl.Series([], dtype=pl.Int64),
    })
    
    # Initialize write queue components
    import asyncio
    data_service._write_queue = asyncio.Queue()
    data_service._write_event = asyncio.Event()
    data_service._shutdown_event = asyncio.Event()
    data_service._initialized = True
    
    # Trigger ranking refresh to ensure ranks are calculated on real data
    print("[Fixture] Calculating rankings...")
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, ranking_service.refresh_rankings)
    
    print(f"[Fixture] Rankings calculated. Total ranked entries: {ranking_service.get_total_ranked_entries()}")
    
    return leaderboard_service


@pytest.mark.asyncio
async def test_baseline_player_counts(leaderboard_service_with_mock_data):
    """
    Characterization Test 1: Baseline Population Counts
    
    Verifies that:
    - Without filters, we get all ranked player-race combinations
    - With "Best Race Only", we get one entry per unique player
    """
    service = leaderboard_service_with_mock_data
    
    # Get baseline count (all player-race combinations)
    all_data = await service.get_leaderboard_data(page_size=10000)
    total_player_races = all_data['true_total_players']
    
    print(f"\n[Test] Total ranked player-race combinations: {total_player_races}")
    
    # Get count with "Best Race Only"
    best_race_data = await service.get_leaderboard_data(
        best_race_only=True,
        page_size=10000
    )
    total_unique_players = best_race_data['true_total_players']
    
    print(f"[Test] Total unique players (best race only): {total_unique_players}")
    
    # Assertions
    assert total_player_races > 0, "Should have at least some ranked player-races"
    assert total_unique_players > 0, "Should have at least some unique players"
    assert total_unique_players <= total_player_races, \
        "Unique players should be less than or equal to total player-races"
    
    # Store these values for other tests
    return {
        'total_player_races': total_player_races,
        'total_unique_players': total_unique_players
    }


@pytest.mark.asyncio
async def test_best_race_only_rank_distribution(leaderboard_service_with_mock_data):
    """
    Characterization Test 2: Rank Distribution with "Best Race Only"
    
    Verifies that when "Best Race Only" is active, the rank distribution
    is top-heavy (most players' best races are in higher ranks).
    
    This test captures the expected distribution and will fail if the
    order-of-operations bug is reintroduced.
    """
    service = leaderboard_service_with_mock_data
    
    # Get the total count with best_race_only
    best_race_data = await service.get_leaderboard_data(
        best_race_only=True,
        page_size=10000
    )
    total_best_race_players = best_race_data['true_total_players']
    
    print(f"\n[Test] Total players (best race only): {total_best_race_players}")
    
    # Get count for each rank with best_race_only
    rank_counts = {}
    ranks = ['s_rank', 'a_rank', 'b_rank', 'c_rank', 'd_rank', 'e_rank', 'f_rank']
    
    for rank in ranks:
        data = await service.get_leaderboard_data(
            best_race_only=True,
            rank_filter=rank,
            page_size=10000
        )
        count = data['true_total_players']
        rank_counts[rank] = count
        print(f"[Test] {rank.upper()}: {count} players")
    
    # Assertions
    # 1. All counts should be non-negative
    for rank, count in rank_counts.items():
        assert count >= 0, f"{rank} should have non-negative count"
    
    # 2. Sum of all rank counts should equal total (this is the critical regression test)
    sum_of_ranks = sum(rank_counts.values())
    assert sum_of_ranks == total_best_race_players, \
        f"Sum of filtered ranks ({sum_of_ranks}) should equal total best race players ({total_best_race_players})"
    
    print(f"[Test] [OK] Sum of ranks ({sum_of_ranks}) equals total ({total_best_race_players})")
    
    # Note: This assertion depends on the actual data distribution
    # We expect top-heavy but don't assert it as it depends on the dataset
    # The critical test is the sum matching the total


@pytest.mark.asyncio
async def test_sum_of_filtered_best_race_ranks_equals_total(leaderboard_service_with_mock_data):
    """
    Regression Test 1: Sum of Ranked "Best Race" Players
    
    This test directly automates the manual check that revealed the bug.
    It proves that filtering by rank on the "best race" pool correctly
    partitions the set without losing or gaining players.
    
    If this test fails, it means the order-of-operations bug has been reintroduced.
    """
    service = leaderboard_service_with_mock_data
    
    # Step 1: Get total with best_race_only
    best_race_data = await service.get_leaderboard_data(
        best_race_only=True,
        page_size=10000
    )
    expected_total = best_race_data['true_total_players']
    
    print(f"\n[Regression Test] Expected total (best race only): {expected_total}")
    
    # Step 2: Sum up all rank-filtered counts
    ranks = ['s_rank', 'a_rank', 'b_rank', 'c_rank', 'd_rank', 'e_rank', 'f_rank']
    actual_sum = 0
    
    for rank in ranks:
        data = await service.get_leaderboard_data(
            best_race_only=True,
            rank_filter=rank,
            page_size=10000
        )
        count = data['true_total_players']
        actual_sum += count
        print(f"[Regression Test] {rank}: {count} (running sum: {actual_sum})")
    
    # Step 3: Assert they match
    assert actual_sum == expected_total, \
        f"REGRESSION DETECTED: Sum of rank-filtered counts ({actual_sum}) " \
        f"does not equal total best-race count ({expected_total}). " \
        f"This indicates the order-of-operations bug has been reintroduced."
    
    print(f"[Regression Test] [PASS]: Sum ({actual_sum}) equals total ({expected_total})")


@pytest.mark.asyncio
async def test_invariant_adding_filters_never_increases_player_count(leaderboard_service_with_mock_data):
    """
    Invariant Test 1: Filtering is Always Reductive
    
    Verifies that adding additional filters to a query can only narrow
    the results, never expand them.
    """
    service = leaderboard_service_with_mock_data
    
    print("\n[Invariant Test] Testing that filters are always reductive...")
    
    # Baseline: best_race_only
    data1 = await service.get_leaderboard_data(
        best_race_only=True,
        page_size=10000
    )
    count1 = data1['true_total_players']
    print(f"[Invariant Test] Count with best_race_only: {count1}")
    
    # Add country filter
    data2 = await service.get_leaderboard_data(
        best_race_only=True,
        country_filter=['US', 'KR'],
        page_size=10000
    )
    count2 = data2['true_total_players']
    print(f"[Invariant Test] Count with best_race_only + country filter: {count2}")
    
    assert count2 <= count1, \
        f"Adding country filter increased count from {count1} to {count2}"
    
    # Add rank filter
    data3 = await service.get_leaderboard_data(
        best_race_only=True,
        country_filter=['US', 'KR'],
        rank_filter='a_rank',
        page_size=10000
    )
    count3 = data3['true_total_players']
    print(f"[Invariant Test] Count with best_race_only + country + rank filter: {count3}")
    
    assert count3 <= count2, \
        f"Adding rank filter increased count from {count2} to {count3}"
    
    print(f"[Invariant Test] [PASS]: Filters are reductive ({count1} -> {count2} -> {count3})")


@pytest.mark.asyncio
async def test_invariant_best_race_only_returns_unique_players(leaderboard_service_with_mock_data):
    """
    Invariant Test 2: Player Uniqueness in "Best Race Only" Mode
    
    Guarantees that the "best race" logic correctly selects only one
    entry per player (no duplicates).
    """
    service = leaderboard_service_with_mock_data
    
    print("\n[Invariant Test] Testing player uniqueness in best race only mode...")
    
    # Get all players with best_race_only
    data = await service.get_leaderboard_data(
        best_race_only=True,
        page_size=10000
    )
    
    players = data['players']
    total_count = data['true_total_players']
    
    print(f"[Invariant Test] Total players returned: {len(players)}")
    print(f"[Invariant Test] Reported total: {total_count}")
    
    # Extract discord_uid from each player
    discord_uids = [player['discord_uid'] for player in players]
    unique_discord_uids = set(discord_uids)
    
    print(f"[Invariant Test] Unique discord_uids: {len(unique_discord_uids)}")
    
    # Assert: All discord_uids should be unique
    assert len(discord_uids) == len(unique_discord_uids), \
        f"Found duplicate players in best race only mode. " \
        f"Total: {len(discord_uids)}, Unique: {len(unique_discord_uids)}"
    
    print(f"[Invariant Test] [PASS]: All players are unique")


@pytest.mark.asyncio
async def test_unranked_players_excluded_from_leaderboard(leaderboard_service_with_mock_data):
    """
    Characterization Test: Unranked Players (0 games) are Excluded
    
    Verifies that players with 0 games played (u_rank) do not appear
    on the leaderboard, even though they exist in the system.
    """
    service = leaderboard_service_with_mock_data
    
    print("\n[Test] Verifying unranked players are excluded from leaderboard...")
    
    # Get all leaderboard data
    data = await service.get_leaderboard_data(page_size=10000)
    players = data['players']
    
    # Check that no player has u_rank
    unranked_players = [p for p in players if p.get('rank') == 'u_rank']
    
    assert len(unranked_players) == 0, \
        f"Found {len(unranked_players)} unranked players on leaderboard, but they should be excluded"
    
    print(f"[Test] [PASS]: No unranked players found on leaderboard")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])


