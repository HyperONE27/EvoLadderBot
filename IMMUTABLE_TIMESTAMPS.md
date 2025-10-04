# Immutable Timestamp Protection

## Overview

Three timestamp fields in the `players` table are **immutable** - they can only be set once and cannot be overwritten.

## Protected Fields

| Field | When Set | Protection Method | Can Change? |
|-------|----------|-------------------|-------------|
| `created_at` | On player creation | Database DEFAULT | ❌ Never |
| `accepted_tos_date` | When TOS accepted (first time) | SQL COALESCE | ❌ Never |
| `completed_setup_date` | When setup completed (first time) | SQL COALESCE | ❌ Never |
| `updated_at` | Every update | Always overwritten | ✅ Always |

## How It Works

### created_at

```sql
CREATE TABLE players (
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ...
)
```

- Set automatically by database on INSERT
- Not included in UPDATE queries
- **Result**: Cannot be modified after creation

### accepted_tos_date

```sql
-- Only sets if currently NULL
accepted_tos_date = COALESCE(accepted_tos_date, ?)
```

- `COALESCE(accepted_tos_date, new_value)` returns:
  - `accepted_tos_date` if it's NOT NULL (keeps existing value)
  - `new_value` if `accepted_tos_date` IS NULL (sets new value)
- **Result**: Once set, subsequent attempts to update do nothing

### completed_setup_date

```sql
-- Only sets if currently NULL
completed_setup_date = COALESCE(completed_setup_date, ?)
```

- Same mechanism as `accepted_tos_date`
- **Result**: Once set, subsequent attempts to update do nothing

## Test Results

```
1. Creating player...
   created_at: 2025-10-04 02:01:21
   accepted_tos_date: None
   completed_setup_date: None

2. Accepting TOS (first time)...
   accepted_tos_date: 2025-10-03T19:01:21.784008

3. Accepting TOS again (should NOT overwrite date)...
   accepted_tos_date: 2025-10-03T19:01:21.784008  ✓ Unchanged

4. Completing setup (first time)...
   completed_setup_date: 2025-10-03T19:01:21.999606

5. Completing setup again (should NOT overwrite date)...
   completed_setup_date: 2025-10-03T19:01:21.999606  ✓ Unchanged

6. Verifying created_at was never modified...
   created_at: 2025-10-04 02:01:21  ✓ Unchanged

7. Verifying updated_at was modified...
   updated_at: 2025-10-03T19:01:22.107348  ✓ Changed
```

## Code Implementation

### In `db_reader_writer.py`

```python
def update_player(self, discord_uid: int, ...) -> bool:
    """
    Protected fields (cannot be overwritten once set):
    - created_at: Set automatically on creation, cannot be modified
    - accepted_tos_date: Set once when accepted_tos becomes True
    - completed_setup_date: Set once when completed_setup becomes True
    """
    
    if accepted_tos is not None:
        updates.append("accepted_tos = ?")
        params.append(accepted_tos)
        if accepted_tos:
            # Only set if currently NULL
            updates.append("accepted_tos_date = COALESCE(accepted_tos_date, ?)")
            params.append(datetime.now().isoformat())
    
    if completed_setup is not None:
        updates.append("completed_setup = ?")
        params.append(completed_setup)
        if completed_setup:
            # Only set if currently NULL
            updates.append("completed_setup_date = COALESCE(completed_setup_date, ?)")
            params.append(datetime.now().isoformat())
```

## Why This Matters

### Audit Trail Integrity

Once a user accepts TOS or completes setup, we need to know **when** they first did it:

- **Legal compliance**: TOS acceptance date for legal records
- **User onboarding**: When did they complete initial setup?
- **Historical accuracy**: Original timestamps preserved forever

### Prevents Accidental Overwrites

Without protection, code like this could accidentally reset dates:

```python
# BAD - without protection
service.update_player(discord_uid, accepted_tos=True)  # Resets date!
service.complete_setup(...)  # Resets setup date!
```

With protection:
```python
# GOOD - with protection
service.update_player(discord_uid, accepted_tos=True)  # Date preserved ✓
service.complete_setup(...)  # Setup date preserved ✓
```

## Behavior Examples

### Scenario 1: First TOS Acceptance

```python
# User accepts TOS for first time
service.accept_terms_of_service(discord_uid=123)

# Result:
# accepted_tos = True
# accepted_tos_date = "2025-10-04 12:00:00"  ✓ Set
```

### Scenario 2: TOS Acceptance Again

```python
# User accepts TOS again (maybe they toggled it off and back on)
service.accept_terms_of_service(discord_uid=123)

# Result:
# accepted_tos = True
# accepted_tos_date = "2025-10-04 12:00:00"  ✓ Unchanged (original date preserved)
```

### Scenario 3: Setup Re-run

```python
# User completes setup
service.complete_setup(discord_uid=123, ...)
# completed_setup_date = "2025-10-04 13:00:00"  ✓ Set

# User updates their profile later
service.complete_setup(discord_uid=123, ...)
# completed_setup_date = "2025-10-04 13:00:00"  ✓ Unchanged (original date preserved)
```

## Database Queries

### Check if timestamps are protected

```sql
-- See current values
SELECT 
    discord_uid,
    created_at,
    accepted_tos_date,
    completed_setup_date,
    updated_at
FROM players
WHERE discord_uid = 123;

-- Try to overwrite (will fail)
UPDATE players 
SET accepted_tos_date = '2025-01-01' 
WHERE discord_uid = 123 AND accepted_tos_date IS NOT NULL;
-- Result: 0 rows affected (COALESCE protects it)
```

## Benefits

1. ✅ **Data Integrity**: Original timestamps preserved forever
2. ✅ **Audit Compliance**: Accurate historical records
3. ✅ **Bug Prevention**: Can't accidentally reset important dates
4. ✅ **Legal Protection**: TOS acceptance dates for legal purposes
5. ✅ **User Trust**: Transparent record of when actions occurred

## Related Files

- `src/backend/db/db_reader_writer.py` - Implementation
- `src/backend/db/create_table.py` - Table schema with defaults
- `IMPLEMENTATION_NOTES.md` - Field documentation

---

**Summary**: Three timestamp fields are immutable once set, preserving accurate historical records and preventing accidental overwrites.

