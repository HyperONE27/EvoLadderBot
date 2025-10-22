# Fixing the Replay Listener's Webhook Timeout Issue

**Status: ✅ FIXED**

This document outlines the architectural flaw in the replay listener that caused a 401 error on long games and describes the implemented solution.

## The Problem: Expiring Interaction Tokens

The initial assessment correctly identified that using a webhook tied to a Discord interaction is fragile due to the token's 15-minute lifespan. While the system correctly *detects* replays using a persistent `on_message` listener, it incorrectly attempts to *update the UI* using the original, expired interaction.

**The exact flaw is the use of `interaction.edit_original_response()` on an interaction object that may be hours old.**

### Code culprit:

-   **File:** `src/bot/commands/queue_command.py`
-   **Lines:** `2005:2007` and `2023:2025`
-   **Problematic Code:** `await match_view.last_interaction.edit_original_response(...)`

When a game lasts longer than 15 minutes, the `last_interaction` token becomes invalid, causing Discord to return a `401 Unauthorized` or `404 Not Found` error, preventing the UI from updating.

## The Solution: Decouple UI Updates from the Original Interaction

To fix this, we must stop trying to edit the original message after 15 minutes have passed. Instead, the bot should send a **new message** to the user's DM channel to provide updates.

### Step-by-Step Implementation Plan

#### 1. Store the Channel Object, Not the Interaction

The `MatchFoundView` should store the `discord.TextChannel` object (the user's DM channel) instead of the `interaction` object.

-   **In `QueueSearchingView._listen_for_match`:**
    -   Instead of storing `match_view.last_interaction = self.last_interaction`, store the channel object.
    -   Change `643:643:src/bot/commands/queue_command.py` to `match_view.channel = self.last_interaction.channel`.

#### 2. Send New Messages for Updates

In the `on_message` handler, instead of editing the old response, we will send a new message. We also need to keep track of the last-sent message so we can delete it and avoid cluttering the DM channel.

-   **In `MatchFoundView`:**
    -   Add a new property: `self.last_update_message_id: Optional[int] = None`.

-   **In the `on_message` handler in `queue_command.py`:**
    -   Before sending an update, check if `match_view.last_update_message_id` exists. If it does, fetch and delete that message to keep the channel clean.
    -   Replace `await match_view.last_interaction.edit_original_response(...)` with `await match_view.channel.send(...)`.
    -   Store the ID of the new message: `new_message = await match_view.channel.send(...)`, then `match_view.last_update_message_id = new_message.id`.

This logic should be applied in two places:
-   When handling an **invalid replay** (`2000:2007:src/bot/commands/queue_command.py`).
-   When handling a **valid replay** for the immediate UI update (`2012:2026:src/bot/commands/queue_command.py`).

#### 3. Handling Final Match Completion

The same logic applies to the `handle_completion_notification` method in `MatchFoundView`.

-   **In `MatchFoundView.handle_completion_notification`:**
    -   The call to `self.last_interaction.edit_original_response()` at line `1183` is also a source of this bug.
    -   It should be replaced with the same logic: delete the previous update message if it exists, send a new message with the final embed, and store its ID.

### Benefits of this Approach

-   **Robust and Timeout-Proof:** The bot will be able to update the user on the match status no matter how long the game takes.
-   **Clean UI:** By deleting the previous update message before sending a new one, the user's DM channel remains clean and easy to read.
-   **Decoupled Architecture:** This change fully decouples the match lifecycle from the initial interaction, creating a more resilient and reliable system.

## Implementation Summary

The fix has been successfully implemented with the following changes to `src/bot/commands/queue_command.py`:

1. **Added new properties to `MatchFoundView`:**
   - `self.channel`: Stores the Discord channel object for persistent access
   - `self.last_update_message`: Tracks the most recent update message for replacement

2. **Created helper method `_send_or_update_view()`:**
   - Deletes the previous update message (if it exists)
   - Sends a new message with the updated embed and view
   - Returns success/failure status for fallback handling

3. **Updated all UI update locations:**
   - `on_message` handler (invalid replay): Lines 2028-2041
   - `on_message` handler (valid replay): Lines 2052-2066
   - `handle_completion_notification`: Lines 1208-1221
   - `disable_abort_after_delay`: Lines 852-866

4. **Implemented graceful fallback:**
   - First attempts to use the channel-based approach
   - Falls back to the interaction method if within the 15-minute window
   - Suppresses errors gracefully to prevent crashes

The fix ensures that games lasting longer than 15 minutes will continue to receive UI updates without encountering 401 errors.
