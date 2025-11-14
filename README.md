# EvoLadderBot

### Requirements
- Python 3.12+
- Git

### Setup
```bash
git clone https://github.com/TeamKoprulu/EvoLadderBot.git
cd EvoLadderBot
python scripts/setup.py
```

## Directory Structure

```
EvoLadderBot/
├── data/
│   ├── misc/
│   │   ├── admins.json
│   │   ├── countries.json
│   │   ├── cross_table.json
│   │   ├── cross_table.xlsx
│   │   ├── emotes.json
│   │   ├── leaderboard.json
│   │   ├── maps.json
│   │   ├── mods.json
│   │   ├── races.json
│   │   └── regions.json
│   ├── replays/
│   ├── wal/
│   │   └── write_log.db
│   └── last_reconciliation.timestamp
├── diffs/
├── docs/
│   ├── architecture/
│   ├── schemas/
│   │   └── postgres_schema.md
│   ├── MATCHMAKING_INVARIANT_FIXES.md
│   ├── TODO.md
│   └── archived.zip
├── logs/
│   └── failed_writes/
│       └── failed_writes.log
├── scripts/
│   ├── add_admin_actions_table.py
│   ├── add_performance_indexes.py
│   ├── auto_convert_db_v2.py
│   ├── auto_convert_db.py
│   ├── code_stats.py
│   ├── convert_db_methods.py
│   ├── count_src_data_stats.py
│   ├── cross_table_converter.py
│   ├── generate_realistic_mock_data.py
│   ├── ladder_probe.py
│   ├── matchmaking_analysis.py
│   ├── matchmaking_comparison_analysis.py
│   ├── matchmaking_deep_analysis.py
│   ├── matchmaking_fairness_comparison.py
│   ├── matchmaking_long_wait_analysis.py
│   ├── matchmaking_optimization_exploration.py
│   ├── matchmaking_three_way_comparison.py
│   ├── populate_supabase.py
│   └── setup.py
├── secrets/
├── src/
│   ├── backend/
│   │   ├── api/
│   │   │   └── server.py
│   │   ├── core/
│   │   ├── db/
│   │   ├── infrastructure/
│   │   ├── monitoring/
│   │   ├── services/
│   │   └── types/
│   └── bot/
│       ├── commands/
│       ├── components/
│       ├── utils/
│       ├── __init__.py
│       ├── bot_setup.py
│       ├── config.py
│       ├── main.py
│       └── message_queue.py
├── tests/
│   ├── backend/
│   ├── bot/
│   │   └── utils/
│   ├── characterize/
│   ├── end_to_end/
│   ├── fixtures/
│   │   └── mmrs_1v1_snapshot.csv
│   ├── integration/
│   ├── test_data/
│   ├── utils/
│   └── [test files]
├── evoladder.db
├── Procfile
├── railway.json
├── requirements.txt
├── runtime.txt
├── README.md
├── CLEANUP_ANALYSIS.md
├── IMPLEMENTATION_COMPLETE.md
├── IMPLEMENTATION_PLAN.md
├── IMPLEMENTATION_SUMMARY.md
└── PRODUCTION_TEST_CHECKLIST.md
```

## Directory Structure (Simplified)

```
EvoLadderBot/
├── data/
│   ├── misc/
│   │   ├── admins.json
│   │   ├── countries.json
│   │   ├── cross_table.json
│   │   ├── cross_table.xlsx
│   │   ├── emotes.json
│   │   ├── leaderboard.json
│   │   ├── maps.json
│   │   ├── mods.json
│   │   ├── races.json
│   │   └── regions.json
│   ├── replays/
│   ├── wal/
│   │   └── write_log.db
│   └── last_reconciliation.timestamp
│
├── docs/
│   ├── architecture/
│   ├── schemas/
│   ├── MATCHMAKING_INVARIANT_FIXES.md
│   ├── TODO.md
│   └── archived.zip
│
├── secrets/
│   ├── .env.prod
│   └── .env.test
│
├── src/
│   ├── backend/
│   │   ├── api/
│   │   │   └── server.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   └── types.py
│   │   ├── db/
│   │   │   ├── adapters/
│   │   │   │   ├── base_adapter.py
│   │   │   │   ├── postgresql_adapter.py
│   │   │   │   ├── sqlite_adapter.py
│   │   │   │   └── timed_adapter.py
│   │   │   ├── connection_pool.py
│   │   │   ├── db_connection.py
│   │   │   └── db_reader_writer.py
│   │   ├── services/
│   │   │   ├── admin_service.py
│   │   │   ├── app_context.py
│   │   │   ├── base_config_service.py
│   │   │   ├── cache_service.py
│   │   │   ├── command_guard_service.py
│   │   │   ├── countries_service.py
│   │   │   ├── data_access_service.py
│   │   │   ├── leaderboard_service.py
│   │   │   ├── localization_service.py
│   │   │   ├── maps_service.py
│   │   │   ├── match_completion_service.py
│   │   │   ├── matchmaking_service.py
│   │   │   ├── mmr_service.py
│   │   │   ├── mods_service.py
│   │   │   ├── notification_service.py
│   │   │   ├── races_service.py
│   │   │   ├── ranking_service.py
│   │   │   ├── regions_service.py
│   │   │   ├── replay_service.py
│   │   │   ├── storage_service.py
│   │   │   ├── user_info_service.py
│   │   │   └── validation_service.py
│   │   └── types/
│   │
│   └── bot/
│       ├── commands/
│       │   ├── activate_command.py
│       │   ├── admin_command.py
│       │   ├── help_command.py
│       │   ├── leaderboard_command.py
│       │   ├── profile_command.py
│       │   ├── prune_command.py
│       │   ├── queue_command.py
│       │   ├── setcountry_command.py
│       │   ├── setup_command.py
│       │   └── termsofservice_command.py
│       ├── components/
│       │   ├── banned_embed.py
│       │   ├── cancel_embed.py
│       │   ├── command_guard_embeds.py
│       │   ├── confirm_embed.py
│       │   ├── confirm_restart_cancel_buttons.py
│       │   ├── error_embed.py
│       │   ├── match_confirmation_embed.py
│       │   ├── match_report_notification_embed.py
│       │   ├── next_previous_buttons.py
│       │   ├── replay_details_embed.py
│       │   └── shield_battery_bug_embed.py
│       ├── utils/
│       │   ├── command_decorators.py
│       │   ├── discord_utils.py
│       │   └── message_helpers.py
│       ├── bot_setup.py
│       ├── config.py
│       ├── main.py
│       └── message_queue.py
│
├── tests/
│   ├── backend/
│   ├── bot/
│   ├── characterize/
│   ├── end_to_end/
│   ├── fixtures/
│   ├── integration/
│   ├── test_data/
│   └── utils/
│
├── .env
├── evoladder.db
├── Procfile
├── railway.json
├── README.md
├── requirements.txt
└── runtime.txt
```