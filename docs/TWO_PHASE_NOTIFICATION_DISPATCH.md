# Two-Phase Match Notification Dispatch

## Problem Statement

Currently, match notifications fire independently for each match:
1. Each match triggers 4 API calls simultaneously (2 edits + 2 sends)
2. In large waves (15+ matches), this causes 60+ API calls at once
3. Players in later batches see delays with no indication they were matched

## User Experience Issue

**Bad UX**: Players waiting in later batches see:
- Other players already reporting results
- No indication they got matched yet
- Perceived unfairness ("Why did they get notified first?")

**Good UX**: All players see:
1. Immediate "Match Found!" confirmation (everyone at the same time)
2. Detailed match info arrives shortly after (can be staggered)

## Solution: Two-Phase Dispatch

### Phase 1: Instant Confirmation (All Players)
Send "Match Found!" confirmation edits to ALL players immediately:
- Edit "Searching..." → "Match Found! Details incoming..."
- Small, fast messages
- 2 API calls per match (1 per player)
- Can send all at once (30 edits = 30 API calls, under 50/sec limit)

### Phase 2: Detailed Match Info (Batched)
Send detailed match embeds in batches with delays:
- Full match details with buttons
- Larger, slower messages
- 2 API calls per match (1 per player)
- Batched to stay under rate limits

## Implementation Strategy

### Current Flow

```
Matchmaker.attempt_match() →
  for each match:
    create_match() →
    call match_callback(match_result) →
      asyncio.create_task(notification_service.publish_match_found(match))
      
Each player's QueueSearchingView._listen_for_match():
  match = await notification_queue.get()
  # Edit searching message
  await last_interaction.edit_original_response(confirmation_embed)
  # Send detailed embed
  await channel.send(detailed_embed, view=match_view)
```

**Problem**: Each match triggers independently, no coordination.

### Proposed Flow

```
Matchmaker.attempt_match() →
  matches = []  # Collect all matches
  
  for match_pair in match_pairs:
    match_result = create_match(...)
    matches.append(match_result)
  
  # Dispatch in two coordinated phases
  await dispatch_matches_two_phase(matches)
```

## Implementation Details

### Option 1: Modify Notification Service (Recommended)

Add a new method to `NotificationService` for bulk two-phase dispatch:

```python
async def publish_matches_two_phase(self, matches: List[MatchResult]) -> None:
    """
    Publish multiple matches using two-phase dispatch:
    Phase 1: Send all confirmation edits immediately
    Phase 2: Send all detailed embeds in batches
    
    Args:
        matches: List of match results to publish
    """
    print(f"[NotificationService] Dispatching {len(matches)} matches in two phases")
    
    # PHASE 1: Confirmation edits (all at once)
    # Signal all players that they got matched
    confirmation_tasks = []
    for match in matches:
        # Create a special "confirmation only" notification
        confirmation = MatchConfirmation(match_id=match.match_id)
        
        p1_id = match.player_1_discord_id
        p2_id = match.player_2_discord_id
        
        async with self._lock:
            if p1_id in self._player_listeners:
                await self._player_listeners[p1_id].put(('confirmation', confirmation))
            if p2_id in self._player_listeners:
                await self._player_listeners[p2_id].put(('confirmation', confirmation))
    
    print(f"  Phase 1: Sent {len(matches) * 2} confirmation signals")
    
    # Small delay to let confirmations process
    await asyncio.sleep(0.1)
    
    # PHASE 2: Detailed embeds (batched with delays)
    BATCH_SIZE = 10  # 10 matches = 20 API calls (under 50/sec)
    BATCH_DELAY = 1.0
    
    for i in range(0, len(matches), BATCH_SIZE):
        batch = matches[i:i+BATCH_SIZE]
        
        # Send detailed match info for this batch
        for match in batch:
            p1_id = match.player_1_discord_id
            p2_id = match.player_2_discord_id
            
            async with self._lock:
                if p1_id in self._player_listeners:
                    await self._player_listeners[p1_id].put(('details', match))
                if p2_id in self._player_listeners:
                    await self._player_listeners[p2_id].put(('details', match))
        
        print(f"  Phase 2: Sent batch {i//BATCH_SIZE + 1} ({len(batch)} matches)")
        
        # Delay between batches (skip for last batch)
        if i + BATCH_SIZE < len(matches):
            await asyncio.sleep(BATCH_DELAY)
```

### Option 2: Modify Queue View to Handle Two-Phase Messages

Update `QueueSearchingView._listen_for_match()`:

```python
async def _listen_for_match(self):
    """Listen for two-phase match notifications."""
    notification_queue = await notification_service.subscribe(self.player.discord_user_id)
    
    try:
        # PHASE 1: Wait for confirmation
        msg_type, payload = await notification_queue.get()
        
        if msg_type == 'confirmation':
            # Show immediate confirmation
            confirmation_embed = discord.Embed(
                title="🎉 Match Found!",
                description="Loading match details...",
                color=discord.Color.green()
            )
            await self.last_interaction.edit_original_response(
                embed=confirmation_embed,
                view=None
            )
            print(f"[Match] Player {self.player.discord_user_id} confirmed")
            
            # PHASE 2: Wait for detailed match info
            msg_type, match_result = await notification_queue.get()
        
        elif msg_type == 'details':
            # Old single-phase path (fallback)
            match_result = payload
            
            # Edit searching message to confirmation
            confirmation_embed = discord.Embed(
                title="🎉 Match Found!",
                description="Your match is ready.",
                color=discord.Color.green()
            )
            await self.last_interaction.edit_original_response(
                embed=confirmation_embed,
                view=None
            )
        
        # At this point we have match_result
        is_player1 = match_result.player_1_discord_id == self.player.discord_user_id
        
        # Create and send detailed match view
        match_view = MatchFoundView(match_result, is_player1)
        embed = await asyncio.get_running_loop().run_in_executor(
            None, match_view.get_embed
        )
        new_match_message = await self.channel.send(embed=embed, view=match_view)
        
        # ... rest of setup
        
    finally:
        await notification_service.unsubscribe(self.player.discord_user_id)
```

### Option 3: Centralized Batch Handler (Alternative)

Create a dedicated `MatchNotificationDispatcher` service:

```python
class MatchNotificationDispatcher:
    """Handles rate-limited, two-phase match notification dispatch."""
    
    async def dispatch_match_wave(self, matches: List[MatchResult]):
        """
        Dispatch all matches from a matchmaking wave in two phases.
        
        Phase 1: Immediate confirmation to all players
        Phase 2: Batched detailed embeds
        """
        print(f"[Dispatcher] Dispatching {len(matches)} matches")
        
        # Collect all players and their views
        player_views = {}  # discord_uid -> QueueSearchingView
        for match in matches:
            # Look up views from queue_searching_view_manager
            p1_view = queue_searching_view_manager.get_view(match.player_1_discord_id)
            p2_view = queue_searching_view_manager.get_view(match.player_2_discord_id)
            if p1_view:
                player_views[match.player_1_discord_id] = (p1_view, match, True)
            if p2_view:
                player_views[match.player_2_discord_id] = (p2_view, match, False)
        
        # PHASE 1: Send all confirmations at once
        confirmation_tasks = []
        for discord_uid, (view, match, is_p1) in player_views.items():
            task = self._send_confirmation(view, match)
            confirmation_tasks.append(task)
        
        await asyncio.gather(*confirmation_tasks)
        print(f"  Phase 1: {len(confirmation_tasks)} confirmations sent")
        
        # Brief pause to let confirmations render
        await asyncio.sleep(0.2)
        
        # PHASE 2: Send detailed embeds in batches
        BATCH_SIZE = 10
        player_items = list(player_views.items())
        
        for i in range(0, len(player_items), BATCH_SIZE):
            batch = player_items[i:i+BATCH_SIZE]
            
            batch_tasks = []
            for discord_uid, (view, match, is_p1) in batch:
                task = self._send_detailed_embed(view, match, is_p1)
                batch_tasks.append(task)
            
            await asyncio.gather(*batch_tasks)
            print(f"  Phase 2: Batch {i//BATCH_SIZE + 1} sent ({len(batch)} embeds)")
            
            if i + BATCH_SIZE < len(player_items):
                await asyncio.sleep(1.0)
    
    async def _send_confirmation(self, view: QueueSearchingView, match: MatchResult):
        """Send immediate match found confirmation."""
        confirmation_embed = discord.Embed(
            title="🎉 Match Found!",
            description="Loading match details...",
            color=discord.Color.green()
        )
        await view.last_interaction.edit_original_response(
            embed=confirmation_embed,
            view=None
        )
    
    async def _send_detailed_embed(self, view: QueueSearchingView, 
                                   match: MatchResult, is_player1: bool):
        """Send detailed match embed with buttons."""
        match_view = MatchFoundView(match, is_player1)
        embed = await asyncio.get_running_loop().run_in_executor(
            None, match_view.get_embed
        )
        await view.channel.send(embed=embed, view=match_view)
        # ... setup and cleanup
```

## Recommended Approach

**Option 1 (Notification Service)** is cleanest because:
1. ✅ Centralized rate limit management
2. ✅ Clean separation of concerns
3. ✅ Easy to test independently
4. ✅ Works with existing architecture
5. ✅ Simple message protocol: `('confirmation', data)` or `('details', data)`

## API Call Analysis

### Current (Uncoordinated)
- 15 matches × 4 calls each = 60 API calls simultaneously
- Result: Rate limit hit, 2-3 second delays for some players

### Two-Phase Coordinated
- Phase 1: 15 matches × 2 confirmation edits = 30 API calls (instant)
- Phase 2: 15 matches × 2 embed sends = 30 API calls (batched)
  - Batch 1 (10 matches): 20 API calls at t=0
  - Batch 2 (5 matches): 10 API calls at t=1s

Total time: ~1.2 seconds vs. 2-3+ seconds with rate limiting
All players see confirmation within ~100ms

## Migration Path

1. **Add two-phase support to NotificationService**
   - New `publish_matches_two_phase()` method
   - Keep existing `publish_match_found()` as fallback

2. **Update QueueSearchingView to handle both message types**
   - Support `('confirmation', data)` and `('details', data)` messages
   - Fallback to single-phase if only `('details', data)` received

3. **Update Matchmaker.attempt_match()**
   - Collect all matches before dispatching
   - Call `notification_service.publish_matches_two_phase(matches)`

4. **Test with mock load**
   - Simulate 20+ match waves
   - Verify confirmations arrive < 200ms for all players
   - Verify detailed embeds arrive in batches

## Benefits

1. ✅ **Better UX**: All players know immediately they got matched
2. ✅ **Perceived Fairness**: Everyone gets confirmation at the same time
3. ✅ **Rate Limit Safety**: Controlled batching prevents 429 errors
4. ✅ **Graceful Degradation**: First 10 matches still instant for both phases
5. ✅ **Monitoring**: Easy to track phase 1 vs phase 2 latency separately

## Testing Strategy

```python
async def test_two_phase_dispatch():
    """Test two-phase notification with 20 simulated matches."""
    matches = [create_mock_match(i) for i in range(20)]
    
    # Simulate player views listening
    listeners = {}
    for match in matches:
        listeners[match.player_1_discord_id] = MockListener()
        listeners[match.player_2_discord_id] = MockListener()
    
    # Dispatch
    start = time.time()
    await notification_service.publish_matches_two_phase(matches)
    
    # Verify all confirmations arrived quickly
    for listener in listeners.values():
        assert listener.confirmation_time < 0.5  # < 500ms
    
    # Verify detailed embeds arrived in batches
    batch_1_times = [l.details_time for l in list(listeners.values())[:20]]
    batch_2_times = [l.details_time for l in list(listeners.values())[20:]]
    
    assert max(batch_1_times) < 1.0  # First batch instant
    assert min(batch_2_times) > 1.0  # Second batch after delay
    
    print("✅ Two-phase dispatch working correctly")
```

## Metrics to Track

1. **Phase 1 Latency**: Time from match creation to confirmation sent
2. **Phase 2 Latency**: Time from confirmation to detailed embed sent
3. **Total Latency**: Time from match creation to detailed embed sent
4. **Matches per Wave**: Track distribution over time
5. **Rate Limit Hits**: Monitor for 429 errors (should be zero)

## Rollout Plan

1. **Week 1**: Implement and test in development
2. **Week 2**: Deploy to staging, simulate large waves
3. **Launch Day**: Already in place as safety measure
4. **Post-Launch**: Monitor metrics, adjust batch size if needed

