# EvoLadderBot
A Discord ladder bot for SC: Evo Complete. Backend is engineered to allow for expansion to web client later.

## Environment Variables

The bot requires the following environment variables to be set in a `.env` file:

- `EVOLADDERBOT_TOKEN`: Your Discord bot token
- `WORKER_PROCESSES` (optional): Number of worker processes for CPU-bound tasks like replay parsing
  - Default: 2
  - Recommended: Set to the number of CPU cores minus one for optimal performance
  - Examples:
    - For 2-core CPU: `WORKER_PROCESSES=1`
    - For 4-core CPU: `WORKER_PROCESSES=3`
    - For 8-core CPU: `WORKER_PROCESSES=7`

## Repository Structure
```
EvoLadderBot/
├── data/
│   ├── locales/
│   │   ├── enUS.json
│   │   ├── koKR.json
│   │   └── zhCN.json
│   └── starcraft/
│
├── src/
│   ├── backend/
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   └── server.py
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── 
│   │   │   ├── 
│   │   │   ├── 
│   │   │   └── 
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── matchmaking.py
│   │       ├── ratings.py
│   │       └── region_mapping.py
│   │
│   ├── bot/
│   │   ├── api/
│   │   ├── interface/
│   │   │   ├── __init__.py
│   │   │   ├── bot_interface_commands.py
│   │   │   ├── bot_interface_main.py
│   │   │   └── bot_interface_views.py
│   │   └── __init__.py
│   │
│   └── utils/
│       ├── __init__.py
│       ├── country_region.py
│       ├── localization_utils.py
│       ├── other_utils.py
│       └── strings_utils.py
│
├── tests/
│   ├── backend/
│   ├── bot/
│   ├── end_to_end/
│   └── utils/
├── .env
├── .gitattributes
├── .gitignore
├── README.md
└── requirements.txt
```