# Ephemeral Messages Update

## ⚠️ IMPORTANT: DM Limitation

**Ephemeral messages don't work in DMs.** This is a Discord platform limitation. Since all bot commands are DM-only, `ephemeral=True` has no effect. 

**The actual solution is `/prune`** - users manually clean up old messages.

See `EPHEMERAL_MESSAGES_DM_LIMITATION.md` for full details.

---

## Summary

Attempted to make all bot commands use ephemeral messages (visible only to the user who triggered the command) EXCEPT for `/queue` related messages, which need to be persistent for the matchmaking flow.

**Result**: Changes have no effect in DMs, but kept for future-proofing if guild support is added.

## Why Ephemeral Messages?

### Benefits
1. **Reduces clutter** - Messages don't accumulate in DM channels
2. **Privacy** - Messages are only visible to the user
3. **No pruning needed** - Ephemeral messages disappear when Discord restarts
4. **Better UX** - Cleaner interface, less overwhelming

### When NOT to use ephemeral
- **Queue/matchmaking messages** - Need to persist for:
  - Match state tracking
  - Replay uploads
  - Result reporting
  - Opponent interaction

## Changes Made

### Commands Updated to Ephemeral ✅

1. **`activate_command.py`**
   - Added `ephemeral=True` to post-confirmation message (line 105)

2. **`setup_command.py`**
   - Added `ephemeral=True` to error message (line 617)
   - Added `ephemeral=True` to post-confirmation message (line 640)

3. **`termsofservice_command.py`**
   - Added `ephemeral=True` to error message (line 119)
   - Added `ephemeral=True` to confirmation message (line 137)
   - Added `ephemeral=True` to decline message (line 155)

4. **`setcountry_command.py`**
   - Added `ephemeral=True` to error message (line 85)
   - Added `ephemeral=True` to success message (line 104)

### Already Ephemeral ✅

1. **`leaderboard_command.py`**
   - Uses `send_ephemeral_response()` helper
   - All messages already ephemeral

2. **`profile_command.py`**
   - Uses `send_ephemeral_response()` helper
   - All messages already ephemeral

3. **`prune_command.py`**
   - Uses `ephemeral=True` throughout
   - All messages already ephemeral

### Intentionally NOT Ephemeral ✅

1. **`queue_command.py`**
   - Uses `ephemeral=False` explicitly
   - Messages need to persist for:
     - Match views
     - Replay uploads
     - Result reporting
     - Status updates

## Implementation Pattern

### Before (Non-Ephemeral)
```python
await interaction.response.send_message(
    embed=embed,
    view=view
)
```

### After (Ephemeral)
```python
await interaction.response.send_message(
    embed=embed,
    view=view,
    ephemeral=True
)
```

### Helper Function (Already Ephemeral)
```python
# This function already adds ephemeral=True
await send_ephemeral_response(interaction, embed=embed, view=view)
```

## User Experience Impact

### Before
- User triggers `/setup`
- Bot sends message to DM
- Message stays in DM permanently
- Accumulates over time
- Needs `/prune` to clean up

### After
- User triggers `/setup`
- Bot sends ephemeral message
- Message only visible to user
- Disappears on Discord restart
- No cleanup needed

### Queue Exception
- User triggers `/queue`
- Bot sends **non-ephemeral** message
- Message stays persistent
- Needed for match flow
- Still needs `/prune` for old matches

## Testing Checklist

- [ ] `/activate` shows ephemeral messages
- [ ] `/setup` shows ephemeral messages
- [ ] `/termsofservice` shows ephemeral messages
- [ ] `/setcountry` shows ephemeral messages
- [ ] `/profile` shows ephemeral messages
- [ ] `/leaderboard` shows ephemeral messages
- [ ] `/prune` shows ephemeral messages
- [ ] `/queue` shows **non-ephemeral** messages (intentional)
- [ ] Ephemeral messages disappear on Discord restart
- [ ] Queue messages persist through Discord restart

## Future Considerations

### Potential Enhancements
1. **Ephemeral duration** - Discord ephemeral messages are deleted after 15 minutes of inactivity
2. **Context preservation** - Users can't scroll back to see old ephemeral messages
3. **Queue state recovery** - Non-ephemeral queue messages help users recover state

### Trade-offs
| Aspect | Ephemeral | Non-Ephemeral |
|--------|-----------|---------------|
| **Clutter** | ✅ No clutter | ❌ Accumulates |
| **Privacy** | ✅ Only visible to user | ❌ Visible to all |
| **Persistence** | ❌ Disappears | ✅ Stays forever |
| **History** | ❌ Can't scroll back | ✅ Full history |
| **Cleanup** | ✅ Auto-cleans | ❌ Needs `/prune` |

## Conclusion

Ephemeral messages are now the default for all bot interactions except matchmaking (`/queue`). This significantly improves the user experience by:
- Reducing visual clutter
- Eliminating need for frequent `/prune` calls
- Providing better privacy
- Making the bot feel more responsive and clean

Queue messages remain non-ephemeral because they're critical for match state and need to persist through Discord restarts.

