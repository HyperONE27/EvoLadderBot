# Analysis: `GLOBAL_TIMEOUT` and View Lifecycles

This document provides a comprehensive analysis of how `GLOBAL_TIMEOUT` interacts with every `discord.ui.View` in the codebase. It addresses the core architectural pattern where new views are created on interaction and evaluates the impact on each command flow.

## 1. Core Concepts

### `GLOBAL_TIMEOUT`
This is a server-wide setting (e.g., 3600 seconds / 1 hour) that defines the default lifespan for a `discord.ui.View`. After this timeout expires, the components on the view (buttons, dropdowns) become disabled, and the `on_timeout` method is called on the view object in our bot, signaling that it should be cleaned up.

### View Interaction Patterns
Our codebase uses two distinct patterns for handling view interactions:

1.  **Stateless / Re-creation Pattern:** When a user interacts with a component, the callback method creates an entirely **new view instance** and sends it back to the user, replacing the old one. This new view gets its own fresh timeout timer.
2.  **Stateful / Self-Mutating Pattern:** When a user interacts, the callback method modifies the properties of the **existing view instance** (e.g., `self.selected_option = ...`) and then edits the message to re-render the same view object with its new state. The original timeout timer continues to count down.

---

## 2. Analysis of Views by Command

I have categorized each view by the pattern it uses and analyzed the implications.

### `/leaderboard` - `LeaderboardView`

-   **Pattern:** Stateless / Re-creation
-   **Behavior:** As we discussed, every time you filter, change pages, or clear filters, the `update_view` method is called. This method explicitly creates a `new_view = LeaderboardView(...)` and sends it as a replacement.
-   **Impact:**
    -   **Timeout Resets on Every Click:** This is why you can interact with it for over an hour. The timeout only applies to periods of inactivity.
    -   **Memory Safe:** The old view is correctly garbage collected.
    -   **Intended Impact:** This is the **correct and intended** behavior for a complex, multi-state interface. It ensures the view doesn't frustratingly time out while a user is actively exploring the data. There are no negative unintended impacts here.

### `/setup` - `UnifiedSetupView`

-   **Pattern:** Stateless / Re-creation
-   **Behavior:** This view is even more complex than the leaderboard. When you select a country or region from a dropdown, its `callback` calls `self.view.update_view(interaction)`. This `update_view` method works identically to the leaderboard's: it creates a `new_view = UnifiedSetupView(...)` with the updated selections and replaces the old one.
-   **Impact:**
    -   **Timeout Resets on Every Click:** Just like the leaderboard, the setup process won't time out as long as the user is actively selecting their options.
    -   **Intended Impact:** This is also the **correct and intended** behavior. A user might take several minutes to find their country and region, and the view should not expire during this process.

### `/queue` - `QueueView`, `QueueSearchingView`, and `MatchFoundView`

This command has a more complex, multi-stage flow with different patterns.

#### `QueueView` (Race & Veto Selection)

-   **Pattern:** Stateful / Self-Mutating
-   **Behavior:** When you select a race or veto a map, the select menu's `callback` simply modifies the state on the *existing* view object (e.g., `self.view.selected_bw_race = self.values[0]`). It then calls `interaction.response.edit_message(view=self.view)`, re-rendering the *same* view instance.
-   **Impact:**
    -   **Timeout is Persistent:** The `GLOBAL_TIMEOUT` starts counting down the moment the `/queue` command is used. It does **not** reset when you change your selections.
    -   **Intended Impact:** This is appropriate. The queue setup is a quick action. A user has a fixed amount of time (1 hour) to make their selections and hit "Join Queue." If they walk away for an hour, the view should rightly expire.

#### `QueueSearchingView` (The "Searching..." Screen)

-   **Pattern:** Stateful / Self-Mutating
-   **Behavior:** This view is created when you join the queue. It has its own `GLOBAL_TIMEOUT`. It persists until either a match is found or the user cancels.
-   **Impact:**
    -   **Timeout is Persistent:** The timeout starts when the search begins.
    -   **Unintended Impact (Potential Bug):** The `on_timeout` method for this view is not implemented. If a user enters the queue and no match is found for the duration of `GLOBAL_TIMEOUT` (1 hour), the view will expire, the buttons will become disabled, but the bot **will not automatically remove the player from the matchmaking queue in the backend**. The user will be in a "ghost queue" state—no longer able to cancel via the UI but still considered active by the matchmaker.

#### `MatchFoundView` (The Match View)

-   **Pattern:** Stateful / Self-Mutating (with a twist)
-   **Behavior:** This view is stateful and is designed to be very long-lived. Crucially, it is initialized with `super().__init__(timeout=None)`.
-   **Impact:**
    -   **No Timeout:** Setting `timeout=None` explicitly disables the timeout entirely. The buttons on this view will **never** automatically expire.
    -   **Intended Impact:** This is the correct behavior. A match can last for a very long time, and players need to be able to report the result or upload a replay whenever it finishes. The view's lifecycle is managed manually by the match completion logic, not by a timer.

---

## 3. Summary of Findings

Your understanding is correct: every time a new view instance is created, it gets a fresh timeout timer.

-   For the **Leaderboard** and **Setup** commands, this is an intentional and beneficial design pattern that prevents the UI from expiring while a user is actively engaged. It has no negative unintended consequences.
-   For the **Queue** command flow, the views are stateful, and the timeout is persistent. This has revealed a **potential bug**:
    -   **A player can get stuck in the matchmaking queue if the `QueueSearchingView` times out before a match is found.** The user's UI will expire, but they will remain in the backend queue, unable to leave.

This analysis confirms that while the timeout-resetting behavior is intended and safe for some commands, we need to address the timeout handling in the `QueueSearchingView` to prevent users from getting into a broken state.
