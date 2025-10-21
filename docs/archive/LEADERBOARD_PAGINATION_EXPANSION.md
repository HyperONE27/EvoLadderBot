# Leaderboard Pagination Expansion

## Overview
Updated the leaderboard to display 4 sections of 10 players each (40 players total per page) and limited pagination to 25 pages to avoid Discord dropdown limits.

## Changes Made

### 1. Updated Page Size
- **File**: `src/bot/commands/leaderboard_command.py`
- **Changes**:
  - Changed `page_size=20` to `page_size=40` in all leaderboard data calls
  - Updated comments to reflect "4 sections of 10" players per page
  - Modified `players_per_field = 10` to remain the same (10 players per Discord field)

### 2. Added Page Limit
- **File**: `src/backend/services/leaderboard_service.py`
- **Changes**:
  - Added `max_pages = 25` limit to prevent Discord dropdown overflow
  - Implemented player truncation when total pages exceed 25
  - Updated `total_players` count to reflect any truncation
  - Added explanatory comments about the 25-page limit

## Technical Details

### Page Structure
- **Per Page**: 40 players total
- **Per Section**: 10 players (4 sections per page)
- **Max Pages**: 25 pages
- **Max Players Displayed**: 1,000 players (25 × 40)

### Discord Limitations
- Discord dropdowns have a limit of 25 options
- Each page represents one dropdown option
- 25 pages × 40 players = 1,000 total players displayed
- Players beyond this limit are truncated to maintain UI functionality

### Performance Impact
- **Database**: No change in query performance
- **Memory**: Slightly increased due to larger page sizes
- **UI**: Better user experience with more players per page
- **Caching**: Same 60-second cache TTL maintained

## Benefits

1. **More Players Per Page**: Users see 40 players instead of 20
2. **Better Organization**: 4 clear sections of 10 players each
3. **Discord Compliance**: Stays within dropdown limits
4. **Scalable**: Can handle up to 1,000 players efficiently
5. **Consistent Layout**: Maintains the existing 10-player field structure

## Files Modified

- `src/bot/commands/leaderboard_command.py`
  - Updated page size from 20 to 40
  - Updated comments and documentation
  
- `src/backend/services/leaderboard_service.py`
  - Added 25-page limit
  - Implemented player truncation
  - Updated total player count logic

## Testing Recommendations

1. **Page Navigation**: Test all 25 pages load correctly
2. **Player Count**: Verify 40 players per page
3. **Section Layout**: Confirm 4 sections of 10 players
4. **Truncation**: Test with >1,000 players to verify truncation
5. **Performance**: Monitor response times with larger page sizes
6. **Dropdown Limits**: Verify Discord dropdowns don't exceed 25 options

## Future Considerations

- If player count grows beyond 1,000, consider implementing search/filtering
- Monitor performance with the larger page sizes
- Consider implementing "jump to page" functionality for large datasets
- Evaluate if 40 players per page is optimal for user experience

## Deployment Notes

- No database changes required
- No environment variable changes
- Backward compatible with existing data
- Immediate effect after deployment
