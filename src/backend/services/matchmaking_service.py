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
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.backend.core import config
from src.backend.services.maps_service import MapsService
from src.backend.services.regions_service import RegionsService

@dataclass
class QueuePreferences:
	"""Player's queue preferences"""
	selected_races: List[str]
	vetoed_maps: List[str]
	discord_user_id: int
	user_id: str  # The player's "gamer name"

@dataclass
class MatchResult:
    """Represents the result of a match."""
    match_id: int
    player_1_discord_id: int
    player_2_discord_id: int
    player_1_user_id: str
    player_2_user_id: str
    player_1_race: str
    player_2_race: str
    map_choice: str
    server_choice: str
    in_game_channel: str
    match_result: Optional[str] = None
    match_result_confirmation_status: Optional[str] = None
    replay_uploaded: str = "No"
    replay_upload_time: Optional[int] = None
    # Cached ranks for performance
    player_1_rank: Optional[str] = None
    player_2_rank: Optional[str] = None

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
	# --- System Tuning Parameters ---
	# The time window in seconds to consider a player "active" after their last activity.
	# Chosen based on the average game length (10-15 minutes).
	ACTIVITY_WINDOW_SECONDS = config.MM_ACTIVITY_WINDOW_SECONDS

	# How often to prune the recent_activity list, in seconds.
	PRUNE_INTERVAL_SECONDS = config.MM_PRUNE_INTERVAL_SECONDS

	# Global matchmaking interval (matchwave) in seconds.
	MATCH_INTERVAL_SECONDS = config.MM_MATCH_INTERVAL_SECONDS

	# Time window in seconds for players to abort a match after it's found.
	ABORT_TIMER_SECONDS = config.MM_ABORT_TIMER_SECONDS

	# The number of matchmaking waves before the MMR window expands.
	# With a 45-second wave interval, expansion occurs once per wave.
	MMR_EXPANSION_STEP = config.MM_MMR_EXPANSION_STEP

	# --- Queue Pressure Ratio Thresholds ---
	# Ratio of (players in queue) / (total active players).
	HIGH_PRESSURE_THRESHOLD = config.MM_HIGH_PRESSURE_THRESHOLD
	MODERATE_PRESSURE_THRESHOLD = config.MM_MODERATE_PRESSURE_THRESHOLD

	# --- MMR Window Parameters (Base, Growth) ---
	# (base, growth) values for the max_diff function under different pressures.
	HIGH_PRESSURE_PARAMS = config.MM_HIGH_PRESSURE_PARAMS
	MODERATE_PRESSURE_PARAMS = config.MM_MODERATE_PRESSURE_PARAMS
	LOW_PRESSURE_PARAMS = config.MM_LOW_PRESSURE_PARAMS
	DEFAULT_PARAMS = config.MM_DEFAULT_PARAMS

	def __init__(self, players: Optional[List[Player]] = None):
		self.players: List[Player] = players or []
		self.running = False
		self.match_callback: Optional[Callable[[MatchResult], None]] = None
		self.regions_service = RegionsService()
		self.maps_service = MapsService()
		self.lock = asyncio.Lock()
		
		# System for tracking effective population
		self.recent_activity: Dict[int, float] = {}
		self.last_prune_time: float = time.time()
		
		# Track last matchmaking time for accurate timer display
		self.last_match_time: float = time.time()

	async def add_player(self, player: Player) -> None:
		"""Add a player to the matchmaking pool with MMR lookup."""
		from src.backend.services.performance_service import FlowTracker
		from src.backend.services.data_access_service import DataAccessService
		flow = FlowTracker(f"matchmaker.add_player", user_id=player.discord_user_id)
		
		flow.checkpoint("start_mmr_lookups")
		# Get MMRs from DataAccessService (in-memory, sub-millisecond)
		data_service = DataAccessService()
		
		for race in player.preferences.selected_races:
			# Get MMR from DataAccessService (in-memory, instant)
			mmr_value = data_service.get_player_mmr(player.discord_user_id, race)
			
			if mmr_value is not None:
				# MMR found in memory
				if race.startswith("bw_"):
					player.bw_mmr = mmr_value
				elif race.startswith("sc2_"):
					player.sc2_mmr = mmr_value
			else:
				# MMR not found - create default MMR entry
				print(f"[DataAccessService] MMR not found for {player.discord_user_id}/{race}, creating default")
				from src.backend.services.mmr_service import MMRService
				mmr_service = MMRService()
				default_mmr = mmr_service.default_mmr()
				
				# Create MMR using DataAccessService (async write to DB)
				await data_service.create_or_update_mmr(
					player.discord_user_id,
					player.user_id,
					race,
					default_mmr
				)
				
				if race.startswith("bw_"):
					player.bw_mmr = default_mmr
				elif race.startswith("sc2_"):
					player.sc2_mmr = default_mmr

		flow.checkpoint("mmr_lookups_complete")
		
		async with self.lock:
			flow.checkpoint("acquired_lock")
			print(f"👤 {player.user_id} (Discord ID: {player.discord_user_id}) joined the queue")
			print(f"   Selected races: {player.preferences.selected_races}")
			print(f"   BW MMR: {player.bw_mmr}, SC2 MMR: {player.sc2_mmr}")
			print(f"   Vetoed maps: {player.preferences.vetoed_maps}")
			self.players.append(player)
			print(f"   Total players in queue: {len(self.players)}")
			
			# Log player activity
			self.recent_activity[player.discord_user_id] = time.time()
		
		flow.complete("success")

	async def remove_player(self, discord_user_id: int) -> None:
		"""Remove a player from the matchmaking pool by Discord ID."""
		async with self.lock:
			before_count = len(self.players)
			self.players = [p for p in self.players if p.discord_user_id != discord_user_id]
			after_count = len(self.players)
			print(f"🚪 Player with Discord ID {discord_user_id} left the queue")
			print(f"   Players before removal: {before_count}, after: {after_count}")

	async def remove_players_from_matchmaking_queue(self, discord_user_ids: List[int]) -> None:
		"""
		Remove multiple players from the matchmaking queue when they get matched.
		
		This is called when players are successfully matched and should be removed
		from the matchmaking pool to prevent them from being matched again.
		
		Args:
			discord_user_ids: List of Discord user IDs to remove from the queue
		"""
		async with self.lock:
			before_count = len(self.players)
			self.players = [p for p in self.players if p.discord_user_id not in discord_user_ids]
			after_count = len(self.players)
			removed_count = before_count - after_count
			print(f"🎯 Removed {removed_count} matched players from matchmaking queue")
			print(f"   Players before removal: {before_count}, after: {after_count}")

	async def release_queue_lock_for_players(self, discord_user_ids: List[int]) -> None:
		"""
		Release the queue lock for players when a match is resolved or aborted.
		
		This allows players to queue again after their match is completed.
		This is different from removing from matchmaking queue - these players
		are already out of the matchmaking queue but need their queue lock released.
		
		Args:
			discord_user_ids: List of Discord user IDs to release from queue lock
		"""
		# This method handles the queue lock release logic
		# The actual queue lock is managed in the bot commands, but this method
		# can be used to trigger the release process
		print(f"🔓 Releasing queue lock for {len(discord_user_ids)} players after match resolution")
		
		# Import here to avoid circular imports
		from src.bot.commands.queue_command import queue_searching_view_manager, match_results, channel_to_match_view_map
		
		# Remove players from the queue searching views and match results
		for discord_user_id in discord_user_ids:
			# Remove from queue searching view manager
			await queue_searching_view_manager.unregister(discord_user_id)
			
			# Remove from match results if present
			match_results.pop(discord_user_id, None)
			
			# Remove from channel_to_match_view_map if present
			# Need to find and remove all channels where this player has a match view
			channels_to_remove = []
			for channel_id, match_view in list(channel_to_match_view_map.items()):
				if (match_view.match_result.player_1_discord_id == discord_user_id or 
				    match_view.match_result.player_2_discord_id == discord_user_id):
					channels_to_remove.append(channel_id)
			
			for channel_id in channels_to_remove:
				channel_to_match_view_map.pop(channel_id, None)
				print(f"🔓 Removed match view for player {discord_user_id} from channel {channel_id}")
			
			print(f"🔓 Released queue lock for player {discord_user_id}")

	def set_match_callback(self, callback: Callable[[MatchResult, Callable[[Callable], None]], None]) -> None:
		"""Set the callback function to be called when a match is found."""
		self.match_callback = callback

	def get_queue_snapshot(self) -> Dict[str, int]:
		"""Return current queue statistics for UI display."""
		current_players = list(self.players)
		bw_only, sc2_only, both_races = self.categorize_players(current_players)
		return {
			"active_population": len(self.recent_activity),
			"bw_only": len(bw_only),
			"sc2_only": len(sc2_only),
			"both_races": len(both_races),
		}

	def _calculate_queue_pressure(self, queue_size: int, effective_pop: int) -> float:
		"""Calculate the scale-adjusted queue pressure ratio."""
		if effective_pop <= 0:
			return 0.0

		if effective_pop <= 25:
			scale = 1.2  # amplify impact in small populations
		elif effective_pop <= 100:
			scale = 1.0  # balanced default
		else:
			scale = 0.8  # dampen for large populations

		return min(1.0, (scale * queue_size) / effective_pop)

	def max_diff(self, wait_cycles: int) -> int:
		"""
		Calculate max MMR difference based on queue pressure and wait time.
		"""
		queue_size = len(self.players)
		effective_pop = len(self.recent_activity)
		
		# Avoid division by zero if no one is active
		if effective_pop == 0:
			# Fallback to a default conservative behavior
			base, growth = self.DEFAULT_PARAMS
		else:
			pressure_ratio = self._calculate_queue_pressure(queue_size, effective_pop)

			if pressure_ratio >= self.HIGH_PRESSURE_THRESHOLD:  # High pressure
				base, growth = self.HIGH_PRESSURE_PARAMS
			elif pressure_ratio >= self.MODERATE_PRESSURE_THRESHOLD:  # Moderate pressure
				base, growth = self.MODERATE_PRESSURE_PARAMS
			else:  # Low pressure
				base, growth = self.LOW_PRESSURE_PARAMS

		# Increase MMR range once per matchmaking wave
		return base + (wait_cycles // self.MMR_EXPANSION_STEP) * growth

	def categorize_players(self, players: List[Player]) -> Tuple[List[Player], List[Player], List[Player]]:
		"""
		Categorize players into BW-only, SC2-only, and both lists.
		
		Returns:
			Tuple of (bw_only, sc2_only, both_races) lists, sorted by MMR
		"""
		bw_only = []
		sc2_only = []
		both_races = []
		
		for player in players:
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
			max_diff = self.max_diff(lead_player.wait_cycles)
			
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

	def generate_in_game_channel(self) -> str:
		"""Generate a random 3-digit in-game channel name."""
		return "scevo" + str(random.randint(100, 999))

	def _get_available_maps(self, p1: Player, p2: Player) -> List[str]:
		"""Get maps that haven't been vetoed by either player using maps service.
		
		Returns full map names.
		"""
		all_maps = self.maps_service.get_available_maps()
		
		# Get vetoed maps from both players (now full names)
		vetoed_maps = set(p1.preferences.vetoed_maps + p2.preferences.vetoed_maps)
		
		# Return maps that aren't vetoed
		return [map_name for map_name in all_maps if map_name not in vetoed_maps]

	async def attempt_match(self):
		"""Try to find and process all valid matches using the advanced algorithm."""
		from src.backend.services.performance_service import FlowTracker
		flow = FlowTracker("matchmaker.attempt_match")
		
		flow.checkpoint("copy_player_list")
		# Operate on a copy of the list to prevent race conditions from new players joining
		current_players = self.players.copy()
		
		if len(current_players) < 2:
			flow.complete("not_enough_players")
			return  # Silent when not enough players

		print("🎯 Attempting to match players with advanced algorithm...")
		
		flow.checkpoint("increment_wait_cycles")
		# Increment wait cycles for all players
		for player in current_players:
			player.wait_cycles += 1

		flow.checkpoint("categorize_players")
		# Categorize players into original lists
		original_bw_only, original_sc2_only, original_both_races = self.categorize_players(current_players)
		
		print(f"   📊 Queue composition: BW-only={len(original_bw_only)}, SC2-only={len(original_sc2_only)}, Both={len(original_both_races)}")
		
		# Create working copies for this matching cycle
		bw_list = original_bw_only.copy()
		sc2_list = original_sc2_only.copy()
		both_races = original_both_races.copy()
		
		flow.checkpoint("equalize_lists")
		# Equalize BW and SC2 lists using both_races players
		bw_list, sc2_list, remaining_z = self.equalize_lists(bw_list, sc2_list, both_races)
		
		print(f"   📊 After equalization: BW={len(bw_list)}, SC2={len(sc2_list)}, Remaining Z={len(remaining_z)}")
		
		flow.checkpoint("find_matches_start")
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
		
		flow.checkpoint("find_matches_complete")
		
		flow.checkpoint("process_matches_start")
		# Process matches
		matched_players = set()
		for p1, p2 in matches:
			print(f"✅ Match found: {p1.user_id} vs {p2.user_id}")
			available_maps = self._get_available_maps(p1, p2)
			if not available_maps:
				print(f"❌ No available maps for {p1.user_id} vs {p2.user_id}")
				continue
					
			map_choice = random.choice(available_maps)
			server_choice = self.regions_service.get_random_game_server()
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
			
			# Get current MMR values for both players
			p1_mmr = int(p1.get_effective_mmr(is_bw_match) or 1500)
			p2_mmr = int(p2.get_effective_mmr(not is_bw_match) or 1500)
			
			flow.checkpoint(f"create_match_db_start_{p1.discord_user_id}_vs_{p2.discord_user_id}")
			# Create the match record using DataAccessService (writes to memory + DB)
			from src.backend.services.data_access_service import DataAccessService
			data_service = DataAccessService()
			
			match_data = {
				'player_1_discord_uid': p1.discord_user_id,
				'player_2_discord_uid': p2.discord_user_id,
				'player_1_race': p1_race,
				'player_2_race': p2_race,
				'map_played': map_choice,
				'server_choice': server_choice,
				'player_1_mmr': p1_mmr,
				'player_2_mmr': p2_mmr,
				'mmr_change': 0  # MMR change will be calculated and updated after match result
			}
			
			match_id = await data_service.create_match(match_data)
			flow.checkpoint(f"create_match_db_complete_{p1.discord_user_id}_vs_{p2.discord_user_id}")

			flow.checkpoint(f"create_match_result_object_{p1.discord_user_id}_vs_{p2.discord_user_id}")
			
			# Get cached ranks for performance (avoid dynamic calculation in embed)
			from src.backend.services.app_context import ranking_service
			p1_rank = ranking_service.get_letter_rank(p1.discord_user_id, p1_race)
			p2_rank = ranking_service.get_letter_rank(p2.discord_user_id, p2_race)
			
			match_result = MatchResult(
				match_id=match_id,
				player_1_discord_id=p1.discord_user_id,
				player_2_discord_id=p2.discord_user_id,
				player_1_user_id=p1.user_id,
				player_2_user_id=p2.user_id,
				player_1_race=p1_race,
				player_2_race=p2_race,
				map_choice=map_choice,
				server_choice=server_choice,
				in_game_channel=in_game_channel,
				player_1_rank=p1_rank,
				player_2_rank=p2_rank
			)
					
			from src.backend.services.match_completion_service import match_completion_service

			flow.checkpoint(f"invoke_match_callback_{p1.discord_user_id}_vs_{p2.discord_user_id}")
			if self.match_callback:
				print(f"📞 Calling match callback for {p1.user_id} vs {p2.user_id}")
				self.match_callback(
					match_result,
					register_completion_callback=lambda callback: match_completion_service.start_monitoring_match(
						match_id,
						on_complete_callback=callback
					)
				)
			else:
				# If no frontend is registered, still monitor the match so backend workflows continue
				match_completion_service.start_monitoring_match(match_id)
				print("⚠️  No match callback set!")
			
			flow.checkpoint(f"match_callback_complete_{p1.discord_user_id}_vs_{p2.discord_user_id}")
					
			# Track matched players
			matched_players.add(p1.discord_user_id)
			matched_players.add(p2.discord_user_id)
		
		flow.checkpoint("process_matches_complete")
		
		flow.checkpoint("update_queue_start")
		# Now clean up the matchmaker queue based on who was matched
		# Remove matched players from the original lists
		await self._update_queue_after_matching(matched_players, original_bw_only, original_sc2_only, original_both_races)
		flow.checkpoint("update_queue_complete")
		
		print(f"   📊 Final state: {len(matched_players)} players matched")

		if not matches:
			print("❌ No valid matches this round.")
		
		flow.complete("success")

	def _prune_recent_activity(self):
		"""Remove players from activity log if they haven't been seen in 15 minutes."""
		now = time.time()
		stale_players = [
			uid for uid, timestamp in self.recent_activity.items()
			if now - timestamp > self.ACTIVITY_WINDOW_SECONDS
		]
		for uid in stale_players:
			del self.recent_activity[uid]

	async def _update_queue_after_matching(self, matched_players: set, original_bw_only: List[Player], 
								   original_sc2_only: List[Player], original_both_races: List[Player]):
		"""
		Update the matchmaker queue after matching by removing matched players.
		
		Args:
			matched_players: Set of Discord IDs of matched players
			original_bw_only: Original BW-only players list
			original_sc2_only: Original SC2-only players list  
			original_both_races: Original both-races players list
		"""
		# Update activity for matched players
		timestamp = time.time()
		for discord_id in matched_players:
			self.recent_activity[discord_id] = timestamp
			
		# Remove matched players from the matchmaking queue
		matched_player_list = list(matched_players)
		await self.remove_players_from_matchmaking_queue(matched_player_list)
		
		# Log remaining players by category
		remaining_bw = [p for p in original_bw_only if p.discord_user_id not in matched_players]
		remaining_sc2 = [p for p in original_sc2_only if p.discord_user_id not in matched_players]
		remaining_both = [p for p in original_both_races if p.discord_user_id not in matched_players]
		
		print(f"   📊 Remaining players: BW-only={len(remaining_bw)}, SC2-only={len(remaining_sc2)}, Both={len(remaining_both)}")

	async def run(self):
		"""Continuously try to match players every MATCH_INTERVAL_SECONDS."""
		self.running = True
		print("🚀 Advanced matchmaker started - checking for matches every 45 seconds")

		interval = self.MATCH_INTERVAL_SECONDS

		while self.running:
			import math
			
			# Optimized Unix-epoch synchronization
			now = time.time()
			# Use floor division to avoid floating remainder jitter
			next_tick = math.floor(now / interval + 1.0) * interval
			sleep_duration = next_tick - now
			
			# Clamp small negatives to zero (clock drift or scheduler delay)
			if sleep_duration < 0:
				sleep_duration = 0.0
			
			if sleep_duration > 0:
				await asyncio.sleep(sleep_duration)
				if not self.running:
					break

			# Update last match time for display purposes
			self.last_match_time = time.time()

			# Prune stale activity data periodically
			current_time = time.time()
			if current_time - self.last_prune_time > self.PRUNE_INTERVAL_SECONDS:
				self._prune_recent_activity()
				self.last_prune_time = current_time

			if len(self.players) > 0:
				print(f"⏰ Checking for matches with {len(self.players)} players in queue...")
			await self.attempt_match()

	def stop(self) -> None:
		"""Stop matchmaking loop."""
		self.running = False

	async def record_match_result(self, match_id: int, player_discord_uid: int, report_value: int) -> bool:
		"""
		Record a player's report for a match. This is the single entry point for any report.
		Uses DataAccessService for fast, non-blocking writes.
		
		Respects the atomic status field to prevent recording results for already-completed matches.
		"""
		# Use DataAccessService for fast in-memory updates
		from src.backend.services.data_access_service import DataAccessService
		from src.backend.services.match_completion_service import match_completion_service
		data_service = DataAccessService()
		
		# Acquire lock to prevent race conditions with abort/complete operations
		lock = match_completion_service._get_lock(match_id)
		async with lock:
			# Check current match status - if already terminal, reject the report
			match_data = data_service.get_match(match_id)
			if not match_data:
				print(f"[Matchmaker] Cannot record result for match {match_id}: match not found in memory")
				return False
			
			current_status = match_data.get('status', 'IN_PROGRESS')
			if current_status in ('COMPLETE', 'ABORTED', 'CONFLICT', 'PROCESSING_COMPLETION'):
				print(f"[Matchmaker] Cannot record result for match {match_id}: already in terminal/processing state {current_status}")
				return False
			
			# Update in-memory match data immediately
			success = data_service.update_match_report(match_id, player_discord_uid, report_value)
			if not success:
				print(f"[Matchmaker] Failed to update player report for match {match_id} in memory.")
				return False
		
		# After any report, trigger an immediate check (outside the lock to avoid deadlock).
		# This will pick up aborts, conflicts, or completions instantly.
		import asyncio
		print(f"[Matchmaker] Triggering immediate completion check for match {match_id} after a report.")
		asyncio.create_task(match_completion_service.check_match_completion(match_id))
		
		return True
	
	async def abort_match(self, match_id: int, player_discord_uid: int) -> bool:
		"""
		Abort a match and decrement the player's abort count.
		
		This operation is atomic and prevents race conditions by acquiring
		the same lock used by check_match_completion.
		
		Args:
			match_id: The ID of the match to abort.
			player_discord_uid: The Discord UID of the player initiating the abort.
			
		Returns:
			True if the abort was successful, False otherwise.
		"""
		# Use DataAccessService for fast abort operations
		from src.backend.services.data_access_service import DataAccessService
		from src.backend.services.match_completion_service import match_completion_service
		data_service = DataAccessService()
		
		# Acquire the same lock used by check_match_completion to prevent race conditions
		lock = match_completion_service._get_lock(match_id)
		async with lock:
			# Check current match status - if already terminal, reject the abort
			match_data = data_service.get_match(match_id)
			if not match_data:
				print(f"[Matchmaker] Cannot abort match {match_id}: match not found in memory")
				return False
			
			current_status = match_data.get('status', 'IN_PROGRESS')
			if current_status in ('COMPLETE', 'ABORTED', 'CONFLICT'):
				print(f"[Matchmaker] Cannot abort match {match_id}: already in terminal state {current_status}")
				return False
			
			# Abort the match in memory and queue DB write
			success = await data_service.abort_match(match_id, player_discord_uid)
			
			if success:
				# Atomically transition to ABORTED state
				data_service.update_match_status(match_id, 'ABORTED')
				print(f"[Matchmaker] Match {match_id} aborted by player {player_discord_uid}, status updated to ABORTED")
				
				# Trigger immediate completion check to notify all players
				# This ensures both players receive the abort notification
				print(f"[Matchmaker] Triggering immediate completion check for match {match_id} after abort.")
				import asyncio
				asyncio.create_task(match_completion_service.check_match_completion(match_id))
			
			return success
	
	async def _calculate_and_write_mmr(self, match_id: int, match_data: dict) -> bool:
		"""Helper to calculate and write MMR changes using DataAccessService."""
		# Get match details from DataAccessService (in-memory, instant)
		from src.backend.services.data_access_service import DataAccessService
		data_service = DataAccessService()
		
		match_data = data_service.get_match(match_id)
		if not match_data:
			print(f"[Matchmaker] Could not find match {match_id} in memory")
			return False
		
		# Guard: Check if MMR has already been calculated for this match
		# Only skip if both in-memory and database are consistent
		if match_data.get('mmr_change') != 0.0:
			# Verify that the database actually has the updated MMR values
			# If not, we need to recalculate
			try:
				from src.backend.db.db_reader_writer import DatabaseReader
				db_reader = DatabaseReader()
				
				# Check if database MMR values match in-memory values
				p1_uid = match_data['player_1_discord_uid']
				p2_uid = match_data['player_2_discord_uid']
				p1_race = match_data.get('player_1_race')
				p2_race = match_data.get('player_2_race')
				
				if p1_race and p2_race:
					p1_mmr_db = db_reader.get_player_mmr_1v1(p1_uid, p1_race)
					p2_mmr_db = db_reader.get_player_mmr_1v1(p2_uid, p2_race)
					
					p1_mmr_memory = data_service.get_player_mmr(p1_uid, p1_race)
					p2_mmr_memory = data_service.get_player_mmr(p2_uid, p2_race)
					
					print(f"[Matchmaker] MMR Consistency Check for match {match_id}:")
					print(f"  Player 1 DB: {p1_mmr_db['mmr'] if p1_mmr_db else 'None'}, Memory: {p1_mmr_memory}")
					print(f"  Player 2 DB: {p2_mmr_db['mmr'] if p2_mmr_db else 'None'}, Memory: {p2_mmr_memory}")
					
					# If database and memory don't match, we need to recalculate
					# Also, if the match has an MMR change but the database MMR values haven't been updated, recalculate
					db_memory_mismatch = (p1_mmr_db and p1_mmr_memory and abs(p1_mmr_db['mmr'] - p1_mmr_memory) > 0.1) or \
										(p2_mmr_db and p2_mmr_memory and abs(p2_mmr_db['mmr'] - p2_mmr_memory) > 0.1)
					
					# Check if database MMR values are stale (haven't been updated from the match)
					# If the match has an MMR change but the database values are the same as before the match, recalculate
					mmr_change = match_data.get('mmr_change', 0)
					if mmr_change != 0 and not db_memory_mismatch:
						# The match has an MMR change recorded, but let's verify the database was actually updated
						# If the database values are the same as the original match values, the database write failed
						print(f"[Matchmaker] Match {match_id} has MMR change {mmr_change} but database may not be updated. Recalculating to ensure consistency.")
						db_memory_mismatch = True
					
					if db_memory_mismatch:
						print(f"[Matchmaker] Database and memory MMR values don't match for match {match_id}. Recalculating.")
					else:
						print(f"[Matchmaker] MMR for match {match_id} has already been calculated. Skipping.")
						return True
				else:
					print(f"[Matchmaker] MMR for match {match_id} has already been calculated. Skipping.")
					return True
			except Exception as e:
				print(f"[Matchmaker] Error checking MMR consistency for match {match_id}: {e}")
				# If we can't verify, proceed with calculation
				pass
		
		# Check if both players have reported and if their reports match
		p1_report = match_data.get('player_1_report')
		p2_report = match_data.get('player_2_report')
		
		if p1_report is None or p2_report is None:
			print(f"[Matchmaker] Player report recorded for match {match_id}, waiting for other player")
			return True
		
		# Determine match result from player reports
		# Reports: 0=draw, 1=player 1 wins, 2=player 2 wins, -1=aborted, -3=aborted by this player
		if p1_report == -3 or p2_report == -3:
			# Match was aborted
			match_result = -1
		elif p1_report == -1 and p2_report == -1:
			# Both players aborted
			match_result = -1
		elif p1_report == 0 and p2_report == 0:
			# Both players agree on draw
			match_result = 0
		elif p1_report == 1 and p2_report == 1:
			# Both players agree player 1 wins
			match_result = 1
		elif p1_report == 2 and p2_report == 2:
			# Both players agree player 2 wins
			match_result = 2
		elif p1_report == 1 and p2_report == 2:
			# Conflicting reports - one says P1 wins, other says P2 wins
			match_result = -2
		elif p1_report == 2 and p2_report == 1:
			# Conflicting reports - one says P2 wins, other says P1 wins
			match_result = -2
		elif p1_report == 0 and p2_report in [1, 2]:
			# Conflicting reports - one says draw, other says win
			match_result = -2
		elif p2_report == 0 and p1_report in [1, 2]:
			# Conflicting reports - one says draw, other says win
			match_result = -2
		else:
			# Conflicting reports
			match_result = -2
		
		print(f"[Matchmaker] Match {match_id} result determined: {match_result} (p1={p1_report}, p2={p2_report})")
		
		if match_result == -1:
			print(f"[Matchmaker] Match {match_id} was aborted. Skipping MMR calculation.")
			return True

		if match_result == -2:
			print(f"[Matchmaker] Conflicting reports for match {match_id}, manual resolution required")
			return True
		
		# Both players have reported and reports match - process MMR
		print(f"[Matchmaker] Both players reported for match {match_id}, processing MMR changes")
		
		player1_uid = match_data['player_1_discord_uid']
		player2_uid = match_data['player_2_discord_uid']
		
		# Get the races that were actually played from the match data
		p1_race = match_data.get('player_1_race')
		p2_race = match_data.get('player_2_race')

		if p1_race and p2_race:
			# Get current MMR values from DataAccessService (in-memory, instant)
			p1_current_mmr = data_service.get_player_mmr(player1_uid, p1_race)
			p2_current_mmr = data_service.get_player_mmr(player2_uid, p2_race)
			
			if p1_current_mmr is not None and p2_current_mmr is not None:
				# Calculate MMR changes
				from src.backend.services.mmr_service import MMRService
				mmr_service = MMRService()
				
				# Update match result in database
				await data_service.update_match(match_id, match_result=match_result)
				
				# Calculate new MMR values
				mmr_outcome = mmr_service.calculate_new_mmr(
					p1_current_mmr, 
					p2_current_mmr, 
					match_result
				)
				
				# Determine game outcomes
				p1_won = match_result == 1
				p1_lost = match_result == 2
				p1_drawn = match_result == 0
				
				p2_won = match_result == 2
				p2_lost = match_result == 1
				p2_drawn = match_result == 0
				
				# Get current game counts from DataAccessService
				p1_all_mmrs = data_service.get_all_player_mmrs(player1_uid)
				p2_all_mmrs = data_service.get_all_player_mmrs(player2_uid)
				
				# Update both players' MMR using DataAccessService (async, non-blocking)
				await data_service.update_player_mmr(
					player1_uid, p1_race, int(mmr_outcome.player_one_mmr),
					games_won=1 if p1_won else None,
					games_lost=1 if p1_lost else None,
					games_drawn=1 if p1_drawn else None
				)
				
				await data_service.update_player_mmr(
					player2_uid, p2_race, int(mmr_outcome.player_two_mmr),
					games_won=1 if p2_won else None,
					games_lost=1 if p2_lost else None,
					games_drawn=1 if p2_drawn else None
				)
				
			# Calculate and store MMR change
			p1_mmr_change = mmr_service.calculate_mmr_change(
				p1_current_mmr, 
				p2_current_mmr, 
				match_result
			)
			
			# Update match MMR change using DataAccessService (async, non-blocking)
			await data_service.update_match_mmr_change(match_id, p1_mmr_change)
			
			print(f"[Matchmaker] Updated MMR for match {match_id}:")
			print(f"   Player 1 ({player1_uid}): {p1_current_mmr} -> {mmr_outcome.player_one_mmr} ({p1_race})")
			print(f"   Player 2 ({player2_uid}): {p2_current_mmr} -> {mmr_outcome.player_two_mmr} ({p2_race})")
			print(f"   MMR Change: {p1_mmr_change:+} (positive = player 1 gained)")
			
			return p1_mmr_change
		else:
			print(f"[Matchmaker] Could not get MMR data for players in match {match_id}")
			return 0.0

	async def is_player_in_queue(self, discord_user_id: int) -> bool:
		"""Check if a player is in the queue."""
		async with self.lock:
			return any(p.discord_user_id == discord_user_id for p in self.players)

	def get_next_matchmaking_time(self) -> int:
		"""
		Get the Unix timestamp of the next matchmaking wave using optimized epoch sync.
		
		Returns:
			int: Unix timestamp of the next matchmaking wave
		"""
		import math
		
		now = time.time()
		interval = self.MATCH_INTERVAL_SECONDS
		
		# Use floor division to avoid floating remainder jitter
		next_tick = math.floor(now / interval + 1.0) * interval
		
		return int(next_tick)


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