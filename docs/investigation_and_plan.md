# Investigation & Refactoring Plan: Interaction Handling

## 1. Executive Summary

A recent regression introduced an `AttributeError: 'MatchFoundView' object has no attribute 'last_interaction'` error, causing UI updates for aborted matches to fail. This investigation traced the root cause to an incomplete refactoring (commit `0e3ee10`) that removed the `last_interaction` attribute from `MatchFoundView` but failed to update all code paths that relied on it.

Further analysis revealed that this was not an isolated issue. The codebase contains several outdated or incorrect patterns for handling Discord interactions, leading to race conditions, timeouts, and inconsistent UI updates.

This document outlines the identified problems and presents a methodical plan to refactor the `queue` and `prune` commands to use a robust, production-grade architecture.

---

## 2. Root Cause Analysis: The Regression

-   **Commit:** `0e3ee10` ("changed interaction token edits to bot token + channel-message id based edits")
-   **Intent:** To solve a webhook timeout issue by moving from temporary interaction tokens to a more persistent `message.edit()` pattern using stored channel and message IDs.
-   **The Flaw:** The refactoring was incomplete. It successfully removed the `last_interaction` attribute from `MatchFoundView` but **missed updating the `handle_completion_notification` method for `abort` statuses.** This legacy code was left trying to access an attribute that no longer existed, causing the crash.
-   **Key Takeaway:** The architectural direction of the commit was correct, but its partial implementation created the regression.

---

## 3. Broader Architectural Problems Identified

Our investigation uncovered that the regression was a symptom of wider architectural inconsistencies in how interactions are handled.

### Problem A: Incomplete Refactoring in `queue_command.py`

The `last_interaction` bug is not limited to aborts. The same outdated pattern exists for **all** match completion notifications, meaning users would not receive final UI updates for completed matches or result conflicts either.

-   **Evidence (`_send_final_notification_embed`):** Still checks for `if not self.last_interaction:`, which will always be true, preventing the "Match Result Finalized" message.
-   **Evidence (`_send_conflict_notification_embed`):** Also checks for `self.last_interaction`, preventing the "Match Result Conflict" message.

### Problem B: Asymmetrical UI Updates in Abort Flow

As you correctly pointed out, even if the `last_interaction` attribute were fixed, the current logic is flawed. When one player aborts a match, **only their UI is updated.** The other player receives the backend notification but their `MatchFoundView` has no recent `interaction` object to use, so their UI remains stale until they try to interact with it. This creates a confusing and inconsistent user experience.

### Problem C: Architectural Race Condition in `prune_command.py`

The `prune` command has a fundamental design flaw that violates Discord's 3-second acknowledgment rule.

-   **The Flaw:** It performs a slow, multi-second I/O operation (fetching message history from Discord's API) *before* sending its initial response.
-   **The Result:** If message fetching takes longer than 3 seconds, the interaction token expires, and the bot's attempt to respond fails with an `Unknown Webhook` error. This is a classic race condition.
-   **Your Insight:** You are correct that we must send an initial, temporary embed immediately. The `prune` command is unique because it cannot show the user any meaningful data until it receives information back from Discord. Therefore, the correct flow is:
    1.  Send an immediate "Analyzing messages..." embed with disabled buttons.
    2.  Asynchronously fetch and analyze the message history.
    3.  Update the initial message with the final confirmation prompt and enable the buttons.

---

## 4. The Refactoring Plan: A Unified, Robust Architecture

The goal is to refactor both `queue_command.py` and `prune_command.py` to adhere to modern, robust interaction handling patterns.

### Phase 1: Fix `prune_command.py` with Immediate Deferral

This is the most straightforward fix and will be addressed first.

1.  **Modify `prune_command`**:
    -   Immediately upon receiving the interaction, send a "placeholder" embed (e.g., "🗑️ Analyzing Messages...") with disabled buttons. This will use `interaction.response.send_message()`.
    -   Fetch and analyze the channel history asynchronously.
    -   Once the analysis is complete, use `interaction.edit_original_response()` to update the placeholder embed with the real confirmation prompt and enable the buttons.

### Phase 2: Implement a Persistent, ID-Based Tracking System for `queue_command.py`

This is the core architectural change to fix all issues related to `last_interaction`.

1.  **Capture Message Context**:
    -   In `JoinQueueButton.callback`, after sending the initial "Searching..." view, we will use `interaction.original_response()` to get the `discord.Message` object.
    -   The `message.id` and `message.channel.id` will be stored on the `QueueSearchingView`.

2.  **Propagate Context to `MatchFoundView`**:
    -   When `_listen_for_match` creates a `MatchFoundView`, it will pass the `message_id` and `channel_id` into its constructor.
    -   The `MatchFoundView` will store these IDs, completely removing any need for a `last_interaction` attribute.

3.  **Centralize Updates with a Bot-Token Helper**:
    -   The existing `_edit_original_message` helper in `MatchFoundView` is the correct pattern. It uses the stored IDs and the bot's permanent token to reliably fetch and edit the message.
    -   **Crucially, this method will be used for ALL asynchronous UI updates**, including those for the other player in an abort scenario.

### Phase 3: Fix Asymmetrical UI Updates & Unify Backend-Initiated Flows

This phase ensures all players in a match receive timely UI updates, regardless of who initiated the action, and unifies all backend-driven updates under a single, robust pattern.

1.  **Unify Backend Notifications**:
    -   The `matchmaker` currently uses different notification mechanisms for different outcomes. This will be standardized. All match-terminating events (`abort`, `complete`, `conflict`) will be published as global notifications via the `notification_service`. This creates a single, predictable channel for all final-state updates.

2.  **Update `MatchFoundView` to Handle Unified Events**:
    -   The `MatchFoundView` for **both** players already listens for backend notifications. Its `handle_completion_notification` method will be confirmed to handle all terminal states (`abort`, `complete`, `conflict`) identically.
    -   When any of these events are received, the handler will reliably call `self._edit_original_message()` to update its UI.
    -   **Architectural Principle**: There is no "abort flow" that is distinct from the "completion flow" or "conflict flow" at the UI update level. They are all parallel outcomes processed by the same event handler, guaranteeing that both players see the final match state consistently and simultaneously.

By executing this plan, we will eliminate the regression, fix the underlying architectural flaws, and create a more stable, responsive, and consistent user experience.
