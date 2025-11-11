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
from src.backend.services.mmr_service import MMRService

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
				 bw_mmr: Optional[int] = None, sc2_mmr: Optional[int] = None, 
				 residential_region: Optional[str] = None):
		self.discord_user_id = discord_user_id
		self.user_id = user_id
		self.preferences = preferences
		self.bw_mmr = bw_mmr
		self.sc2_mmr = sc2_mmr
		self.residential_region = residential_region
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
		
		# Store the planned next matchmaking time for accurate display
		self.next_match_time: float = time.time()

	async def add_player(self, player: Player) -> None:
		"""Add a player to the matchmaking pool with MMR lookup."""
		from src.backend.services.performance_service import FlowTracker
		from src.backend.services.data_access_service import DataAccessService
		
		flow = FlowTracker(f"matchmaker.add_player", user_id=player.discord_user_id)
		
		flow.checkpoint("start_data_lookups")
		# Get MMRs and region from DataAccessService (in-memory, sub-millisecond)
		data_service = DataAccessService()
		
		player_info = data_service.get_player_info(player.discord_user_id)
		if player_info and player_info.get('region'):
			player.residential_region = player_info['region']
		
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
				
				mmr_service = MMRService()
				default_mmr = mmr_service.default_mmr()
				
				# Get actual player name from player_info
				player_name = None
				if player_info:
					player_name = player_info.get('player_name') or player_info.get('discord_username')
				
				if not player_name:
					player_name = f"Player{player.discord_user_id}"
					print(f"[Matchmaker] WARNING: No player_name found for discord_uid={player.discord_user_id}, using fallback: {player_name}")
				
				# Create MMR using DataAccessService (async write to DB)
				await data_service.create_or_update_mmr(
					player.discord_user_id,
					player_name,
					race,
					default_mmr
				)
				
				if race.startswith("bw_"):
					player.bw_mmr = default_mmr
				elif race.startswith("sc2_"):
					player.sc2_mmr = default_mmr

		flow.checkpoint("data_lookups_complete")
		
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
		
		# Reset player states to idle
		from src.backend.services.app_context import data_access_service
		for discord_user_id in discord_user_ids:
			await data_access_service.set_player_state(discord_user_id, "idle")
		
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

	def get_queue_players(self) -> List[Player]:
		"""
		Get a snapshot of the current matchmaking queue players.
		
		Returns a copy of the players list for admin/monitoring purposes.
		This is thread-safe as it returns a copy.
		
		Returns:
			List of Player objects currently in queue
		"""
		return self.players.copy()
	
	def get_queue_size(self) -> int:
		"""
		Get the current number of players in the matchmaking queue.
		
		Returns:
			Integer count of players in queue
		"""
		return len(self.players)

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

		if effective_pop <= config.MM_POPULATION_THRESHOLD_LOW:
			scale = config.MM_PRESSURE_SCALE_LOW_POP  # amplify impact in small populations
		elif effective_pop <= config.MM_POPULATION_THRESHOLD_MID:
			scale = config.MM_PRESSURE_SCALE_MID_POP  # balanced default
		else:
			scale = config.MM_PRESSURE_SCALE_HIGH_POP  # dampen for large populations

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

	def _calculate_skill_bias(self, player: Player) -> int:
		"""
		Calculate skill bias for a "both" player.
		Positive = stronger at BW, Negative = stronger at SC2.
		
		Args:
			player: A player with both BW and SC2 races
			
		Returns:
			Skill bias (bw_mmr - sc2_mmr)
		"""
		bw_mmr = player.bw_mmr or config.MMR_DEFAULT
		sc2_mmr = player.sc2_mmr or config.MMR_DEFAULT
		return bw_mmr - sc2_mmr

	def equalize_lists(self, list_x: List[Player], list_y: List[Player], 
					  list_z: List[Player]) -> Tuple[List[Player], List[Player], List[Player]]:
		"""
		Intelligently equalize the sizes of list_x (BW) and list_y (SC2) by assigning 
		"both" players from list_z based on:
		1. Population balance (hard constraint)
		2. Skill bias (assign to stronger side)
		3. Mean MMR balance (soft constraint)
		
		Args:
			list_x: BW-only players list
			list_y: SC2-only players list
			list_z: Both-races players list
			
		Returns:
			Tuple of (equalized_bw, equalized_sc2, remaining_both)
		"""
		bw_list = list_x.copy()
		sc2_list = list_y.copy()
		both_players = list_z.copy()
		
		# Special case: if both X and Y are empty, distribute evenly by skill bias
		if not bw_list and not sc2_list and both_players:
			# Sort by skill bias (SC2-favoring to BW-favoring)
			both_players_sorted = sorted(both_players, key=lambda p: self._calculate_skill_bias(p))
			
			# Split evenly: first half to SC2, second half to BW
			mid = len(both_players_sorted) // 2
			sc2_list = both_players_sorted[:mid]
			bw_list = both_players_sorted[mid:]
			
			return bw_list, sc2_list, []
		
		if not both_players:
			# No "both" players to assign
			return bw_list, sc2_list, []
		
		# Step 1: Calculate population delta
		delta_n = len(bw_list) - len(sc2_list)
		
		# Step 2: Sort "both" players by skill bias (ascending: SC2-favoring first)
		both_players_sorted = sorted(both_players, key=lambda p: self._calculate_skill_bias(p))
		
		# Step 3: Assign players to balance counts (hard constraint)
		if delta_n < 0:
			# BW needs more players
			needed = abs(delta_n)
			# Take the most BW-favoring players (from the end)
			for _ in range(min(needed, len(both_players_sorted))):
				bw_list.append(both_players_sorted.pop())
		elif delta_n > 0:
			# SC2 needs more players
			needed = delta_n
			# Take the most SC2-favoring players (from the start)
			for _ in range(min(needed, len(both_players_sorted))):
				sc2_list.append(both_players_sorted.pop(0))
		
		# If lists are now equal and we have remaining "both" players, distribute evenly
		while len(both_players_sorted) > 0:
			if len(bw_list) < len(sc2_list):
				bw_list.append(both_players_sorted.pop())
			elif len(bw_list) > len(sc2_list):
				sc2_list.append(both_players_sorted.pop(0))
			else:
				# Equal - alternate
				if both_players_sorted:
					sc2_list.append(both_players_sorted.pop(0))
				if both_players_sorted:
					bw_list.append(both_players_sorted.pop())
		
		# Calculate population balance after Step 3
		current_pop_difference = abs(len(bw_list) - len(sc2_list))
		
		# Step 4: Calculate mean MMRs and rebalance if needed
		if len(bw_list) > 0 and len(sc2_list) > 0:
			bw_mean = sum(p.bw_mmr or config.MMR_DEFAULT for p in bw_list) / len(bw_list)
			sc2_mean = sum(p.sc2_mmr or config.MMR_DEFAULT for p in sc2_list) / len(sc2_list)
			mmr_delta = bw_mean - sc2_mean
			
			# If skill imbalance exceeds threshold, try to shift neutral players
			if abs(mmr_delta) > config.MM_BALANCE_THRESHOLD_MMR:
				# Find "both" players with small bias (neutral)
				both_in_bw = [p for p in bw_list if p.has_bw_race and p.has_sc2_race]
				both_in_sc2 = [p for p in sc2_list if p.has_bw_race and p.has_sc2_race]
				
				# Sort by absolute bias (most neutral first)
				both_in_bw.sort(key=lambda p: abs(self._calculate_skill_bias(p)))
				both_in_sc2.sort(key=lambda p: abs(self._calculate_skill_bias(p)))
				
				if mmr_delta > config.MM_BALANCE_THRESHOLD_MMR and both_in_bw:
					# BW is stronger, move neutral player to SC2
					# Only move if it doesn't worsen population balance
					new_pop_difference = abs((len(bw_list) - 1) - (len(sc2_list) + 1))
					if new_pop_difference <= current_pop_difference:
						player_to_move = both_in_bw[0]
						bw_list.remove(player_to_move)
						sc2_list.append(player_to_move)
				elif mmr_delta < -config.MM_BALANCE_THRESHOLD_MMR and both_in_sc2:
					# SC2 is stronger, move neutral player to BW
					# Only move if it doesn't worsen population balance
					new_pop_difference = abs((len(bw_list) + 1) - (len(sc2_list) - 1))
					if new_pop_difference <= current_pop_difference:
						player_to_move = both_in_sc2[0]
						sc2_list.remove(player_to_move)
						bw_list.append(player_to_move)
		
		return bw_list, sc2_list, []

	def _filter_by_priority(self, lead_side: List[Player], follow_side: List[Player]) -> Tuple[List[Player], List[Player]]:
		"""
		Filter players by priority to equalize sides before matching.
		
		If one side has more players, keep only the highest-priority players
		(most wait_cycles) up to the count of the smaller side.
		
		Args:
			lead_side: Lead side players list
			follow_side: Follow side players list
			
		Returns:
			Tuple of (filtered_lead, filtered_follow) with equal or near-equal sizes
		"""
		lead_count = len(lead_side)
		follow_count = len(follow_side)
		
		# If sides are already equal, no filtering needed
		if lead_count == follow_count:
			return lead_side, follow_side
		
		# Determine which side is larger
		if lead_count > follow_count:
			# Lead side has excess players - keep only top priority players
			target_count = follow_count
			sorted_lead = sorted(lead_side, key=lambda p: p.wait_cycles, reverse=True)
			filtered_lead = sorted_lead[:target_count]
			
			if len(filtered_lead) < lead_count:
				removed = lead_count - len(filtered_lead)
				print(f"   🔽 Filtered {removed} low-priority players from lead side (kept {len(filtered_lead)} highest priority)")
			
			return filtered_lead, follow_side
		else:
			# Follow side has excess players - keep only top priority players
			target_count = lead_count
			sorted_follow = sorted(follow_side, key=lambda p: p.wait_cycles, reverse=True)
			filtered_follow = sorted_follow[:target_count]
			
			if len(filtered_follow) < follow_count:
				removed = follow_count - len(filtered_follow)
				print(f"   🔽 Filtered {removed} low-priority players from follow side (kept {len(filtered_follow)} highest priority)")
			
			return lead_side, filtered_follow

	def _build_candidate_pairs(self, lead_side: List[Player], follow_side: List[Player],
							  is_bw_match: bool) -> List[Tuple[float, Player, Player, int]]:
		"""
		Build all valid match candidates within MMR windows.
		
		Args:
			lead_side: Players on the lead side
			follow_side: Players on the follow side
			is_bw_match: True if lead is BW, False if lead is SC2
			
		Returns:
			List of (score, lead_player, follow_player, mmr_diff) tuples
			Score is lower for better matches (squared MMR diff minus wait priority)
		"""
		candidates = []
		queue_size = len(self.players)
		
		for lead_player in lead_side:
			lead_mmr = lead_player.get_effective_mmr(is_bw_match) or 0
			max_diff = self.max_diff(lead_player.wait_cycles)
			
			for follow_player in follow_side:
				follow_mmr = follow_player.get_effective_mmr(not is_bw_match) or 0
				mmr_diff = abs(lead_mmr - follow_mmr)
				
				if mmr_diff <= max_diff:
					# Score: squared MMR diff minus wait priority
					# Lower score = better match
					wait_priority = (lead_player.wait_cycles + follow_player.wait_cycles)
					score = (mmr_diff ** 2) - (wait_priority * config.MM_WAIT_CYCLE_PRIORITY_COEFFICIENT)
					
					candidates.append((score, lead_player, follow_player, mmr_diff))
		
		return candidates

	def _select_matches_from_candidates(self, candidates: List[Tuple[float, Player, Player, int]]) -> List[Tuple[Player, Player]]:
		"""
		Greedily select matches from sorted candidates to maximize overall quality.
		
		Args:
			candidates: List of (score, lead_player, follow_player, mmr_diff)
			
		Returns:
			List of matched player pairs
		"""
		candidates.sort(key=lambda x: x[0])  # Sort by score ascending (lower is better)
		
		matches = []
		used_lead = set()
		used_follow = set()
		
		for score, lead_player, follow_player, mmr_diff in candidates:
			if (lead_player.discord_user_id not in used_lead and 
				follow_player.discord_user_id not in used_follow):
				matches.append((lead_player, follow_player))
				used_lead.add(lead_player.discord_user_id)
				used_follow.add(follow_player.discord_user_id)
		
		return matches

	def find_matches(self, lead_side: List[Player], follow_side: List[Player], 
					is_bw_match: bool) -> List[Tuple[Player, Player]]:
		"""
		Find matches between lead_side and follow_side players using locally-optimal algorithm.
		
		Uses candidate-based approach to minimize sum of squared MMR differences
		while respecting wait time priorities.
		
		Args:
			lead_side: List of players to match from
			follow_side: List of players to match against
			is_bw_match: True for BW vs SC2, False for SC2 vs BW
			
		Returns:
			List of matched player pairs
		"""
		if not lead_side or not follow_side:
			return []
		
		# Build all valid candidate pairs within MMR windows
		candidates = self._build_candidate_pairs(lead_side, follow_side, is_bw_match)
		
		# Select matches greedily from sorted candidates (minimizes squared MMR diffs)
		matches = self._select_matches_from_candidates(candidates)
		
		return matches

	def _refine_matches_least_squares(self, matches: List[Tuple[Player, Player]], 
									  is_bw_match: bool) -> List[Tuple[Player, Player]]:
		"""
		Perform adjacent swap passes to minimize sum of squared MMR differences.
		Runs for MM_REFINEMENT_PASSES iterations.
		Only swaps if both new pairs remain within their MMR windows.
		
		Args:
			matches: Initial list of matched player pairs
			is_bw_match: True if lead is BW, False if lead is SC2
			
		Returns:
			Refined list of matched player pairs
		"""
		if len(matches) < 2:
			return matches
		
		match_list = list(matches)  # Mutable copy
		total_swaps = 0
		
		for pass_num in range(config.MM_REFINEMENT_PASSES):
			swaps_made = False
			
			for i in range(len(match_list) - 1):
				p1_lead, p1_follow = match_list[i]
				p2_lead, p2_follow = match_list[i + 1]
				
				# Calculate current squared error
				p1_lead_mmr = p1_lead.get_effective_mmr(is_bw_match) or 0
				p1_follow_mmr = p1_follow.get_effective_mmr(not is_bw_match) or 0
				p2_lead_mmr = p2_lead.get_effective_mmr(is_bw_match) or 0
				p2_follow_mmr = p2_follow.get_effective_mmr(not is_bw_match) or 0
				
				error_before = ((p1_lead_mmr - p1_follow_mmr) ** 2 + 
							  (p2_lead_mmr - p2_follow_mmr) ** 2)
				
				# Calculate error after swap (swap follow players)
				error_after = ((p1_lead_mmr - p2_follow_mmr) ** 2 + 
							 (p2_lead_mmr - p1_follow_mmr) ** 2)
				
				if error_after < error_before:
					# Check if swap respects MMR windows
					max_diff_p1 = self.max_diff(p1_lead.wait_cycles)
					max_diff_p2 = self.max_diff(p2_lead.wait_cycles)
					
					new_diff_p1 = abs(p1_lead_mmr - p2_follow_mmr)
					new_diff_p2 = abs(p2_lead_mmr - p1_follow_mmr)
					
					if new_diff_p1 <= max_diff_p1 and new_diff_p2 <= max_diff_p2:
						# Perform swap
						match_list[i] = (p1_lead, p2_follow)
						match_list[i + 1] = (p2_lead, p1_follow)
						swaps_made = True
						total_swaps += 1
			
			# Early exit if no swaps in this pass
			if not swaps_made:
				break
		
		if total_swaps > 0:
			print(f"   🔄 Least-squares refinement: {total_swaps} swaps made across {pass_num + 1} passes")
		
		return match_list

	def generate_in_game_channel(self, match_id: int) -> str:
		"""
		Generate an in-game channel name based on the match ID.
		
		The channel name is scevo## where ## is based on the ones digit of the match_id:
		- If ones digit is 1-9: use that digit (padded to 2 digits)
		- If ones digit is 0: use 10
		
		Examples:
		- match_id=1 -> scevo01
		- match_id=9 -> scevo09
		- match_id=10 -> scevo10
		- match_id=11 -> scevo01
		- match_id=20 -> scevo10
		
		Args:
			match_id: The match ID
			
		Returns:
			In-game channel name in format scevo##
		"""
		ones_digit = match_id % config.MM_IN_GAME_CHANNEL_BASE_NUMBER
		channel_number = config.MM_IN_GAME_CHANNEL_BASE_NUMBER if ones_digit == 0 else ones_digit
		return f"{config.MM_IN_GAME_CHANNEL_PREFIX}{channel_number:02d}"

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
		
		# Log skill balance after equalization
		if len(bw_list) > 0 and len(sc2_list) > 0:
			bw_mean = sum(p.bw_mmr or config.MMR_DEFAULT for p in bw_list) / len(bw_list)
			sc2_mean = sum(p.sc2_mmr or config.MMR_DEFAULT for p in sc2_list) / len(sc2_list)
			print(f"   ⚖️  Skill balance: BW avg={bw_mean:.0f}, SC2 avg={sc2_mean:.0f}, delta={abs(bw_mean - sc2_mean):.0f}")
		
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
			
			# Apply priority-based filtering before matching
			lead_side, follow_side = self._filter_by_priority(lead_side, follow_side)
			print(f"   🎯 After priority filtering: lead={len(lead_side)}, follow={len(follow_side)}")
			
			bw_matches = self.find_matches(lead_side, follow_side, is_bw_match)
			
			# Apply least-squares refinement to improve match quality
			bw_matches = self._refine_matches_least_squares(bw_matches, is_bw_match)
			
			matches.extend(bw_matches)
			print(f"   ✅ Found {len(bw_matches)} BW vs SC2 matches (lead: {len(lead_side)}, follow: {len(follow_side)})")
			
			# Log match quality metrics
			if bw_matches:
				mmr_diffs = []
				for p1, p2 in bw_matches:
					p1_mmr = p1.get_effective_mmr(is_bw_match) or 0
					p2_mmr = p2.get_effective_mmr(not is_bw_match) or 0
					mmr_diffs.append(abs(p1_mmr - p2_mmr))
				
				avg_diff = sum(mmr_diffs) / len(mmr_diffs)
				min_diff = min(mmr_diffs)
				max_diff = max(mmr_diffs)
				print(f"   📈 Match quality: avg MMR diff={avg_diff:.1f}, min={min_diff}, max={max_diff}")
		
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
			
			# Determine optimal server based on player regions
			if p1.residential_region and p2.residential_region:
				try:
					from src.backend.services.regions_service import RegionMappingNotFoundError
					server_name = self.regions_service.get_match_server(
						p1.residential_region, 
						p2.residential_region
					)
					server_choice = self.regions_service.get_game_server_code_by_name(server_name)
					print(f"   🌍 Server selection: {p1.residential_region} + {p2.residential_region} → {server_choice}")
				except RegionMappingNotFoundError as e:
					print(f"   ⚠️  Region mapping not found: {e}")
					print(f"   🎲 Falling back to random server selection")
					server_choice = self.regions_service.get_random_game_server()
				except ValueError as e:
					print(f"   ⚠️  Server name lookup failed: {e}")
					print(f"   🎲 Falling back to random server selection")
					server_choice = self.regions_service.get_random_game_server()
			else:
				print(f"   ⚠️  Missing region data for one or both players")
				print(f"   🎲 Using random server selection")
				server_choice = self.regions_service.get_random_game_server()
				
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
			p1_mmr = int(p1.get_effective_mmr(is_bw_match) or config.MMR_DEFAULT)
			p2_mmr = int(p2.get_effective_mmr(not is_bw_match) or config.MMR_DEFAULT)
			
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
			
			# Set both players to in-match state
			await data_service.set_player_state(p1.discord_user_id, f"in_match:{match_id}")
			await data_service.set_player_state(p2.discord_user_id, f"in_match:{match_id}")
			
			# Generate in-game channel based on match_id
			in_game_channel = self.generate_in_game_channel(match_id)
			
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
		print(f"🚀 Advanced matchmaker started - checking for matches every {self.MATCH_INTERVAL_SECONDS} seconds")

		interval = self.MATCH_INTERVAL_SECONDS

		while self.running:
			import math
			
			# Optimized Unix-epoch synchronization
			now = time.time()
			# Use floor division to avoid floating remainder jitter
			next_tick = math.floor(now / interval + 1.0) * interval
			
			# Store the next match time BEFORE sleeping so display is accurate
			self.next_match_time = next_tick
			
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
			
			# After matching, immediately calculate and store the next match time
			# This ensures the display is accurate even during processing
			now_after_match = time.time()
			next_tick_after_match = math.floor(now_after_match / interval + 1.0) * interval
			self.next_match_time = next_tick_after_match

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
			# Check if match is already in a terminal state by inspecting database columns
			match_data = data_service.get_match(match_id)
			if not match_data:
				print(f"[Matchmaker] Cannot record result for match {match_id}: match not found in memory")
				return False
			
			# Determine if match is terminal based on ACTUAL database columns
			match_result = match_data.get('match_result')
			p1_report = match_data.get('player_1_report')
			p2_report = match_data.get('player_2_report')
			
			# Terminal conditions:
			# 1. match_result is set to a definitive value (-1=abort, -2=conflict, 0/1/2=result)
			# 2. Both players reported and agree (match should be processed)
			is_terminal = (
				match_result is not None and match_result in (-1, -2, 0, 1, 2)
			)
			
			if is_terminal:
				print(f"[Matchmaker] Cannot record result for match {match_id}: already terminal (result={match_result}, reports: p1={p1_report}, p2={p2_report})")
				return False
			
		# Update in-memory match data immediately
		success = data_service.update_match_report(match_id, player_discord_uid, report_value)
		if not success:
			print(f"[Matchmaker] Failed to update player report for match {match_id} in memory.")
			return False
		
		# Send notification to opponent if they haven't reported yet
		# Only for win/loss/draw reports (not aborts)
		if report_value in [0, 1, 2]:
			await self._notify_opponent_of_report(
				match_id, 
				player_discord_uid, 
				report_value, 
				match_data
			)
	
	# After any report, trigger an immediate check (outside the lock to avoid deadlock).
		# This will pick up aborts, conflicts, or completions instantly.
		import asyncio
		print(f"[Matchmaker] Triggering immediate completion check for match {match_id} after a report.")
		asyncio.create_task(match_completion_service.check_match_completion(match_id))
		
		return True
	
	async def _notify_opponent_of_report(
		self, 
		match_id: int, 
		reporting_player_uid: int, 
		report_value: int,
		match_data: dict
	) -> None:
		"""
		Notify the opponent that the reporting player has submitted their match result.
		Only sends if the opponent has NOT yet reported.
		
		Args:
			match_id: Match ID
			reporting_player_uid: Discord UID of the player who just reported
			report_value: The report value (0=draw, 1=player1 win, 2=player2 win)
			match_data: Current match data from DataAccessService
		"""
		try:
			from src.backend.services.process_pool_health import get_bot_instance
			from src.bot.utils.message_helpers import queue_user_send
			from src.backend.services.app_context import data_access_service
			import discord
			
			# Determine opponent
			player_1_uid = match_data['player_1_discord_uid']
			player_2_uid = match_data['player_2_discord_uid']
			p1_report = match_data.get('player_1_report')
			p2_report = match_data.get('player_2_report')
			
			# Determine which player is the opponent
			if reporting_player_uid == player_1_uid:
				opponent_uid = player_2_uid
				opponent_report = p2_report
			else:
				opponent_uid = player_1_uid
				opponent_report = p1_report
			
			# Only send if opponent hasn't reported yet
			if opponent_report is not None:
				return
			
			# Get player names
			reporting_player_info = data_access_service.get_player_info(reporting_player_uid)
			reporting_player_name = reporting_player_info.get('player_name', f'<@{reporting_player_uid}>')
			
			# Format the report text as full sentence
			if report_value == 0:
				report_text = "The match was a draw"
			elif report_value == 1:
				player_1_info = data_access_service.get_player_info(player_1_uid)
				player_1_name = player_1_info.get('player_name', f'<@{player_1_uid}>')
				report_text = f"{player_1_name} wins"
			else:  # report_value == 2
				player_2_info = data_access_service.get_player_info(player_2_uid)
				player_2_name = player_2_info.get('player_name', f'<@{player_2_uid}>')
				report_text = f"{player_2_name} wins"
			
			# Get bot instance and send notification
			bot = get_bot_instance()
			if bot:
				opponent_user = await bot.fetch_user(opponent_uid)
				
				# Create notification embed (blurple color)
				notification_embed = discord.Embed(
					title=f"Match #{match_id} - 📝 Your Opponent Reported",
					description=f"{reporting_player_name} reported: **{report_text}**\n\nIf you're seeing this, it likely means you have not reported the match result yet. **Please do so as soon as possible.**",
					color=discord.Color.blurple()
				)
				
				# Send via message queue (low priority, delayed delivery)
				await queue_user_send(opponent_user, embed=notification_embed)
				print(f"[Matchmaker] Sent opponent report notification to player {opponent_uid} for match {match_id}")
		
		except Exception as e:
			print(f"[Matchmaker] Failed to send opponent report notification for match {match_id}: {e}")
	
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
			# Check if match is already terminal by inspecting database columns
			match_data = data_service.get_match(match_id)
			if not match_data:
				print(f"[Matchmaker] Cannot abort match {match_id}: match not found in memory")
				return False
			
			# Check if match is already terminal based on match_result
			match_result = match_data.get('match_result')
			is_terminal = match_result is not None and match_result in (-1, -2, 0, 1, 2)
			
			if is_terminal:
				print(f"[Matchmaker] Cannot abort match {match_id}: already terminal (result={match_result})")
				return False
			
			# Abort the match in memory and queue DB write
			success = await data_service.abort_match(match_id, player_discord_uid)
			
			if success:
				print(f"[Matchmaker] Match {match_id} aborted by player {player_discord_uid}")
				
				# Trigger immediate completion check to notify all players
				# This ensures both players receive the abort notification
				print(f"[Matchmaker] Triggering immediate completion check for match {match_id} after abort.")
				import asyncio
				asyncio.create_task(match_completion_service.check_match_completion(match_id))
			
			return success
	
	async def _calculate_and_write_mmr(self, match_id: int, match_data: dict) -> int:
		"""
		Helper to calculate and write MMR changes using DataAccessService.
		
		Args:
			match_id: Match ID
			match_data: Fresh match data (use the provided data, don't refetch!)
			
		Returns:
			MMR change amount (positive = player 1 gained)
		"""
		from src.backend.services.data_access_service import DataAccessService
		data_service = DataAccessService()
		
		# Use the provided match_data (don't overwrite with potentially stale data!)
		if not match_data:
			print(f"[Matchmaker] No match data provided for match {match_id}")
			return 0
		
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
						return match_data.get('mmr_change', 0)
				else:
					print(f"[Matchmaker] MMR for match {match_id} has already been calculated. Skipping.")
					return match_data.get('mmr_change', 0)
			except Exception as e:
				print(f"[Matchmaker] Error checking MMR consistency for match {match_id}: {e}")
				# If we can't verify, proceed with calculation
				pass
		
		# Check if both players have reported and if their reports match
		p1_report = match_data.get('player_1_report')
		p2_report = match_data.get('player_2_report')
		
		if p1_report is None or p2_report is None:
			print(f"[Matchmaker] Player report recorded for match {match_id}, waiting for other player")
			return 0
		
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
			return 0

		if match_result == -2:
			print(f"[Matchmaker] Conflicting reports for match {match_id}, manual resolution required")
			return 0
		
		# Both players have reported and reports match - process MMR
		print(f"[Matchmaker] Both players reported for match {match_id}, processing MMR changes")
		
		player1_uid = match_data['player_1_discord_uid']
		player2_uid = match_data['player_2_discord_uid']
		
		# Get the races that were actually played from the match data
		p1_race = match_data.get('player_1_race')
		p2_race = match_data.get('player_2_race')

		# Initialize MMR service (needed for calculations below)
		mmr_service = MMRService()
		
		if p1_race and p2_race:
			# Get complete MMR records from DataAccessService (in-memory, instant)
			# Retrieve all data in one call per player to avoid redundant lookups
			p1_all_mmrs = data_service.get_all_player_mmrs(player1_uid)
			p2_all_mmrs = data_service.get_all_player_mmrs(player2_uid)
			
			# Get current stats for each player's race
			p1_stats = p1_all_mmrs.get(p1_race, {})
			p2_stats = p2_all_mmrs.get(p2_race, {})
			
			# Extract current MMR values
			p1_current_mmr = p1_stats.get('mmr')
			p2_current_mmr = p2_stats.get('mmr')
			
			if p1_current_mmr is not None and p2_current_mmr is not None:
				# Calculate MMR changes
				
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
				
				p1_current_games = p1_stats.get('games_played', 0)
				p1_current_won = p1_stats.get('games_won', 0)
				p1_current_lost = p1_stats.get('games_lost', 0)
				p1_current_drawn = p1_stats.get('games_drawn', 0)
				
				p2_current_games = p2_stats.get('games_played', 0)
				p2_current_won = p2_stats.get('games_won', 0)
				p2_current_lost = p2_stats.get('games_lost', 0)
				p2_current_drawn = p2_stats.get('games_drawn', 0)
				
				# Update both players' MMR using DataAccessService (async, non-blocking)
				await data_service.update_player_mmr(
					player1_uid, p1_race, int(mmr_outcome.player_one_mmr),
					games_played=p1_current_games + 1,  # INCREMENT total games
					games_won=p1_current_won + 1 if p1_won else p1_current_won,
					games_lost=p1_current_lost + 1 if p1_lost else p1_current_lost,
					games_drawn=p1_current_drawn + 1 if p1_drawn else p1_current_drawn
				)
				
				await data_service.update_player_mmr(
					player2_uid, p2_race, int(mmr_outcome.player_two_mmr),
					games_played=p2_current_games + 1,  # INCREMENT total games
					games_won=p2_current_won + 1 if p2_won else p2_current_won,
					games_lost=p2_current_lost + 1 if p2_lost else p2_current_lost,
					games_drawn=p2_current_drawn + 1 if p2_drawn else p2_current_drawn
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
			return 0

	async def is_player_in_queue(self, discord_user_id: int) -> bool:
		"""Check if a player is in the queue."""
		async with self.lock:
			return any(p.discord_user_id == discord_user_id for p in self.players)

	def get_next_matchmaking_time(self) -> int:
		"""
		Get the Unix timestamp of the next matchmaking wave.
		Uses the pre-calculated next_match_time from the run loop for accurate synchronization.
		
		Returns:
			int: Unix timestamp of the next matchmaking wave
		"""
		import math
		
		# If matchmaker is running, use the stored next match time for accuracy
		if self.running and self.next_match_time > time.time():
			return int(self.next_match_time)
		
		# Otherwise, calculate it (fallback for when matchmaker hasn't started)
		now = time.time()
		interval = self.MATCH_INTERVAL_SECONDS
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