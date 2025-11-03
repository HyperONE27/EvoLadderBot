# Match Notifications and Moderation Enhancements

## Overview
Implement six new features to improve match flow efficiency, user education, moderation capabilities, and admin tooling while conserving Discord API budget.

## 1. Deactivate Searching View on Match Found

**Goal**: Stop updating the "Searching..." view when a match is found to save API calls.

**Changes to `src/bot/commands/queue_command.py`**:

In `QueueSearchingView._listen_for_match()`:
- Remove the entire "Match Found!" confirmation embed edit (currently lines 681-692)
- The code sends match notification via `queue_channel_send()` which returns a `discord.Message` object with the message ID
- CRITICAL: Only deactivate AFTER the message is successfully sent and we have the message ID
- Flow: Remove "Match Found!" edit → send match notification → capture message ID → deactivate view → unregister

**Code to remove:**
```python
confirmation_embed = discord.Embed(
    title="🎉 Match Found!",
    description=f"Your match is ready. Full details below.",
    color=discord.Color.green()
)

await queue_edit_original(
    self.last_interaction,
    content=None,
    embed=confirmation_embed,
    view=None
)
flow.checkpoint("searching_message_edited")
```

Keep the rest intact:
1. Creates MatchFoundView
2. Generates match embed
3. Sends new match message via `queue_channel_send()` (returns message ID)
4. Captures message ID in `match_view.original_message_id`
5. Registers for replay detection
6. Unregisters from queue_searching_view_manager (this deactivates the view)

## 2. Shield Battery Bug Notification

**Goal**: Educate new players about the shield battery bug 15 seconds after their first match, IF one of the races is Brood War Protoss.

### Database Schema Changes

**File: `docs/schemas/postgres_schema.md`**

Add after `player_state` (currently line 26):
```sql
shield_battery_bug      BOOLEAN DEFAULT FALSE,
```

**File: `src/backend/db/create_table.py`**

Add after `player_state` (currently line 55):
```python
shield_battery_bug      INTEGER DEFAULT 0,
```

### Data Access Layer

**File: `src/backend/services/data_access_service.py`**:

1. Add to empty DataFrame schema (in `_load_all_tables()` method, after `"player_state"` at line 187):
```python
"shield_battery_bug": pl.Series([], dtype=pl.Boolean),
```

2. Add to `WriteJobType` enum (after `UPDATE_PLAYER_STATE` currently at line 56):
```python
UPDATE_SHIELD_BATTERY_BUG = "update_shield_battery_bug"
```

3. Add methods after `set_player_state()`:
```python
def get_shield_battery_bug(self, discord_uid: int) -> bool:
    """Get whether player has acknowledged the shield battery bug."""
    if self._players_df is None or len(self._players_df) == 0:
        return False
    
    # Handle missing column (defensive)
    if "shield_battery_bug" not in self._players_df.columns:
        return False
    
    player_row = self._players_df.filter(pl.col("discord_uid") == discord_uid)
    if len(player_row) == 0:
        return False
    
    return player_row["shield_battery_bug"][0]

async def set_shield_battery_bug(self, discord_uid: int, value: bool) -> bool:
    """Set whether player has acknowledged the shield battery bug."""
    if self._players_df is None:
        return False
    
    # Update in-memory DataFrame
    mask = pl.col("discord_uid") == discord_uid
    self._players_df = self._players_df.with_columns(
        pl.when(mask).then(pl.lit(value)).otherwise(pl.col("shield_battery_bug")).alias("shield_battery_bug")
    )
    
    # Queue async database write
    await self._queue_write_job(WriteJobType.UPDATE_SHIELD_BATTERY_BUG, {
        "discord_uid": discord_uid,
        "value": value
    })
    
    return True
```

4. Add handler in `_process_write_job()` after UPDATE_PLAYER_STATE handler:
```python
elif job.job_type == WriteJobType.UPDATE_SHIELD_BATTERY_BUG:
    self._db_writer.update_shield_battery_bug(
        job.data["discord_uid"],
        job.data["value"]
    )
```

5. Add to `create_player()` new_row DataFrame:
```python
"shield_battery_bug": [False],
```

**File: `src/backend/db/db_reader_writer.py`**:

Add method after `update_player_state()`:
```python
def update_shield_battery_bug(self, discord_uid: int, value: bool) -> bool:
    """Update shield battery bug acknowledgement in database."""
    query = "UPDATE players SET shield_battery_bug = :value WHERE discord_uid = :discord_uid"
    params = {"discord_uid": discord_uid, "value": value}
    self._cursor.execute(query, params)
    self._connection.commit()
    return True
```

### UI Component

**File: `src/bot/components/shield_battery_bug_embed.py`** (NEW):
```python
import discord
from src.backend.services.app_context import data_access_service
from src.bot.utils.message_helpers import queue_interaction_edit
from src.bot.config import GLOBAL_TIMEOUT


class ShieldBatteryBugView(discord.ui.View):
    """View for the shield battery bug notification."""
    
    def __init__(self, discord_uid: int):
        super().__init__(timeout=GLOBAL_TIMEOUT)
        self.discord_uid = discord_uid
        
        # Add the confirm button
        self.add_item(ShieldBatteryBugButton(self))


class ShieldBatteryBugButton(discord.ui.Button):
    """Button to acknowledge the shield battery bug warning."""
    
    def __init__(self, parent_view: ShieldBatteryBugView):
        super().__init__(
            label="I Understand",
            style=discord.ButtonStyle.success,
            emoji="✅",
            row=0
        )
        self.parent_view = parent_view
    
    async def callback(self, interaction: discord.Interaction):
        """Handle button click - uses interaction queue for immediate response."""
        # Update button to acknowledged state
        self.disabled = True
        self.style = discord.ButtonStyle.secondary
        self.label = "Acknowledged"
        
        # Update in database
        await data_access_service.set_shield_battery_bug(self.parent_view.discord_uid, True)
        
        # Get current embed and add confirmation field
        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            embed.add_field(
                name="✅ Acknowledged",
                value=f"<@{self.parent_view.discord_uid}> has acknowledged this information.",
                inline=False
            )
        
        # Update the message using interaction queue (high priority)
        await queue_interaction_edit(interaction, embed=embed, view=self.parent_view)


def create_shield_battery_bug_embed() -> discord.Embed:
    """Create the shield battery bug notification embed."""
    embed = discord.Embed(
        title="⚠️ Shield Battery Bug",
        description="Placeholder description about the shield battery bug.",
        color=discord.Color.orange()
    )
    return embed
```

### Match Notification Integration

**File: `src/bot/commands/queue_command.py`**:

In `_listen_for_match()` after sending the match notification (after `new_match_message = await queue_channel_send(...)`):

```python
# Schedule shield battery bug notification if needed (only for BW Protoss matches)
asyncio.create_task(self._send_shield_battery_notification(
    match_result.match_id,
    self.channel,
    match_result.player_1_race,
    match_result.player_2_race
))
```

Add new method after `_listen_for_match()`:

```python
async def _send_shield_battery_notification(
    self,
    match_id: int,
    channel,
    player_1_race: str,
    player_2_race: str
):
    """Send shield battery bug notification 15 seconds after match if player hasn't seen it and match has BW Protoss."""
    from src.backend.services.app_context import data_access_service
    from src.bot.components.shield_battery_bug_embed import create_shield_battery_bug_embed, ShieldBatteryBugView
    
    # Wait 15 seconds
    await asyncio.sleep(15)
    
    # Check if match is still active (not completed/aborted)
    match_data = data_access_service.get_match(match_id)
    if not match_data:
        return  # Match not found
    
    match_result = match_data.get('match_result')
    if match_result is not None:
        # Match is already terminal (completed or aborted)
        return
    
    # Check if player has already acknowledged
    has_acknowledged = data_access_service.get_shield_battery_bug(self.player.discord_user_id)
    if has_acknowledged:
        return
    
    # Check if either race is BW Protoss
    if player_1_race != "bw_protoss" and player_2_race != "bw_protoss":
        return  # No BW Protoss in this match
    
    # Send notification (use notification queue for background message)
    embed = create_shield_battery_bug_embed()
    view = ShieldBatteryBugView(self.player.discord_user_id)
    await queue_channel_send(channel, embed=embed, view=view)
```

## 3. Match Confirmation Reminder

**Goal**: Remind players at 1/3 of the abort timer if they haven't confirmed yet.

**File: `src/bot/commands/queue_command.py`**:

In `_listen_for_match()` after sending the match notification:

```python
# Schedule confirmation reminder
asyncio.create_task(self._send_confirmation_reminder(match_result.match_id, self.channel))
```

Add new method after `_send_shield_battery_notification()`:

```python
async def _send_confirmation_reminder(self, match_id: int, channel):
    """Send match confirmation reminder at 1/3 of abort timer if player hasn't confirmed."""
    from src.backend.services.app_context import matchmaker, match_completion_service, data_access_service
    
    # Calculate reminder time (1/3 of abort timer = 60 seconds for default 180s)
    reminder_time = matchmaker.ABORT_TIMER_SECONDS / 3
    
    # Wait for the reminder time
    await asyncio.sleep(reminder_time)
    
    # Check if match is still active (not completed/aborted)
    match_data = data_access_service.get_match(match_id)
    if not match_data:
        return  # Match not found
    
    match_result = match_data.get('match_result')
    if match_result is not None:
        # Match is already terminal (completed or aborted)
        return
    
    # Check if player has confirmed
    confirmed_players = match_completion_service.match_confirmations.get(match_id, set())
    if self.player.discord_user_id in confirmed_players:
        return  # Player already confirmed
    
    # Send reminder (use notification queue)
    embed = discord.Embed(
        title="⏰ Match Confirmation Reminder",
        description="You need to confirm your match or abort it manually. Check your match notification above for the Confirm Match button.",
        color=discord.Color.orange()
    )
    
    await queue_channel_send(channel, embed=embed)
```

## 4. Player Ban System

**Goal**: Allow admins to ban players from using the bot.

### Database Schema Changes

**File: `docs/schemas/postgres_schema.md`**

Add after `shield_battery_bug`:
```sql
is_banned               BOOLEAN DEFAULT FALSE,
```

**File: `src/backend/db/create_table.py`**

Add after `shield_battery_bug`:
```python
is_banned               INTEGER DEFAULT 0,
```

### Data Access Layer

**File: `src/backend/services/data_access_service.py`**:

1. Add to empty DataFrame schema after `"shield_battery_bug"`:
```python
"is_banned": pl.Series([], dtype=pl.Boolean),
```

2. Add to `WriteJobType` enum:
```python
UPDATE_IS_BANNED = "update_is_banned"
```

3. Add methods (similar to shield_battery_bug):
```python
def get_is_banned(self, discord_uid: int) -> bool:
    """Get whether player is banned."""
    if self._players_df is None or len(self._players_df) == 0:
        return False
    
    # Handle missing column (defensive)
    if "is_banned" not in self._players_df.columns:
        return False
    
    player_row = self._players_df.filter(pl.col("discord_uid") == discord_uid)
    if len(player_row) == 0:
        return False
    
    return player_row["is_banned"][0]

async def set_is_banned(self, discord_uid: int, value: bool) -> bool:
    """Set whether player is banned."""
    if self._players_df is None:
        return False
    
    # Update in-memory DataFrame
    mask = pl.col("discord_uid") == discord_uid
    self._players_df = self._players_df.with_columns(
        pl.when(mask).then(pl.lit(value)).otherwise(pl.col("is_banned")).alias("is_banned")
    )
    
    # Queue async database write
    await self._queue_write_job(WriteJobType.UPDATE_IS_BANNED, {
        "discord_uid": discord_uid,
        "value": value
    })
    
    return True
```

4. Add handler in `_process_write_job()`:
```python
elif job.job_type == WriteJobType.UPDATE_IS_BANNED:
    self._db_writer.update_is_banned(
        job.data["discord_uid"],
        job.data["value"]
    )
```

5. Add to `create_player()` new_row DataFrame:
```python
"is_banned": [False],
```

**File: `src/backend/db/db_reader_writer.py`**:

Add method after `update_shield_battery_bug()`:
```python
def update_is_banned(self, discord_uid: int, value: bool) -> bool:
    """Update ban status in database."""
    query = "UPDATE players SET is_banned = :value WHERE discord_uid = :discord_uid"
    params = {"discord_uid": discord_uid, "value": value}
    self._cursor.execute(query, params)
    self._connection.commit()
    return True
```

### Guard Service Integration

**File: `src/backend/services/command_guard_service.py`**:

Add new exception class after `DMOnlyError` (after line 29):
```python
class BannedError(CommandGuardError):
    """Raised when a banned user attempts to use the bot."""
```

Add new method after `require_setup_completed()`:
```python
def require_not_banned(self, player: Dict[str, Any]) -> None:
    """Check if player is banned. Raises BannedError if banned."""
    if player.get('is_banned', False):
        raise BannedError("Your account has been banned from using this bot.")
```

Modify `ensure_player_record()` to call the ban check (after line 60):
```python
def ensure_player_record(self, discord_user_id: int, discord_username: str) -> Dict[str, Any]:
    """
    Ensure the player exists and return the record.
    
    Uses cache-first strategy:
    1. Check cache for player record
    2. If not found, query database and cache result
    3. Check if player is banned
    4. Return player record
    
    Expected performance: <5ms (cached) vs ~170ms (uncached)
    """
    # Try cache first
    cached_player = player_cache.get(discord_user_id)
    if cached_player:
        # Check ban status before returning
        self.require_not_banned(cached_player)
        return cached_player
    
    # Cache miss - fetch from database
    player_record = self.user_service.ensure_player_exists(discord_user_id, discord_username)
    
    # Cache the result
    player_cache.set(discord_user_id, player_record)
    
    # Check ban status
    self.require_not_banned(player_record)
    
    return player_record
```

### UI Component

**File: `src/bot/components/banned_embed.py`** (NEW):
```python
import discord


def create_banned_embed() -> discord.Embed:
    """Create the banned player embed."""
    embed = discord.Embed(
        title="🚫 Account Banned",
        description="Your account has been banned from using this bot. If you believe this is in error, please contact an administrator.",
        color=discord.Color.red()
    )
    return embed
```

### Guard Embed Integration

**File: `src/bot/components/command_guard_embeds.py`**:

Import the new exception (update imports at top):
```python
from src.backend.services.command_guard_service import (
    CommandGuardError,
    TermsNotAcceptedError,
    SetupIncompleteError,
    AccountNotActivatedError,
    DMOnlyError,
    BannedError
)
```

Add case in `create_command_guard_error_embed()` after `DMOnlyError` case:
```python
elif isinstance(error, BannedError):
    from src.bot.components.banned_embed import create_banned_embed
    return create_banned_embed()
```

**Note**: No need to modify individual command files since `ensure_player_record()` now automatically checks ban status.

## 5. Admin Ban Toggle Command

**Goal**: Let admins toggle ban status for players.

### Admin Service Backend

**File: `src/backend/services/admin_service.py`**:

Add new method after `unblock_player_state()`:
```python
async def toggle_ban_status(
    self,
    discord_uid: int,
    admin_discord_id: int,
    reason: str
) -> dict:
    """
    Toggle the is_banned status for a player.
    Returns dict with old_status, new_status, player_name.
    """
    # Get current status
    current_banned = self.data_service.get_is_banned(discord_uid)
    new_banned = not current_banned
    
    # Update status
    await self.data_service.set_is_banned(discord_uid, new_banned)
    
    # Get player info for logging
    player = self.data_service.get_player_by_discord_uid(discord_uid)
    player_name = player.get("player_name", "Unknown") if player else "Unknown"
    
    # Log admin action
    await self._log_admin_action(
        admin_discord_id=admin_discord_id,
        action_type="toggle_ban",
        target_discord_uid=discord_uid,
        reason=reason,
        details={
            "old_status": current_banned,
            "new_status": new_banned
        }
    )
    
    return {
        "success": True,
        "old_status": current_banned,
        "new_status": new_banned,
        "player_name": player_name
    }
```

### Admin Command

**File: `src/bot/commands/admin_command.py`**:

Add new command after `admin_unblock_queue`:
```python
@admin_group.command(name="ban", description="[Admin] Toggle ban status for a player")
@app_commands.describe(
    user="Player's @username, username, or Discord ID",
    reason="Reason for the ban/unban"
)
@admin_only()
async def admin_ban(
    interaction: discord.Interaction,
    user: str,
    reason: str
):
    """Toggle ban status for a player."""
    # Resolve user input to Discord ID
    user_info = await admin_service.resolve_user(user)
    
    if user_info is None:
        await interaction.response.send_message(
            f"❌ Could not find user: {user}",
            ephemeral=True
        )
        return
    
    uid = user_info['discord_uid']
    player_name = user_info['player_name']
    
    # Check current status
    current_banned = data_access_service.get_is_banned(uid)
    action = "unban" if current_banned else "ban"
    
    async def confirm_callback(button_interaction: discord.Interaction):
        await button_interaction.response.defer()
        
        result = await admin_service.toggle_ban_status(
            discord_uid=uid,
            admin_discord_id=interaction.user.id,
            reason=reason
        )
        
        if result['success']:
            action_past = "banned" if result["new_status"] else "unbanned"
            result_embed = discord.Embed(
                title=f"✅ Admin: Player {action_past.title()}",
                description=f"**Player:** <@{uid}> ({player_name})\n**Status:** {action_past.title()}\n**Previous Status:** {'Banned' if result['old_status'] else 'Not Banned'}",
                color=discord.Color.green()
            )
            
            result_embed.add_field(
                name="👤 Admin",
                value=interaction.user.name,
                inline=True
            )
            result_embed.add_field(
                name="📝 Reason",
                value=reason,
                inline=False
            )
        else:
            result_embed = discord.Embed(
                title="❌ Admin: Ban Toggle Failed",
                description=f"Error: {result.get('error', 'Unknown error')}",
                color=discord.Color.red()
            )
        
        await button_interaction.edit_original_response(embed=result_embed, view=None)
    
    embed, view = _create_admin_confirmation(
        interaction,
        f"⚠️ Admin: Confirm {action.title()}",
        f"**Player:** <@{uid}> ({player_name})\n**Current Status:** {'Banned' if current_banned else 'Not Banned'}\n**Action:** {action.title()}\n**Reason:** {reason}\n\nThis will immediately {'unban' if current_banned else 'ban'} this player. Confirm?",
        confirm_callback
    )
    
    await interaction.response.send_message(embed=embed, view=view)
```

## 6. Replay Embeds in Admin Match Command

**Goal**: Show replay details for both players in the `/admin match` command.

**File: `src/bot/commands/admin_command.py`**:

Add imports at the top if not already present:
```python
import polars as pl
from src.bot.components.replay_details_embed import ReplayDetailsEmbed
```

Modify the `admin_match` command to add replay embeds. After getting `state` from `admin_service.get_match_full_state(match_id)` and before creating the JSON file:

```python
# Prepare replay embeds for both players
replay_embeds = []

# Get player 1 and player 2 replay data
p1_replay_path = match_data.get('player_1_replay_path')
p2_replay_path = match_data.get('player_2_replay_path')

# Player 1 replay
if p1_replay_path:
    try:
        p1_replay = data_access_service._replays_df.filter(
            pl.col("replay_path") == p1_replay_path
        )
        if len(p1_replay) > 0:
            p1_replay_data = p1_replay.to_dicts()[0]
            p1_embed = ReplayDetailsEmbed.get_success_embed(p1_replay_data)
            # Customize title to show player
            p1_embed.title = f"📄 Player 1 Replay: {p1_name}"
            replay_embeds.append(p1_embed)
    except Exception as e:
        error_embed = discord.Embed(
            title=f"❌ Player 1 Replay Error",
            description=f"Failed to load Player 1 replay: {str(e)}",
            color=discord.Color.red()
        )
        replay_embeds.append(error_embed)

# Player 2 replay
if p2_replay_path:
    try:
        p2_replay = data_access_service._replays_df.filter(
            pl.col("replay_path") == p2_replay_path
        )
        if len(p2_replay) > 0:
            p2_replay_data = p2_replay.to_dicts()[0]
            p2_embed = ReplayDetailsEmbed.get_success_embed(p2_replay_data)
            # Customize title to show player
            p2_embed.title = f"📄 Player 2 Replay: {p2_name}"
            replay_embeds.append(p2_embed)
    except Exception as e:
        error_embed = discord.Embed(
            title=f"❌ Player 2 Replay Error",
            description=f"Failed to load Player 2 replay: {str(e)}",
            color=discord.Color.red()
        )
        replay_embeds.append(error_embed)
```

Then modify the followup.send to include the embeds:
```python
await interaction.followup.send(
    content=f"Match #{match_id} State",
    file=file,
    embeds=replay_embeds if replay_embeds else []
)
```

## SQL Migration for Production

After implementing, run these SQL commands on the live Supabase database:
```sql
ALTER TABLE players ADD COLUMN shield_battery_bug BOOLEAN DEFAULT FALSE;
ALTER TABLE players ADD COLUMN is_banned BOOLEAN DEFAULT FALSE;
```

## Implementation Order

1. Ban system (blocks bad actors immediately)
2. Deactivate searching view (immediate API savings)
3. Shield battery bug notification (user education)
4. Match confirmation reminder (reduce timeouts)
5. Replay embeds in admin match command (admin tooling improvement)

## Key Implementation Notes

- The deactivation happens when `queue_searching_view_manager.unregister()` is called
- The match notification is sent via `queue_channel_send()` which returns a `discord.Message` object with an ID
- The confirmation reminder checks `match_completion_service.match_confirmations` which is a `Dict[int, Set[int]]` mapping match_id to confirmed player discord_uids
- The admin ban command uses the same confirmation pattern as other admin commands with `_create_admin_confirmation()` helper
- All new boolean columns need defensive handling in DataAccessService for databases without the columns yet
- For replay embeds, exceptions are caught individually per player and displayed as error embeds
- Shield battery notification only sent if match has BW Protoss (`bw_protoss` race)
- Shield battery and confirmation reminder check if match is terminal before sending
- Ban check is integrated into `ensure_player_record()` so no individual command changes needed
- All UI components use `GLOBAL_TIMEOUT` from `src.bot.config`
- Shield battery confirmation adds a field to the embed and uses interaction queue

## Schema Summary

### PostgreSQL (`docs/schemas/postgres_schema.md`)
- Add `shield_battery_bug BOOLEAN DEFAULT FALSE,` after `player_state`
- Add `is_banned BOOLEAN DEFAULT FALSE,` after `shield_battery_bug`

### SQLite (`src/backend/db/create_table.py`)
- Add `shield_battery_bug INTEGER DEFAULT 0,` after `player_state`
- Add `is_banned INTEGER DEFAULT 0,` after `shield_battery_bug`

### Polars DataFrame (`src/backend/services/data_access_service.py`)
- Add `"shield_battery_bug": pl.Series([], dtype=pl.Boolean),` after `"player_state"`
- Add `"is_banned": pl.Series([], dtype=pl.Boolean),` after `"shield_battery_bug"`
- Add both fields to `create_player()` new_row with default `[False]`

## Implementation To-dos

### Feature 1: Deactivate Searching View
- [ ] Remove "Match Found!" embed edit from `QueueSearchingView._listen_for_match()` in queue_command.py

### Feature 2: Shield Battery Bug Notification
- [ ] Add `shield_battery_bug BOOLEAN DEFAULT FALSE` to PostgreSQL schema (docs/schemas/postgres_schema.md)
- [ ] Add `shield_battery_bug INTEGER DEFAULT 0` to SQLite schema (src/backend/db/create_table.py)
- [ ] Add `"shield_battery_bug": pl.Series([], dtype=pl.Boolean)` to DataAccessService empty DataFrame
- [ ] Add `UPDATE_SHIELD_BATTERY_BUG` to WriteJobType enum
- [ ] Add `get_shield_battery_bug()` method to DataAccessService
- [ ] Add `set_shield_battery_bug()` method to DataAccessService
- [ ] Add handler for UPDATE_SHIELD_BATTERY_BUG in `_process_write_job()`
- [ ] Add `update_shield_battery_bug()` to DatabaseWriter (db_reader_writer.py)
- [ ] Add `"shield_battery_bug": [False]` to `create_player()` new_row DataFrame
- [ ] Create new file `src/bot/components/shield_battery_bug_embed.py` with ShieldBatteryBugView
- [ ] Add `_send_shield_battery_notification()` method to QueueSearchingView
- [ ] Integrate shield battery notification call in `_listen_for_match()` after match message sent

### Feature 3: Match Confirmation Reminder
- [ ] Add `_send_confirmation_reminder()` method to QueueSearchingView
- [ ] Integrate confirmation reminder call in `_listen_for_match()` after match message sent

### Feature 4: Player Ban System
- [ ] Add `is_banned BOOLEAN DEFAULT FALSE` to PostgreSQL schema (docs/schemas/postgres_schema.md)
- [ ] Add `is_banned INTEGER DEFAULT 0` to SQLite schema (src/backend/db/create_table.py)
- [ ] Add `"is_banned": pl.Series([], dtype=pl.Boolean)` to DataAccessService empty DataFrame
- [ ] Add `UPDATE_IS_BANNED` to WriteJobType enum
- [ ] Add `get_is_banned()` method to DataAccessService
- [ ] Add `set_is_banned()` method to DataAccessService
- [ ] Add handler for UPDATE_IS_BANNED in `_process_write_job()`
- [ ] Add `update_is_banned()` to DatabaseWriter (db_reader_writer.py)
- [ ] Add `"is_banned": [False]` to `create_player()` new_row DataFrame
- [ ] Add `BannedError` exception class to command_guard_service.py
- [ ] Add `require_not_banned()` method to CommandGuardService
- [ ] Integrate ban check into `ensure_player_record()` method
- [ ] Create new file `src/bot/components/banned_embed.py` with create_banned_embed()
- [ ] Update imports in command_guard_embeds.py to include BannedError
- [ ] Add BannedError case to `create_command_guard_error_embed()`

### Feature 5: Admin Ban Toggle Command
- [ ] Add `toggle_ban_status()` method to AdminService (admin_service.py)
- [ ] Add `/admin ban` command to admin_command.py with confirmation flow

### Feature 6: Replay Embeds in Admin Match
- [ ] Add `import polars as pl` to admin_command.py if not present
- [ ] Add `from src.bot.components.replay_details_embed import ReplayDetailsEmbed` to admin_command.py
- [ ] Add replay embed generation code to `/admin match` command
- [ ] Update followup.send() to include replay_embeds parameter

### Database Migration (Post-Implementation)
- [ ] Run `ALTER TABLE players ADD COLUMN shield_battery_bug BOOLEAN DEFAULT FALSE;` on Supabase
- [ ] Run `ALTER TABLE players ADD COLUMN is_banned BOOLEAN DEFAULT FALSE;` on Supabase

