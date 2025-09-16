# src/utils/update_countries_json.py
# Run this once to update your countries.json file

import json
from pathlib import Path

DATA_PATH = Path(__file__).parent.parent.parent / "data"

COMMON_COUNTRIES = {
    "AU": "Australia", "AT": "Austria", "BY": "Belarus", "BO": "Bolivia",
    "BA": "Bosnia and Herzegovina", "BR": "Brazil", "BG": "Bulgaria", "CA": "Canada",
    "CL": "Chile", "CN": "China", "CO": "Colombia", "CR": "Costa Rica",
    "HR": "Croatia", "CU": "Cuba", "CZ": "Czechia", "DK": "Denmark",
    "EC": "Ecuador", "EG": "Egypt", "FI": "Finland", "FR": "France",
    "DE": "Germany", "HK": "Hong Kong", "HU": "Hungary", "IN": "India",
    "ID": "Indonesia", "IL": "Israel", "IT": "Italy", "JP": "Japan",
    "KZ": "Kazakhstan", "LV": "Latvia", "LT": "Lithuania", "MY": "Malaysia",
    "MX": "Mexico", "NL": "Netherlands", "NO": "Norway", "PE": "Peru",
    "PH": "Philippines", "PL": "Poland", "RU": "Russia", "SG": "Singapore",
    "KR": "South Korea", "ES": "Spain", "SE": "Sweden", "TW": "Taiwan",
    "UA": "Ukraine", "GB": "United Kingdom", "US": "United States", "VN": "Vietnam"
}

with open(DATA_PATH / "misc" / "countries.json", "r", encoding="utf-8") as f:
    countries = json.load(f)

for country in countries:
    country["common"] = country["code"] in COMMON_COUNTRIES

# Add "Other" option
countries.append({"code": "XX", "name": "Other", "common": True})

with open(DATA_PATH / "misc" / "countries.json", "w", encoding="utf-8") as f:
    json.dump(countries, f, indent=2, ensure_ascii=False)