#!/usr/bin/env python3
"""
Offline EvoLadder matchmaking simulator
---------------------------------------
• No database or Discord calls
• Simulates multiple waves (wait_cycles increases each round)
• Shows when elastic MMR window expands enough to form a match
"""

import asyncio
import time
from src.backend.core import config
from src.backend.services.matchmaking_service import Player, QueuePreferences


class DebugMatchmaker:
    def __init__(self, players=None):
        self.players = players or []
        self.recent_activity = {}
        self.wave = 0

    # ---------------- LOGIC COPIES ----------------

    def _calculate_queue_pressure(self, queue_size, effective_pop):
        if effective_pop <= 0:
            return 0.0
        if effective_pop <= config.MM_POPULATION_THRESHOLD_LOW:
            scale = config.MM_PRESSURE_SCALE_LOW_POP
        elif effective_pop <= config.MM_POPULATION_THRESHOLD_MID:
            scale = config.MM_PRESSURE_SCALE_MID_POP
        else:
            scale = config.MM_PRESSURE_SCALE_HIGH_POP
        return min(1.0, (scale * queue_size) / effective_pop)

    def max_diff(self, wait_cycles):
        queue_size = len(self.players)
        effective_pop = len(self.recent_activity) or len(self.players)
        if effective_pop == 0:
            base, growth = config.MM_DEFAULT_PARAMS
        else:
            pressure = self._calculate_queue_pressure(queue_size, effective_pop)
            if pressure >= config.MM_HIGH_PRESSURE_THRESHOLD:
                base, growth = config.MM_HIGH_PRESSURE_PARAMS
            elif pressure >= config.MM_MODERATE_PRESSURE_THRESHOLD:
                base, growth = config.MM_MODERATE_PRESSURE_PARAMS
            else:
                base, growth = config.MM_LOW_PRESSURE_PARAMS
        return base + (wait_cycles // config.MM_MMR_EXPANSION_STEP) * growth

    def categorize_players(self, players):
        bw_only, sc2_only, both = [], [], []
        for p in players:
            if p.has_bw_race and not p.has_sc2_race:
                bw_only.append(p)
            elif p.has_sc2_race and not p.has_bw_race:
                sc2_only.append(p)
            elif p.has_bw_race and p.has_sc2_race:
                both.append(p)
        return bw_only, sc2_only, both

    def _filter_by_priority(self, lead, follow):
        if len(lead) == len(follow):
            return lead, follow
        if len(lead) > len(follow):
            lead = sorted(lead, key=lambda p: p.wait_cycles, reverse=True)[: len(follow)]
        else:
            follow = sorted(follow, key=lambda p: p.wait_cycles, reverse=True)[: len(lead)]
        return lead, follow

    def _build_candidate_pairs(self, lead, follow, is_bw_match):
        candidates = []
        for p1 in lead:
            m1 = p1.get_effective_mmr(is_bw_match) or 0
            max_d = self.max_diff(p1.wait_cycles)
            for p2 in follow:
                m2 = p2.get_effective_mmr(not is_bw_match) or 0
                diff = abs(m1 - m2)
                if diff <= max_d:
                    score = (diff**2) - (
                        (p1.wait_cycles + p2.wait_cycles)
                        * config.MM_WAIT_CYCLE_PRIORITY_COEFFICIENT
                    )
                    candidates.append((score, p1, p2, diff))
        return candidates

    def _select_matches_from_candidates(self, candidates):
        matches, used_a, used_b = [], set(), set()
        for score, p1, p2, diff in sorted(candidates, key=lambda x: x[0]):
            if p1.discord_user_id not in used_a and p2.discord_user_id not in used_b:
                matches.append((p1, p2))
                used_a.add(p1.discord_user_id)
                used_b.add(p2.discord_user_id)
        return matches

    # ---------------- MAIN LOOP ----------------

    async def run(self, waves=10, interval=1.5):
        """Run multiple matchmaking waves."""
        print(f"=== CONFIG === base/growth: {config.MM_LOW_PRESSURE_PARAMS}, expansion step={config.MM_MMR_EXPANSION_STEP}\n")

        for wave in range(1, waves + 1):
            self.wave = wave
            print(f"\n=== WAVE {wave} ===")
            for p in self.players:
                p.wait_cycles += 1
                self.recent_activity[p.discord_user_id] = time.time()
                print(
                    f"{p.user_id}: wait={p.wait_cycles}, eff_mmr={p.get_effective_mmr(p.has_bw_race)}, max_diff={self.max_diff(p.wait_cycles)}"
                )

            bw_only, sc2_only, both = self.categorize_players(self.players)
            if not bw_only or not sc2_only:
                print("❌ Need at least one BW and one SC2 player to match.")
                await asyncio.sleep(interval)
                continue

            lead, follow, is_bw = (bw_only, sc2_only, True) if len(bw_only) <= len(sc2_only) else (sc2_only, bw_only, False)
            lead, follow = self._filter_by_priority(lead, follow)
            candidates = self._build_candidate_pairs(lead, follow, is_bw)
            print(f"🔍 Candidates: {len(candidates)}")

            if not candidates:
                print("❌ No valid matches within MMR window yet")
                await asyncio.sleep(interval)
                continue

            matches = self._select_matches_from_candidates(candidates)
            if not matches:
                print("❌ No matches formed")
                await asyncio.sleep(interval)
                continue

            print(f"✅ Found {len(matches)} match(es):")
            for a, b in matches:
                ma, mb = a.get_effective_mmr(is_bw), b.get_effective_mmr(not is_bw)
                print(f"   • {a.user_id} ({ma}) vs {b.user_id} ({mb})  Δ={abs(ma - mb)}")

            print("🎉 Match triggered! Stopping simulation.\n")
            break

            await asyncio.sleep(interval)


# ---------------- PLAYER HELPERS ----------------

def make_player(uid, race, mmr):
    prefs = QueuePreferences(
        selected_races=[race],
        vetoed_maps=[],
        discord_user_id=uid,
        user_id=f"Player{uid}",
    )
    return Player(
        discord_user_id=uid,
        user_id=f"Player{uid}",
        preferences=prefs,
        bw_mmr=mmr if race.startswith("bw_") else None,
        sc2_mmr=mmr if race.startswith("sc2_") else None,
    )


# ---------------- DRIVER ----------------

async def main():
    mm = DebugMatchmaker()
    mm.players = [
        make_player(1, "bw_zerg", 1500),
        make_player(2, "sc2_protoss", 1650),
    ]
    await mm.run(waves=12, interval=0.8)


if __name__ == "__main__":
    asyncio.run(main())
