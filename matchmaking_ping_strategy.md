# Matchmaking Strategy: Balancing Ping, MMR, and Queue Times

## 1. Executive Summary

This document outlines and analyzes several strategies for incorporating a "ping rating" into the EvoLadderBot matchmaking algorithm. In a global matchmaking system, it is crucial to balance the desire for close MMR matches with the need for a playable connection (low ping). A naive approach can lead to two negative outcomes:
1.  **High-Ping Matches:** Ignoring ping entirely and matching purely on MMR can pair players from opposite sides of the world (e.g., Korea vs. Europe), resulting in a frustrating, unplayable experience for both.
2.  **Rating Islands:** Being too restrictive with ping can prevent players in less-populated regions from ever playing against the broader community, creating isolated rating pools and excessively long queue times.

The ideal solution finds a tunable middle ground, favoring low-ping matches when available but gradually expanding the search to ensure everyone can find a game in a reasonable amount of time. This document analyzes three primary strategies to achieve this balance.

---

## 2. The Core Data: From Cross-Table to Ping Cost

The foundation of any ping-aware system is a numerical representation of connection quality. Your `cross_table.xlsx` is the source of truth, but it must be converted into a machine-readable format and a "ping cost" model.

-   **Server Lookup Table:** First, the cross-table should be converted into a JSON file (`data/misc/server_lookup.json`). This provides a simple lookup: given two player regions, what is the optimal game server?
-   **Ping Cost Matrix:** Second, you must define a numerical "ping cost" for a player from any given region to play on any given server. This is where your "ping rating" comes in. A lower cost is better. This allows the algorithm to quantify how "bad" a server choice is for each player in a potential match.

**Example `ping_costs.json`:**
```json
{
  "costs": {
    "US West": { "NAW": 0, "NAC": 15, "NAE": 30, "EUW": 80, "KRJ": 50 },
    "US Central": { "NAW": 15, "NAC": 0, "NAE": 15, "EUW": 70, "KRJ": 65 },
    "Central EU": { "EUW": 0, "EUE": 5, "NAE": 60, "KRJ": 120 },
    "Korea": { "KRJ": 0, "CHN": 20, "SEA": 40, "NAW": 50, "EUW": 120 }
  }
}
```
The total ping penalty for a match is `cost(Player1_Region -> Server) + cost(Player2_Region -> Server)`.

---

## 3. Alternative Implementation Strategies

Here are three distinct strategies for integrating this ping cost into your matchmaking algorithm.

### Strategy A: The Combined Score (Recommended)

This strategy modifies the core matchmaking logic to find a match that minimizes a weighted combination of MMR difference and ping penalty.

-   **Concept:** `MatchCost = (MMR_Difference * MMR_WEIGHT) + (Ping_Penalty * PING_WEIGHT)`
-   **How it Works:** The `find_matches` function, instead of searching for the opponent with the `best_diff`, would search for the opponent with the lowest `MatchCost`. The weights (`MMR_WEIGHT`, `PING_WEIGHT`) are tunable parameters that allow you to define how much MMR you're willing to sacrifice for a better connection. For example, a `PING_WEIGHT` of `2.0` would mean that every 1 point of ping penalty is equivalent to a 2 MMR difference.

-   **Pros:**
    -   **Extremely Tunable:** This is the most flexible approach. You can easily adjust the weights to respond to community feedback. If queue times are too long, you can lower the `PING_WEIGHT`. If players are complaining about lag, you can increase it.
    -   **Finds the "Holistically Best" Match:** It doesn't create hard boundaries. It can correctly determine that a 100 MMR difference match with a 10 ping penalty is better than a 20 MMR difference match with a 90 ping penalty.
    -   **Avoids Hard Cutoffs:** A player is never strictly "unmatchable" with another due to ping; the match just becomes increasingly "expensive" and less likely to be chosen over a better alternative.

-   **Cons:**
    -   **More Complex Implementation:** Requires modifying the core `find_matches` loop to calculate the new combined score.
    -   **Tuning Can Be Non-Intuitive:** Finding the "perfect" weights may require experimentation and analysis of match data to see what feels right for the players.

### Strategy B: Tiered Geographical Search

This strategy creates concentric search "tiers" based on geography that expand over time.

-   **Concept:** A player's search for an opponent expands through predefined geographical zones as their queue time increases.
-   **How it Works:**
    1.  **Tier 1 (0-45s in queue):** Search for opponents only within your own primary region (e.g., NAW, NAC, NAE only match each other).
    2.  **Tier 2 (45-90s in queue):** Expand search to include secondary regions (e.g., NA players can now match with SAM and EUW).
    3.  **Tier 3 (90s+ in queue):** Expand search to be fully global.

-   **Pros:**
    -   **Simple to Understand & Implement:** The logic is very clear and doesn't require complex scoring. It's a series of filters applied to the potential opponent pool.
    -   **Guarantees Low Ping for Quick Matches:** Players who get matched quickly are guaranteed to have a good connection.

-   **Cons:**
    -   **Creates "Search Cliffs":** A player waiting for 44 seconds cannot see an opponent who has been waiting for 46 seconds if they are in a different tier. This can lead to situations where two perfectly good opponents just miss each other.
    -   **Less Granular:** It treats a match between NAW and NAE (good ping) the same as a match between NAW and EUW (playable, but higher ping), as they might be in the same "tier."
    -   **Can Feel Punishing:** If you are in a low-population region, you are guaranteed to wait the full 90 seconds every single time, which can be a frustrating user experience.

### Strategy C: Dynamic Ping Limit

This strategy is a hybrid approach. It focuses on a "maximum allowed ping penalty" that increases with a player's wait time.

-   **Concept:** A player can only be matched with opponents if their resulting `Ping_Penalty` is below a certain threshold. This threshold increases the longer they wait in the queue.
-   **How it Works:** Similar to the existing `max_diff` for MMR, you would create a `max_ping_penalty(wait_cycles)` function.
    -   `wait_cycles = 0`: `max_ping_penalty` might be 20 (only allowing excellent connections).
    -   `wait_cycles = 1`: `max_ping_penalty` might be 60 (allowing decent cross-region connections).
    -   `wait_cycles = 2+`: `max_ping_penalty` might be 200 (allowing most connections).

-   **Pros:**
    -   **Direct Control Over Match Quality:** You have a very direct way to prevent the worst-quality matches from ever happening.
    -   **Intuitive for Players:** The idea that "the longer I wait, the wider my search becomes" is easy for players to grasp.

-   **Cons:**
    -   **Can Still Strand Players:** If two players are just outside each other's `max_ping_penalty` window, they won't match, even if they are the only two people in the queue.
    -   **Adds a Second Complex Filter:** The algorithm would have to check for both `mmr_diff <= max_diff` AND `ping_penalty <= max_ping_penalty`, which can make finding a valid match harder than the combined score approach.

---

## 4. Key Trade-Offs to Consider

When choosing and tuning your strategy, you must balance these competing priorities.

#### **Match Quality vs. Queue Time**
This is the central conflict. Every decision you make will fall somewhere on this spectrum. The **Combined Score (A)** gives you a slider, while the **Tiered Search (B)** gives you a switch with a few settings. Prioritizing quality (high ping penalty) will inevitably increase the average time a player spends in the queue, especially during off-peak hours.

#### **Rating Islands vs. Global Competition**
This is the most dangerous long-term risk you identified.
-   **The Risk:** If you make the ping penalty too high (or the geographical tiers too strict), players in regions like Oceania or South America may *only* ever be matched against each other. While their games will be low-ping, their MMR will exist in a vacuum. A 5000 MMR player in OCE may not be equivalent to a 5000 MMR player in EU, but the system will treat them as such. This devalues the integrity of a "global" ladder.
-   **Mitigation:** The **Combined Score (A)** is the best tool to mitigate this. It doesn't forbid a KR-EU match; it just makes it less likely. If two such players are the only high-MMR players in the queue, the algorithm will still correctly identify them as the best available match, preventing them from being stranded. A tiered approach, by contrast, could prevent this match from ever happening.

#### **Fairness vs. Player Experience**
Consider two players of equal MMR, one in North America (a high-population region) and one in South America (a lower-population region).
-   The NA player will likely get fast, low-ping matches consistently.
-   The SA player will have to wait longer for the ping/MMR parameters to expand enough to find a suitable opponent, who will likely be in NA, resulting in a higher-ping game.
Is this "fair"? The NA player gets a better experience simply due to geography. This is an unavoidable reality of a global server, but how you tune your algorithm determines *how much* of a disadvantage the SA player has. A heavily weighted ping penalty protects the NA player's experience at the cost of the SA player's queue time. A lower weight helps the SA player find games faster, but at the cost of potentially worse connections for both.

---

## 5. Deeper Analysis: Greedy vs. Globally Optimal Matching

The recommended "Combined Score" strategy is a **greedy algorithm**. It iterates through a prioritized list of players and, for each one, *greedily* selects the best available opponent from the remaining pool based on the `MatchCost`. Once a pair is made, they are removed, and the algorithm moves to the next player. This approach is simple and fast, but it's important to understand the trade-offs compared to a globally optimal solution.

### The Sub-optimality of a Greedy Approach

A greedy algorithm optimizes for the best immediate, local choice. This can sometimes lead to a worse overall outcome for the entire queue.

Consider a queue with four players:
-   **NA1:** 5000 MMR (North America)
-   **NA2:** 4800 MMR (North America)
-   **EU1:** 5010 MMR (Europe)
-   **EU2:** 4810 MMR (Europe)

Let's assume `NA1` has the highest priority and is matched first.

1.  **Greedy Algorithm in Action:**
    -   `NA1` (5000 MMR) looks for an opponent. The MMR difference with `EU1` is only 10, while the difference with `NA2` is 200. Even with a significant ping penalty for the NA-EU match, the tiny MMR gap might make `EU1` the "cheapest" match for `NA1`.
    -   **Result 1:** `NA1` is paired with `EU1` (high ping, great MMR).
    -   This leaves `NA2` and `EU2`, who are then paired together.
    -   **Result 2:** `NA2` is paired with `EU2` (high ping, great MMR).
    -   **Overall Outcome:** Two matches are made, but both have high latency. The system is functional, but the player experience is poor for everyone.

2.  **A Globally Optimal Solution:**
    -   A global algorithm would evaluate all possible pairings in the entire queue and choose the set of pairs that minimizes the *total combined `MatchCost`* of all matches.
    -   It would calculate the cost of the `(NA1, EU1)` + `(NA2, EU2)` scenario.
    -   It would also calculate the cost of the `(NA1, NA2)` + `(EU1, EU2)` scenario.
    -   Because the ping penalty for cross-region play is high, the second scenario's total cost would be much lower, even with slightly worse MMR differences.
    -   **Overall Outcome:** The algorithm would create two zero-ping matches, dramatically improving the experience for all four players at the cost of slightly less "perfect" MMR pairings.

### The Case for the Greedy Algorithm

If a global algorithm produces a better result, why not use it? The answer lies in complexity, fairness, and the nature of the problem itself.

| Aspect | Greedy Algorithm (Recommended) | Globally Optimal Algorithm |
| :--- | :--- | :--- |
| **Complexity** | **Low.** Computationally fast (approx. O(n²)). Easy to implement and debug. | **High.** Requires complex algorithms (e.g., min-cost max-flow on a bipartite graph), which are much slower (O(n³ or more)). Can become a performance bottleneck with large queues. |
| **Individual Fairness** | **High.** The highest-priority player in the queue is *guaranteed* to get the best possible match available to them at that moment. The system is transparently "fair" to the individual. | **Low.** Can feel "unfair" to individuals. A player might be forced to take a worse match (for them) in order to enable a better overall outcome for the system. This "sacrificial matchmaking" can be frustrating if you're the one sacrificed. |
| **Rating Islands** | **Mitigated via Weights.** The main tool to combat rating islands is to tune the `PING_WEIGHT`. By ensuring the MMR component can eventually overpower the ping component, you allow cross-region play. | **Exacerbated by Ping Focus.** A global optimizer, tasked with minimizing total ping, will be *even more aggressive* about creating regional pairings. It will strongly resist making any cross-region match if a same-region alternative exists, thus creating the very rating islands you want to avoid. |

### Conclusion on Algorithm Choice

The "rating island" problem is not primarily a consequence of a greedy vs. global algorithm; it's a consequence of **over-weighting ping relative to MMR**.

-   A greedy algorithm that heavily penalizes ping will create islands.
-   A global algorithm that heavily penalizes ping will create islands *even more efficiently*.

Therefore, the **Greedy Algorithm with a Combined Score remains the superior pragmatic choice.** It is computationally feasible, feels "fair" to the individual player, and most importantly, gives you the necessary control via the `MMR_WEIGHT` and `PING_WEIGHT` parameters. Your primary focus should be on tuning these weights to strike the right balance, not on implementing a more complex matching algorithm. The goal is not to find the mathematically perfect set of matches in a vacuum, but to create a system that feels fair and consistently produces good-quality games for its users.

---
## 6. Advanced Tuning: Dynamic Weights and Edge Case Handling

You've correctly identified a potential weakness in the "Combined Score" strategy: a single, static `PING_WEIGHT` is a blunt instrument. While it helps on average, it may not behave optimally under specific edge-case conditions, such as very low or very high queue populations, or when a player has been waiting for an unusually long time.

To address this, the system can be evolved to use **dynamic weights** and **hard limits**, moving beyond the hope of a single "optimal" value to a system that adapts to the current state of the queue.

### Dynamic Weight Adjustment

Instead of being constants, the `MMR_WEIGHT` and `PING_WEIGHT` can be functions that adjust based on real-time queue metrics. This allows the matchmaker to be more lenient when it needs to be and stricter when it can afford to be.

#### Key Inputs for Dynamic Adjustment:

1.  **Individual Player Wait Time:** This is the most important factor for fairness. A player who has been waiting longer should have their search gradually broadened. You can achieve this by making the `PING_WEIGHT` effectively *lower* for players who have been in the queue for multiple cycles.

    *   **Concept:** `effective_ping_weight = BASE_PING_WEIGHT / (1 + player.wait_cycles * WAIT_TIME_FACTOR)`
    *   **Effect:** For a player in their first search cycle, the ping penalty is at its maximum. After a few minutes (several `wait_cycles`), their `effective_ping_weight` drops, making the algorithm more willing to accept a higher-ping match to get them out of the queue. This directly prevents players in low-population regions from getting stranded indefinitely.

2.  **Overall Queue Population:** The total number of players searching for a game should influence the system's strictness.

    *   **Concept:**
        *   If `len(queue) < 10`: The system is in a "low population" state. The global `PING_WEIGHT` can be temporarily reduced to prioritize making *any* matches, even if they are cross-region.
        *   If `len(queue) > 50`: The system is in a "high population" state. The global `PING_WEIGHT` can be temporarily increased, as there are likely plenty of low-ping, same-region opponents available. The system can afford to be pickier.

### The High-Ping Veto: A Safety Net

Even with dynamic weighting, some pairings are simply unplayable (e.g., South Africa vs. Australia). A dynamic system might theoretically still make this match if two players with absurdly high MMR were the only ones in the queue for a very long time.

To prevent this, you can implement a hard limit, or a "High-Ping Veto."

-   **Concept:** `if ping_penalty(player1, player2) > MAX_ACCEPTABLE_PENALTY: continue`
-   **How it Works:** Before calculating the `MatchCost`, the algorithm would first perform a simple check. If the raw ping penalty for a potential match exceeds a predefined "unplayable" threshold, that pairing is immediately discarded, regardless of how good the MMR is. This acts as a crucial safety net to prevent the algorithm from creating the worst-possible user experiences, providing a hard boundary that the dynamic weighting operates within.

### Revisiting the Trade-Offs with a Dynamic System

This more sophisticated model gives you a set of interacting levers rather than a single knob, providing much more granular control over the trade-offs:

-   **Match Quality vs. Queue Time:** You are no longer making a single, global trade-off. The `High-Ping Veto` sets your absolute minimum standard for match quality. The dynamic weighting based on **queue population** adjusts the "average" trade-off for everyone, while the weighting based on **player wait time** creates a personalized trade-off that becomes more lenient over time for individuals.
-   **Rating Islands:** The dynamic reduction of `PING_WEIGHT` based on wait time is the most powerful tool against rating islands. It ensures that while the system *prefers* to keep regions separate when populated, it will always reach across boundaries to find games for isolated players, explicitly preventing them from being permanently stranded.

By combining a baseline **Combined Score** with **Dynamic Weight Adjustment** and a **High-Ping Veto**, you create a multi-layered system that handles both the macro behavior (favoring low ping on average) and the critical edge cases (ensuring long-waiting players and sparse queues can still function).

---

## 7. Further Questions & Unresolved Concerns to Consider

Before finalizing the implementation, here are several additional points to mull over. These focus less on the core algorithm and more on the second-order effects related to player behavior, perception, and long-term system health.

#### **On Player Psychology and Perception:**
*   **Transparency vs. "Magic":** How much of the matchmaking logic should be exposed to the players? If they know the exact weights for MMR and ping, will they complain that the tuning is "wrong"? Or is it better for the system to be a "black box" that simply aims to produce good matches, with the details hidden?
*   **The "Feels Bad" Match:** What is the protocol for when the algorithm produces a match that is technically optimal but *feels* bad to the players? For example, Player A is forced to take a 150ms ping match against Player B because it was a 50 MMR difference, when a 50ms ping match against Player C with a 150 MMR difference was also available. How do you justify the "correct" choice to the players involved?
*   **Sacrificial Lambs:** In a globally optimal system (which you've opted against, for good reason), a player might be given a sub-optimal match for themselves to improve the overall quality of matches for everyone else. Does any element of this exist in the greedy model? Could a player feel like they are consistently getting the "short end of the stick" for the health of the queue?

#### **On System Exploitability:**
*   **Region Dodging:** If a player's region is a simple setting, what prevents a high-level EU player from setting their region to "NAW" to avoid the competitive EU queue at peak time? This implies a need to either lock the region setting or have some form of soft verification.
*   **Gaming the Weights:** If players understand how the weights change over time, could a high-MMR player abuse the system? For example, by queueing at a very specific time, they might know the system will become desperate after 90 seconds and be more likely to serve them a much lower-MMR opponent from a different region—an easy win, despite the lag.

#### **On Data, Tooling, and Maintenance:**
*   **What to Log?** To tune the dynamic weights effectively, what data do you need? At a minimum, every match record should probably include not just the final MMRs and server, but the `wait_cycles` of each player and the final `ping_penalty` score of the match.
*   **Is Simulation Necessary?** Rather than tuning the weights on the live player base, would it be worth building a discrete-event simulation? You could take a snapshot of the entire `players` table, run thousands of simulated matchmaking cycles with different weight settings, and analyze the statistical outcomes (e.g., average wait time, average ping penalty, % of cross-region matches) to find the best starting values.

#### **On Long-Term Evolution:**
*   **Population Changes:** How should the dynamic weights adapt if the player base doubles, or if it shrinks by half? A system tuned for 200 concurrent players might behave poorly with 20. Does the algorithm need a meta-layer that adjusts the *rate of change* of the dynamic weights based on the total active player population?
*   **The "Both Games" Problem:** The current logic separates players into BW-only, SC2-only, and Both. The ping penalty adds another dimension. How does this affect the `equalize_lists` function? Will players who queue for both games be more likely to get high-ping matches, as they are used to fill gaps in either pool? Does their flexibility work against them in terms of match quality?