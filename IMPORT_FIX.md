# ✅ ImportError Fixed: data_service → data_access_service

## The Error
```
ImportError: cannot import name 'data_service' from 'src.backend.services.app_context'
Did you mean: 'maps_service'?
```

## Root Cause
I incorrectly imported `data_service` when it should be `data_access_service`.

The service is named `data_access_service` in `app_context.py`:
```python
# Line 93 in app_context.py
data_access_service = DataAccessService()
```

## The Fix

### Changed Import (Line 23)
```python
# BEFORE (WRONG):
from src.backend.services.app_context import admin_service, data_service, ranking_service

# AFTER (CORRECT):
from src.backend.services.app_context import admin_service, data_access_service, ranking_service
```

### Updated All References
Changed all `data_service.` → `data_access_service.`:
- Line 621: `match_data = data_access_service.get_match(match_id)`
- Line 633-634: `p1_info = data_access_service.get_player_info(p1_uid)`
- Line 804: `current_mmr = data_access_service.get_player_mmr(uid, race)`
- Line 989: `current_aborts = data_access_service.get_remaining_aborts(uid)`

### Removed Singleton Violations
```python
# BEFORE (VIOLATED SINGLETON):
from src.backend.services.data_access_service import DataAccessService
data_service = DataAccessService()
current_mmr = data_service.get_player_mmr(uid, race)

# AFTER (CORRECT):
current_mmr = data_access_service.get_player_mmr(uid, race)
```

## Result
✅ Bot imports successfully  
✅ No more ImportError  
✅ Singleton pattern maintained  
✅ Ready to test conflict embeds and admin resolution  

## Files Modified
- `src/bot/commands/admin_command.py` (7 changes)
  - Import statement
  - 4 method call references
  - 2 removed local instantiations

