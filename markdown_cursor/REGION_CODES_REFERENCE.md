# Region Codes Reference

## Important: Use Residential Regions Only

**The `region` field in the `players` table MUST use codes from `residential_regions` in `data/misc/regions.json`.**

Do NOT use codes from `game_servers` or `game_regions`.

## Valid Region Codes (from residential_regions)

| Code | Name |
|------|------|
| NAW | Western North America |
| NAC | Central North America |
| NAE | Eastern North America |
| CAM | Central America and the Caribbean |
| SAM | South America |
| EUW | Western Europe |
| EUE | Northern and Eastern Europe |
| AFR | Africa |
| MEA | Middle East |
| SEA | South and Southeast Asia |
| KRJ | Korea and Japan |
| CHN | China |
| THM | Taiwan, Hong Kong, and Macau |
| OCE | Oceania |
| USB | Urals and Siberia |
| FER | Far East Russia |

## Why This Matters

- **residential_regions**: Where players live (16 options)
- **game_servers**: Physical game servers (9 options) - NOT for player profiles
- **game_regions**: Broad game regions (3 options: AM, EU, AS) - NOT for player profiles

## Examples

### ✅ Correct Usage

```python
from src.backend.services.user_info_service import UserInfoService

service = UserInfoService()

# Player from Eastern US
service.create_player(
    discord_uid=12345,
    player_name="PlayerName",
    battletag="PlayerName#1234",
    country="US",
    region="NAE"  # ✓ From residential_regions
)

# Player from Western Europe
service.create_player(
    discord_uid=12346,
    player_name="EUPlayer",
    battletag="EUPlayer#5678",
    country="FR",
    region="EUW"  # ✓ From residential_regions
)
```

### ❌ Incorrect Usage

```python
# DON'T USE THESE:
region="AM"   # ❌ This is from game_regions
region="USW"  # ❌ This is from game_servers
region="NA"   # ❌ This doesn't exist in any list
region="EU"   # ❌ This is from game_regions
```

## In the Bot Commands

The `/setup` command already uses the correct codes from `residential_regions` through the `RegionsService.get_residential_regions()` method.

When users select their region of residency, they see options like:
- "Eastern North America" (code: NAE)
- "Western Europe" (code: EUW)
- "South America" (code: SAM)
- etc.

## Database Verification

To check if region codes are correct in your database:

```python
from src.backend.services.regions_service import RegionsService
from src.backend.db.db_reader_writer import DatabaseReader

regions_service = RegionsService()
reader = DatabaseReader()

# Get valid codes
valid_codes = regions_service.get_region_codes()
print("Valid region codes:", valid_codes)

# Check all players
players = reader.get_all_players()
for player in players:
    region = player['region']
    if region not in valid_codes:
        print(f"⚠️ Invalid region for {player['player_name']}: {region}")
    else:
        print(f"✓ {player['player_name']}: {region}")
```

---

**Summary**: Always use codes from `residential_regions` in `regions.json` for the `region` field in the `players` table. The test data has been corrected to use the proper codes.

