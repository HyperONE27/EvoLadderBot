# Preference Persistence Fix

## 🎯 **PREFERENCE STORAGE ISSUE IDENTIFIED AND FIXED**

### ✅ **Problem Identified**
Player preferences were not being stored when they joined the queue due to two issues:

1. **Async Task Not Awaited**: The `persist_preferences()` method was creating async tasks with `asyncio.create_task()` but not awaiting them
2. **Missing Persistence on Queue Join**: Preferences were only saved when UI elements changed, not when actually joining the queue

### ✅ **Root Cause Analysis**

#### **Issue 1: Async Task Not Awaited**
**Before (Broken):**
```python
async def persist_preferences(self) -> None:
    # ... prepare data ...
    
    def _write_preferences() -> None:
        # ... complex async task creation ...
        if loop.is_running():
            asyncio.create_task(data_service.update_player_preferences(...))  # ❌ Not awaited!
        else:
            loop.run_until_complete(data_service.update_player_preferences(...))
    
    await loop.run_in_executor(None, _write_preferences)  # ❌ Task might not complete
```

**After (Fixed):**
```python
async def persist_preferences(self) -> None:
    # ... prepare data ...
    
    try:
        # Call async method directly
        await data_service.update_player_preferences(...)  # ✅ Properly awaited
    except Exception as exc:
        logger.error("Failed to update preferences: %s", exc)
```

#### **Issue 2: Missing Persistence on Queue Join**
**Before (Incomplete):**
```python
async def callback(self, interaction: discord.Interaction):
    # ... validation ...
    
    # Create queue preferences (but don't persist them!)
    preferences = QueuePreferences(
        selected_races=self.view.get_selected_race_codes(),
        vetoed_maps=self.view.vetoed_maps,
        # ...
    )
```

**After (Complete):**
```python
async def callback(self, interaction: discord.Interaction):
    # ... validation ...
    
    # Persist current preferences before joining queue
    await self.view.persist_preferences()  # ✅ Save preferences
    
    # Create queue preferences
    preferences = QueuePreferences(
        selected_races=self.view.get_selected_race_codes(),
        vetoed_maps=self.view.vetoed_maps,
        # ...
    )
```

### ✅ **Data Flow Verification**

#### **Preference Storage Pipeline**
1. **UI Changes** → `persist_preferences()` called → DataAccessService → Database
2. **Queue Join** → `persist_preferences()` called → DataAccessService → Database
3. **DataAccessService** → Updates in-memory DataFrame → Queues async DB write
4. **Database Writer** → Processes `UPDATE_PREFERENCES` job → PostgreSQL

#### **Database Schema**
```sql
CREATE TABLE preferences_1v1 (
    discord_uid             BIGINT PRIMARY KEY,
    last_chosen_races       TEXT,
    last_chosen_vetoes      TEXT,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### **WriteJob Processing**
```python
elif job.job_type == WriteJobType.UPDATE_PREFERENCES:
    await loop.run_in_executor(
        None,
        self._db_writer.update_preferences_1v1,
        job.data['discord_uid'],
        job.data.get('last_chosen_races'),
        job.data.get('last_chosen_vetoes')
    )
```

### ✅ **When Preferences Are Now Saved**

1. **Race Selection Changes** ✅
   - Brood War race dropdown
   - StarCraft 2 race dropdown

2. **Map Veto Changes** ✅
   - Map veto dropdown selections

3. **Selection Clearing** ✅
   - Clear selections button

4. **Queue Join** ✅ (NEW)
   - When player clicks "Join Queue" button

### ✅ **Technical Improvements**

#### **Simplified Async Handling**
- **Before**: Complex nested async task creation with event loop detection
- **After**: Direct async method calls with proper error handling

#### **Comprehensive Persistence**
- **Before**: Preferences only saved on UI changes
- **After**: Preferences saved on UI changes AND queue join

#### **Error Handling**
- **Before**: Silent failures in complex async task creation
- **After**: Proper exception handling with logging

### ✅ **Files Modified**

1. **`src/bot/commands/queue_command.py`**
   - Fixed `persist_preferences()` method to properly await async calls
   - Added preference persistence before queue join
   - Simplified async handling

### ✅ **Verification**

#### **Preference Storage Now Works**
- ✅ Race selections are saved when changed
- ✅ Map vetoes are saved when changed  
- ✅ Preferences are saved when joining queue
- ✅ All changes are persisted to database
- ✅ In-memory DataFrames are updated immediately
- ✅ Async database writes are queued properly

#### **Data Flow Complete**
- ✅ UI → DataAccessService → In-Memory → Database
- ✅ Async write queue processing
- ✅ Error handling and logging
- ✅ Database UPSERT operations

## 🎉 **MISSION ACCOMPLISHED**

**PREFERENCE PERSISTENCE NOW WORKING:**
- ✅ **Async tasks properly awaited** - No more silent failures
- ✅ **Preferences saved on queue join** - Complete persistence
- ✅ **Simplified async handling** - Cleaner, more reliable code
- ✅ **Comprehensive error handling** - Better debugging
- ✅ **Database writes working** - All preferences stored

**Your player preferences are now being stored correctly when they queue!** 🎯
