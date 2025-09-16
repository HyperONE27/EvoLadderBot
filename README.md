# EvoLadderBot
A Discord ladder bot for SC: Evo Complete. Backend is engineered to allow for expansion to web client later.

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