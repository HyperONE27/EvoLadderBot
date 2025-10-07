"""
Matchmaking service implementing the advanced MMR-based matching algorithm.

This module defines the MatchmakerService class, which contains methods for:
- Creating the matchmaking queue with MMR tracking
- Adding and removing players to and from the queue
- Implementing BW vs SC2 only matching
- Elastic MMR window based on wait time and queue size
- Database integration for match creation and result recording
"""

import asyncio
import random
import time
from typing import List, Optional, Dict, Any, Callable, Tuple
from dataclasses import dataclass
from src.backend.db.db_reader_writer import DatabaseReader, DatabaseWriter

@dataclass
class QueuePreferences:
    """Player's queue preferences"""
    selected_races: List[str]
    vetoed_maps: List[str]
    discord_user_id: int
    user_id: str  # The player's "gamer name"

@dataclass
class MatchResult:
    """Result of a successful match"""
    match_id: int
    player1_discord_id: int
    player2_discord_id: int
    player1_user_id: str
    player2_user_id: str
    player1_race: str
    player2_race: str
    map_choice: str
    server_choice: str
    in_game_channel: str

class Player:
    def __init__(self, discord_user_id: int, user_id: str, preferences: QueuePreferences, 
                 bw_mmr: Optional[int] = None, sc2_mmr: Optional[int] = None):
        self.discord_user_id = discord_user_id
        self.user_id = user_id
        self.preferences = preferences
        self.bw_mmr = bw_mmr
        self.sc2_mmr = sc2_mmr
        self.queue_start_time = time.time()
        self.wait_cycles = 0
        
        # Determine which races they have
        self.has_bw_race = any(race.startswith("bw_") for race in preferences.selected_races)
        self.has_sc2_race = any(race.startswith("sc2_") for race in preferences.selected_races)
        
        # Get the specific race codes
        self.bw_race = next((race for race in preferences.selected_races if race.startswith("bw_")), None)
        self.sc2_race = next((race for race in preferences.selected_races if race.startswith("sc2_")), None)

    def get_effective_mmr(self, is_bw_match: bool) -> Optional[int]:
        """Get the MMR for the appropriate race (BW or SC2)"""
        if is_bw_match:
            return self.bw_mmr
        else:
            return self.sc2_mmr

    def get_race_for_match(self, is_bw_match: bool) -> Optional[str]:
        """Get the race code for the appropriate match type"""
        if is_bw_match:
            return self.bw_race
        else:
            return self.sc2_race

    def __repr__(self):
        return f"Player({self.user_id}, discord_id={self.discord_user_id}, bw_mmr={self.bw_mmr}, sc2_mmr={self.sc2_mmr})"


class Matchmaker:
    def __init__(self, players: Optional[List[Player]] = None):
        self.players: List[Player] = players or []
        self.running = False
        self.match_callback: Optional[Callable[[MatchResult], None]] = None
        self.db_reader = DatabaseReader()
        self.db_writer = DatabaseWriter()

    def add_player(self, player: Player) -> None:
        """Add a player to the matchmaking pool with MMR lookup."""
        # Look up MMR for each selected race
        for race in player.preferences.selected_races:
            mmr_data = self.db_reader.get_player_mmr_1v1(player.discord_user_id, race)
            if mmr_data:
                mmr_value = mmr_data['mmr']
                if race.startswith("bw_"):
                    player.bw_mmr = mmr_value
                elif race.startswith("sc2_"):
                    player.sc2_mmr = mmr_value
            else:
                # Create default MMR entry if none exists
                from src.backend.services.mmr_service import MMRService
                mmr_service = MMRService()
                default_mmr = mmr_service.default_mmr()
                self.db_writer.create_or_update_mmr_1v1(
                    player.discord_user_id, 
                    player.user_id, 
                    race, 
                    default_mmr
                )
                if race.startswith("bw_"):
                    player.bw_mmr = default_mmr
                elif race.startswith("sc2_"):
                    player.sc2_mmr = default_mmr

        print(f"👤 {player.user_id} (Discord ID: {player.discord_user_id}) joined the queue")
        print(f"   Selected races: {player.preferences.selected_races}")
        print(f"   BW MMR: {player.bw_mmr}, SC2 MMR: {player.sc2_mmr}")
        print(f"   Vetoed maps: {player.preferences.vetoed_maps}")
        self.players.append(player)
        print(f"   Total players in queue: {len(self.players)}")

    def remove_player(self, discord_user_id: int) -> None:
        """Remove a player from the matchmaking pool by Discord ID."""
        before_count = len(self.players)
        self.players = [p for p in self.players if p.discord_user_id != discord_user_id]
        after_count = len(self.players)
        print(f"🚪 Player with Discord ID {discord_user_id} left the queue")
        print(f"   Players before removal: {before_count}, after: {after_count}")

    def set_match_callback(self, callback: Callable[[MatchResult], None]) -> None:
        """Set the callback function to be called when a match is found."""
        self.match_callback = callback

    def max_diff(self, wait_cycles: int, queue_size: int) -> int:
        """
        Calculate maximum acceptable MMR difference based on wait time and queue size.
        
        Args:
            wait_cycles: Number of matching cycles the player has waited
            queue_size: Total number of players in queue
            
        Returns:
            Maximum MMR difference allowed
        """
        if queue_size < 6:
            base, growth = 125, 75
        elif queue_size < 12:
            base, growth = 100, 50
        else:
            base, growth = 75, 25
        step = 6  # number of queue attempts, not number of seconds
        return base + (wait_cycles // step) * growth

    def categorize_players(self) -> Tuple[List[Player], List[Player], List[Player]]:
        """
        Categorize players into BW-only, SC2-only, and both lists.
        
        Returns:
            Tuple of (bw_only, sc2_only, both_races) lists, sorted by MMR
        """
        bw_only = []
        sc2_only = []
        both_races = []
        
        for player in self.players:
            if player.has_bw_race and not player.has_sc2_race:
                bw_only.append(player)
            elif player.has_sc2_race and not player.has_bw_race:
                sc2_only.append(player)
            elif player.has_bw_race and player.has_sc2_race:
                both_races.append(player)
        
        # Sort by MMR (highest first)
        bw_only.sort(key=lambda p: p.bw_mmr or 0, reverse=True)
        sc2_only.sort(key=lambda p: p.sc2_mmr or 0, reverse=True)
        both_races.sort(key=lambda p: max(p.bw_mmr or 0, p.sc2_mmr or 0), reverse=True)
        
        return bw_only, sc2_only, both_races

    def equalize_lists(self, list_x: List[Player], list_y: List[Player], 
                      list_z: List[Player]) -> Tuple[List[Player], List[Player], List[Player]]:
        """
        Equalize the sizes of list_x and list_y by temporarily moving players from list_z.
        Returns the equalized lists AND the remaining unmatched Z players.
        
        Args:
            list_x: First list to equalize
            list_y: Second list to equalize  
            list_z: Source list to move players from
            
        Returns:
            Tuple of (equalized_x, equalized_y, remaining_z)
        """
        x_copy = list_x.copy()
        y_copy = list_y.copy()
        z_copy = list_z.copy()
        
        # Special case: if both X and Y are empty, distribute Z players evenly
        if not x_copy and not y_copy and z_copy:
            # Distribute Z players evenly between X and Y
            for i, player in enumerate(z_copy):
                if i % 2 == 0:
                    x_copy.append(player)
                else:
                    y_copy.append(player)
            z_copy = []  # All Z players have been distributed
            return x_copy, y_copy, z_copy
        
        # Normal equalization logic
        # Distribute Z players to balance X and Y lists
        while z_copy:
            if len(x_copy) < len(y_copy):
                # Move player from z to x
                if x_copy and y_copy:
                    x_mean = sum(p.bw_mmr or 0 for p in x_copy) / len(x_copy)
                    y_mean = sum(p.sc2_mmr or 0 for p in y_copy) / len(y_copy)
                    if x_mean < y_mean:
                        # Move highest-rated player from z to x
                        player = z_copy.pop(0)
                        x_copy.append(player)
                    else:
                        # Move lowest-rated player from z to x
                        player = z_copy.pop(-1)
                        x_copy.append(player)
                else:
                    player = z_copy.pop(0)
                    x_copy.append(player)
            elif len(x_copy) > len(y_copy):
                # Move player from z to y
                if x_copy and y_copy:
                    x_mean = sum(p.bw_mmr or 0 for p in x_copy) / len(x_copy)
                    y_mean = sum(p.sc2_mmr or 0 for p in y_copy) / len(y_copy)
                    if x_mean < y_mean:
                        # Move highest-rated player from z to y
                        player = z_copy.pop(0)
                        y_copy.append(player)
                    else:
                        # Move lowest-rated player from z to y
                        player = z_copy.pop(-1)
                        y_copy.append(player)
                else:
                    player = z_copy.pop(0)
                    y_copy.append(player)
            else:
                # Lists are equal, alternate between x and y
                if len(z_copy) > 0:
                    player = z_copy.pop(0)
                    x_copy.append(player)
                if len(z_copy) > 0:
                    player = z_copy.pop(0)
                    y_copy.append(player)
        
        return x_copy, y_copy, z_copy

    def find_matches(self, lead_side: List[Player], follow_side: List[Player], 
                    is_bw_match: bool) -> List[Tuple[Player, Player]]:
        """
        Find matches between lead_side and follow_side players.
        
        Args:
            lead_side: List of players to match from
            follow_side: List of players to match against
            is_bw_match: True for BW vs SC2, False for SC2 vs BW
            
        Returns:
            List of matched player pairs
        """
        matches = []
        used_lead = set()
        used_follow = set()
        
        # Calculate mean MMR of lead side
        if not lead_side:
            return matches
            
        lead_mean = sum(p.get_effective_mmr(is_bw_match) or 0 for p in lead_side) / len(lead_side)
        
        # Calculate priority for each lead side player and sort once
        lead_side_with_priority = []
        for player in lead_side:
            mmr = player.get_effective_mmr(is_bw_match) or 0
            distance_from_mean = abs(mmr - lead_mean)
            priority = distance_from_mean + (10 * player.wait_cycles)
            lead_side_with_priority.append((priority, player))
        
        # Sort by priority (highest first) - do this once outside the loop
        lead_side_with_priority.sort(key=lambda x: x[0], reverse=True)
        sorted_lead_side = [player for _, player in lead_side_with_priority]
        
        # Try to match each lead side player
        for lead_player in sorted_lead_side:
            if lead_player.discord_user_id in used_lead:
                continue
                
            lead_mmr = lead_player.get_effective_mmr(is_bw_match) or 0
            max_diff = self.max_diff(lead_player.wait_cycles, len(self.players))
            
            # Find best match in follow side
            best_match = None
            best_diff = float('inf')
            
            for follow_player in follow_side:
                if follow_player.discord_user_id in used_follow:
                    continue
                    
                follow_mmr = follow_player.get_effective_mmr(not is_bw_match) or 0
                mmr_diff = abs(lead_mmr - follow_mmr)
                
                if mmr_diff <= max_diff and mmr_diff < best_diff:
                    best_match = follow_player
                    best_diff = mmr_diff
            
            if best_match:
                matches.append((lead_player, best_match))
                used_lead.add(lead_player.discord_user_id)
                used_follow.add(best_match.discord_user_id)
        
        return matches

    def get_available_maps(self, p1: Player, p2: Player) -> List[str]:
        """Get maps that haven't been vetoed by either player."""
        all_maps = ["Arkanoid", "Death Valley", "Keres Passage", "Khione", "Pylon", 
                   "Radeon", "Subsequence", "Sylphid", "Vermeer"]
        
        # Get vetoed maps from both players
        vetoed_maps = set(p1.preferences.vetoed_maps + p2.preferences.vetoed_maps)
        
        # Return maps that aren't vetoed
        return [map_name for map_name in all_maps if map_name not in vetoed_maps]

    def generate_in_game_channel(self) -> str:
        """Generate a random 3-digit in-game channel name."""
        return "scevo" + str(random.randint(100, 999))

    def get_random_server(self) -> str:
        """Get a random server choice (placeholder for now)."""
        servers = ["US East", "US West", "Europe", "Asia"]
        return random.choice(servers)

    async def attempt_match(self):
        """Try to find and process all valid matches using the advanced algorithm."""
        if len(self.players) < 2:
            return  # Silent when not enough players

        print("🎯 Attempting to match players with advanced algorithm...")
        
        # Increment wait cycles for all players
        for player in self.players:
            player.wait_cycles += 1

        # Categorize players into original lists
        original_bw_only, original_sc2_only, original_both_races = self.categorize_players()
        
        print(f"   📊 Queue composition: BW-only={len(original_bw_only)}, SC2-only={len(original_sc2_only)}, Both={len(original_both_races)}")
        
        # Create working copies for this matching cycle
        bw_list = original_bw_only.copy()
        sc2_list = original_sc2_only.copy()
        both_races = original_both_races.copy()
        
        # Equalize BW and SC2 lists using both_races players
        bw_list, sc2_list, remaining_z = self.equalize_lists(bw_list, sc2_list, both_races)
        
        print(f"   📊 After equalization: BW={len(bw_list)}, SC2={len(sc2_list)}, Remaining Z={len(remaining_z)}")
        
        # Find matches
        matches = []
        
        # BW vs SC2 matches - choose smaller list as lead side
        if len(bw_list) > 0 and len(sc2_list) > 0:
            if len(bw_list) <= len(sc2_list):
                # BW list is smaller or equal - use BW as lead side
                lead_side, follow_side = bw_list, sc2_list
                is_bw_match = True
            else:
                # SC2 list is smaller - use SC2 as lead side
                lead_side, follow_side = sc2_list, bw_list
                is_bw_match = False
            
            bw_matches = self.find_matches(lead_side, follow_side, is_bw_match)
            matches.extend(bw_matches)
            print(f"   ✅ Found {len(bw_matches)} BW vs SC2 matches (lead: {len(lead_side)}, follow: {len(follow_side)})")
        
        # Process matches
        matched_players = set()
        for p1, p2 in matches:
            print(f"✅ Match found: {p1.user_id} vs {p2.user_id}")
            
            # Get available maps and pick one randomly
            available_maps = self.get_available_maps(p1, p2)
            if not available_maps:
                print(f"❌ No available maps for {p1.user_id} vs {p2.user_id}")
                continue
            
            map_choice = random.choice(available_maps)
            server_choice = self.get_random_server()
            in_game_channel = self.generate_in_game_channel()
            
            # Determine which races to use for the match
            # p1 is always from the lead side, p2 is always from the follow side
            if is_bw_match:
                # Lead side is BW, follow side is SC2
                p1_race = p1.get_race_for_match(True)  # BW race
                p2_race = p2.get_race_for_match(False)  # SC2 race
            else:
                # Lead side is SC2, follow side is BW
                p1_race = p1.get_race_for_match(False)  # SC2 race
                p2_race = p2.get_race_for_match(True)  # BW race
            
            # Create match in database
            match_id = self.db_writer.create_match_1v1(
                p1.discord_user_id,
                p2.discord_user_id,
                map_choice,
                server_choice
            )
            
            # Create match result
            match_result = MatchResult(
                match_id=match_id,
                player1_discord_id=p1.discord_user_id,
                player2_discord_id=p2.discord_user_id,
                player1_user_id=p1.user_id,
                player2_user_id=p2.user_id,
                player1_race=p1_race,
                player2_race=p2_race,
                map_choice=map_choice,
                server_choice=server_choice,
                in_game_channel=in_game_channel
            )
            
            # Call the match callback if set
            if self.match_callback:
                print(f"📞 Calling match callback for {p1.user_id} vs {p2.user_id}")
                self.match_callback(match_result)
            else:
                print("⚠️  No match callback set!")
            
            # Track matched players
            matched_players.add(p1.discord_user_id)
            matched_players.add(p2.discord_user_id)
        
        # Now clean up the matchmaker queue based on who was matched
        # Remove matched players from the original lists
        self._update_queue_after_matching(matched_players, original_bw_only, original_sc2_only, original_both_races)
        
        print(f"   📊 Final state: {len(matched_players)} players matched")

        if not matches:
            print("❌ No valid matches this round.")

    def _update_queue_after_matching(self, matched_players: set, original_bw_only: List[Player], 
                                   original_sc2_only: List[Player], original_both_races: List[Player]):
        """
        Update the matchmaker queue after matching by removing matched players.
        
        Args:
            matched_players: Set of Discord IDs of matched players
            original_bw_only: Original BW-only players list
            original_sc2_only: Original SC2-only players list  
            original_both_races: Original both-races players list
        """
        # Remove matched players from the main queue
        for discord_id in matched_players:
            self.remove_player(discord_id)
        
        # Log remaining players by category
        remaining_bw = [p for p in original_bw_only if p.discord_user_id not in matched_players]
        remaining_sc2 = [p for p in original_sc2_only if p.discord_user_id not in matched_players]
        remaining_both = [p for p in original_both_races if p.discord_user_id not in matched_players]
        
        print(f"   📊 Remaining players: BW-only={len(remaining_bw)}, SC2-only={len(remaining_sc2)}, Both={len(remaining_both)}")

    async def run(self):
        """Continuously try to match players every 5 seconds."""
        self.running = True
        print("🚀 Advanced matchmaker started - checking for matches every 5 seconds")
        while self.running:
            await asyncio.sleep(5)
            if len(self.players) > 0:
                print(f"⏰ Checking for matches with {len(self.players)} players in queue...")
            await self.attempt_match()

    def stop(self) -> None:
        """Stop matchmaking loop."""
        self.running = False

    def record_match_result(self, match_id: int, winner_discord_uid: Optional[int]) -> bool:
        """
        Record the result of a match and update MMR values.
        
        Args:
            match_id: The ID of the match to update
            winner_discord_uid: The Discord UID of the winner, or -1 for a draw
            
        Returns:
            True if the update was successful, False otherwise
        """
        # First, update the match result in the database
        success = self.db_writer.update_match_result_1v1(match_id, winner_discord_uid)
        if not success:
            return False
        
        # Get match details to determine races played
        match_data = self.db_reader.get_match_1v1(match_id)
        if not match_data:
            print(f"❌ Could not find match {match_id} for MMR calculation")
            return False
        
        # For now, we need to determine the races played
        # This is a limitation - we need to store race information in the match
        # For now, we'll use a default approach or get from player preferences
        player1_uid = match_data['player_1_discord_uid']
        player2_uid = match_data['player_2_discord_uid']
        
        # Get player preferences to determine races
        p1_prefs = self.db_reader.get_preferences_1v1(player1_uid)
        p2_prefs = self.db_reader.get_preferences_1v1(player2_uid)
        
        if not p1_prefs or not p2_prefs:
            print(f"❌ Could not get preferences for players in match {match_id}")
            return True  # Match result was recorded, but MMR not updated
        
        # Parse race preferences
        try:
            import json
            p1_races = json.loads(p1_prefs.get('last_chosen_races', '[]'))
            p2_races = json.loads(p2_prefs.get('last_chosen_races', '[]'))
        except (json.JSONDecodeError, TypeError):
            print(f"❌ Could not parse race preferences for match {match_id}")
            return True
        
        # For now, we'll update MMR for the first race of each player
        # TODO: This should be improved to store actual races played in the match
        if p1_races and p2_races:
            p1_race = p1_races[0]  # Use first selected race
            p2_race = p2_races[0]  # Use first selected race
            
            # Get current MMR values
            p1_mmr_data = self.db_reader.get_player_mmr_1v1(player1_uid, p1_race)
            p2_mmr_data = self.db_reader.get_player_mmr_1v1(player2_uid, p2_race)
            
            if p1_mmr_data and p2_mmr_data:
                p1_current_mmr = p1_mmr_data['mmr']
                p2_current_mmr = p2_mmr_data['mmr']
                
                # Calculate MMR changes
                from src.backend.services.mmr_service import MMRService
                mmr_service = MMRService()
                
                # Determine match result for MMR calculation
                if winner_discord_uid == -1:  # Draw
                    result = 0
                elif winner_discord_uid == player1_uid:  # Player 1 won
                    result = 1
                else:  # Player 2 won
                    result = 2
                
                # Calculate new MMR values
                mmr_outcome = mmr_service.calculate_new_mmr(
                    float(p1_current_mmr), 
                    float(p2_current_mmr), 
                    result
                )
                
                # Update MMR in database
                p1_won = result == 1
                p1_lost = result == 2
                p1_drawn = result == 0
                
                p2_won = result == 2
                p2_lost = result == 1
                p2_drawn = result == 0
                
                # Update both players' MMR
                self.db_writer.update_mmr_after_match(
                    player1_uid, p1_race, mmr_outcome.player_one_mmr,
                    won=p1_won, lost=p1_lost, drawn=p1_drawn
                )
                
                self.db_writer.update_mmr_after_match(
                    player2_uid, p2_race, mmr_outcome.player_two_mmr,
                    won=p2_won, lost=p2_lost, drawn=p2_drawn
                )
                
                print(f"📊 Updated MMR for match {match_id}:")
                print(f"   Player 1 ({player1_uid}): {p1_current_mmr} → {mmr_outcome.player_one_mmr:.1f} ({p1_race})")
                print(f"   Player 2 ({player2_uid}): {p2_current_mmr} → {mmr_outcome.player_two_mmr:.1f} ({p2_race})")
            else:
                print(f"❌ Could not get MMR data for players in match {match_id}")
        
        return True


# Global matchmaker instance
matchmaker = Matchmaker()


async def main() -> None:
    mm = Matchmaker()

    # Start matchmaking loop
    task_matchmaker = asyncio.create_task(mm.run())

    # Start player join simulation
    task_joins = asyncio.create_task(simulate_player_joins(mm))

    # Let simulation run for 30 seconds
    await asyncio.sleep(3000)

    # Stop everything
    mm.stop()
    await task_matchmaker
    task_joins.cancel()


if __name__ == "__main__":
    asyncio.run(main())