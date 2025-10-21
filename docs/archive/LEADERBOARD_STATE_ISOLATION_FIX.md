# Leaderboard State Isolation - Critical Security Fix

## Problem

The singleton `leaderboard_service` was storing mutable filter state that could cause race conditions between users:
- User A's filters could affect User B's view
- Pagination state was shared
- Best Race Only toggle was shared

## Solution Implemented

### 1. Made LeaderboardService STATELESS
- Removed all mutable state from service (lines 62-68 deleted)
- Changed `get_leaderboard_data()` to accept filters as parameters
- All filter state now passed explicitly

### 2. Move State to LeaderboardView 
**NEXT STEPS - Still needs to be completed:**

Add to `LeaderboardView.__init__`:
```python
# Per-user filter state (isolated from other users)
self.current_page: int = 1
self.country_filter: List[str] = []
self.race_filter: Optional[List[str]] = None
self.best_race_only: bool = False
self.country_page1_selection: List[str] = []
self.country_page2_selection: List[str] = []
```

Update all 15 locations that reference `self.view.leaderboard_service.xxx_filter` or `self.view.leaderboard_service.current_page` to use `self.view.xxx` instead.

### 3. Update all callbacks
Each callback needs to update view state, not service state:
- Line 125: `self.view.country_page1_selection = self.values`
- Line 175: `self.view.country_page2_selection = self.values`
- Line 223: `self.view.race_filter = selected_values`
- Line 444: `self.view.current_page -= 1`
- Line 463: `self.view.current_page += 1`
- Line 489: `self.view.best_race_only = not self.view.best_race_only`
- Line 516: Reset all view filters
- Line 560: `self.view.current_page = page_num`

### 4. Update service calls
Pass filters explicitly:
```python
data = await self.leaderboard_service.get_leaderboard_data(
    country_filter=self.country_filter,
    race_filter=self.race_filter,
    best_race_only=self.best_race_only,
    current_page=self.current_page,
    page_size=40
)
```

## Files Modified
- ✅ `src/backend/services/leaderboard_service.py` - Made stateless
- ⚠️  `src/bot/commands/leaderboard_command.py` - NEEDS UPDATE (15+ locations)

## Testing
After fix:
1. Two users open leaderboard simultaneously
2. User A filters to US, page 5
3. User B should see ALL countries, page 1 (not affected by A)
4. User A changes filter - should not affect User B

## Priority
**CRITICAL** - This is a race condition that affects user experience and could be exploited.

