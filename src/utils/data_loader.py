import json
from pathlib import Path
from typing import List, Dict, Optional

class DataLoader:
    """Centralized data loading for countries and regions"""
    
    _instance = None
    _countries = None
    _regions = None
    _common_countries = None
    _country_dict = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._countries is None:
            self._load_data()
    
    def _load_data(self):
        """Load all data files"""
        data_path = Path(__file__).parent.parent.parent / "data" / "misc"
        
        with open(data_path / "countries.json", "r", encoding="utf-8") as f:
            self._countries = json.load(f)
        
        with open(data_path / "regions.json", "r", encoding="utf-8") as f:
            self._regions = json.load(f)
        
        # Create lookup dictionaries
        self._country_dict = {c['code']: c for c in self._countries}
        
        # Filter common countries
        self._common_countries = [c for c in self._countries if c.get('common', False)]
        # Sort common countries alphabetically, but put "Other" at the end
        self._common_countries = sorted(
            [c for c in self._common_countries if c['code'] != 'XX'],
            key=lambda x: x['name']
        )
        other = next((c for c in self._countries if c['code'] == 'XX'), None)
        if other:
            self._common_countries.append(other)
    
    def get_all_countries(self) -> List[Dict]:
        """Get all countries"""
        return self._countries.copy()
    
    def get_common_countries(self) -> List[Dict]:
        """Get common countries for setup"""
        return self._common_countries.copy()
    
    def get_regions(self) -> List[Dict]:
        """Get all regions"""
        return self._regions.copy()
    
    def get_country_by_code(self, code: str) -> Optional[Dict]:
        """Get country by code"""
        return self._country_dict.get(code)
    
    def get_region_by_code(self, code: str) -> Optional[Dict]:
        """Get region by code"""
        return next((r for r in self._regions if r['code'] == code), None)
    
    def search_countries(self, query: str, limit: int = 25) -> List[Dict]:
        """Search countries by name"""
        query_lower = query.lower()
        # Exclude "Other" from search results
        results = [
            c for c in self._countries 
            if query_lower in c['name'].lower() and c['code'] != 'XX'
        ]
        return results[:limit]