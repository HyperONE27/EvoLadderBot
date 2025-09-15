# src/utils/country_organization.py

import json
from pathlib import Path
from typing import Dict, List, Tuple
import math

DATA_PATH = Path(__file__).parent.parent.parent / "data"

# Continent mappings for countries
CONTINENT_MAPPING = {
    "Africa": [
        "DZ", "AO", "BJ", "BW", "BF", "BI", "CM", "CV", "CF", "TD", "KM", "CG", "CD", "CI", "DJ", "EG", "GQ", "ER", "ET", "GA", "GM", "GH", "GN", "GW", "KE", "LS", "LR", "LY", "MG", "MW", "ML", "MR", "MU", "YT", "MA", "MZ", "NA", "NE", "NG", "RE", "RW", "ST", "SN", "SC", "SL", "SO", "ZA", "SS", "SD", "SZ", "TZ", "TG", "TN", "UG", "ZM", "ZW", "EH"
    ],
    "Asia": [
        "AF", "AM", "AZ", "BH", "BD", "BT", "BN", "KH", "CN", "CY", "GE", "HK", "IN", "ID", "IR", "IQ", "IL", "JP", "JO", "KZ", "KW", "KG", "LA", "LB", "MO", "MY", "MV", "MN", "MM", "NP", "KP", "OM", "PK", "PS", "PH", "QA", "SA", "SG", "KR", "LK", "SY", "TW", "TJ", "TH", "TL", "TR", "TM", "AE", "UZ", "VN", "YE"
    ],
    "Europe": [
        "AL", "AD", "AT", "BY", "BE", "BA", "BG", "HR", "CZ", "DK", "EE", "FO", "FI", "FR", "DE", "GI", "GR", "GL", "GG", "VA", "HU", "IS", "IE", "IM", "IT", "JE", "XK", "LV", "LI", "LT", "LU", "MK", "MT", "MD", "MC", "ME", "NL", "NO", "PL", "PT", "RO", "RU", "SM", "RS", "SK", "SI", "ES", "SJ", "SE", "CH", "UA", "GB", "AX"
    ],
    "North America": [
        "AI", "AG", "AW", "BS", "BB", "BZ", "BM", "BQ", "VG", "CA", "KY", "CR", "CU", "CW", "DM", "DO", "SV", "GL", "GD", "GP", "GT", "HT", "HN", "JM", "MQ", "MX", "MS", "NI", "PA", "PR", "BL", "KN", "LC", "MF", "PM", "VC", "SX", "TT", "TC", "US", "VI"
    ],
    "South America": [
        "AR", "BO", "BR", "CL", "CO", "EC", "FK", "GF", "GY", "PY", "PE", "SR", "UY", "VE"
    ],
    "Oceania": [
        "AS", "AU", "CX", "CC", "CK", "FJ", "PF", "GU", "KI", "MH", "FM", "NR", "NC", "NZ", "NU", "NF", "MP", "PW", "PG", "PN", "WS", "SB", "TK", "TO", "TV", "VU", "WF"
    ],
    "Antarctica": [
        "AQ", "BV", "TF", "HM", "GS"
    ]
}

def organize_countries_by_continent() -> Dict[str, List[dict]]:
    """Organize countries by continent"""
    with open(DATA_PATH / "misc" / "countries.json", "r", encoding="utf-8") as f:
        countries = json.load(f)
    
    country_dict = {c['code']: c for c in countries}
    organized = {}
    
    for continent, codes in CONTINENT_MAPPING.items():
        continent_countries = []
        for code in codes:
            if code in country_dict:
                continent_countries.append(country_dict[code])
        
        # Sort by name
        continent_countries.sort(key=lambda x: x['name'])
        organized[continent] = continent_countries
    
    return organized

def split_countries_alphabetically(countries: List[dict], max_per_group: int = 25) -> List[Tuple[str, List[dict]]]:
    """Split countries into alphabetical groups if there are too many"""
    if len(countries) <= max_per_group:
        return [("All", countries)]
    
    # Group by first letter
    letter_groups = {}
    for country in countries:
        first_letter = country['name'][0].upper()
        if first_letter not in letter_groups:
            letter_groups[first_letter] = []
        letter_groups[first_letter].append(country)
    
    # Combine small groups to reach approximately max_per_group
    result = []
    current_group = []
    current_label_parts = []
    
    for letter in sorted(letter_groups.keys()):
        if len(current_group) + len(letter_groups[letter]) <= max_per_group:
            current_group.extend(letter_groups[letter])
            current_label_parts.append(letter)
        else:
            if current_group:
                if len(current_label_parts) == 1:
                    label = current_label_parts[0]
                else:
                    label = f"{current_label_parts[0]}-{current_label_parts[-1]}"
                result.append((label, current_group))
            
            current_group = letter_groups[letter]
            current_label_parts = [letter]
    
    # Add the last group
    if current_group:
        if len(current_label_parts) == 1:
            label = current_label_parts[0]
        else:
            label = f"{current_label_parts[0]}-{current_label_parts[-1]}"
        result.append((label, current_group))
    
    return result

# Pre-compute the organization
ORGANIZED_COUNTRIES = organize_countries_by_continent()