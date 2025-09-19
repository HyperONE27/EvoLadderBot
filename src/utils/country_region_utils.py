import json
from pathlib import Path
from typing import List, Dict, Optional

class CountryLookup:
    """Enhanced country lookup with integrated data management"""
    
    _instance = None
    _countries = None
    _common_countries = None
    _country_dict = None
    
    def __new__(cls, countries_list_path="data/misc/countries.json"):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, countries_list_path="data/misc/countries.json"):
        if self._countries is None:
            self._load_data(countries_list_path)
        
        # Build dicts in both directions for fast lookup (maintaining backward compatibility)
        self.code_to_name = {c["code"]: c["name"] for c in self.countries}
        self.name_to_code = {c["name"]: c["code"] for c in self.countries}

    def _load_data(self, countries_list_path):
        """Load countries data"""
        # Go up from src/utils to project root, then to data/misc
        data_path = Path(__file__).parent.parent.parent / "data" / "misc"
        
        with open(data_path / "countries.json", "r", encoding="utf-8") as f:
            self._countries = json.load(f)
        
        # Create lookup dictionary
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
        
        # Set instance variables
        self.countries = self._countries

    def get_sorted_countries(self):
        """Get all countries sorted by name"""
        return sorted(self.countries, key=lambda x: x["name"])

    def get_country_from_code(self, code: str):
        """Get country name from code (backward compatibility)"""
        return self.code_to_name.get(code)

    def get_code_from_country(self, name: str):
        """Get country code from name (backward compatibility)"""
        return self.name_to_code.get(name)
    
    def get_common_countries(self) -> List[Dict]:
        """Get common countries for setup"""
        return self._common_countries.copy()
    
    def get_country_by_code(self, code: str) -> Optional[Dict]:
        """Get full country data by code"""
        return self._country_dict.get(code)
    
    def search_countries(self, query: str, limit: int = 25) -> List[Dict]:
        """Search countries by name"""
        query_lower = query.lower()
        # Exclude "Other" from search results
        results = [
            c for c in self._countries 
            if query_lower in c['name'].lower() and c['code'] != 'XX'
        ]
        return results[:limit]

class RegionLookup:
    """Region lookup functionality"""
    
    _instance = None
    _regions = None
    _region_dict = None
    
    def __new__(cls, regions_list_path="data/misc/regions.json"):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, regions_list_path="data/misc/regions.json"):
        if self._regions is None:
            self._load_data(regions_list_path)
        
        # Build dicts in both directions for fast lookup
        self.code_to_name = {r["code"]: r["name"] for r in self.regions}
        self.name_to_code = {r["name"]: r["code"] for r in self.regions}
        self.code_to_number = {r["code"]: r["number"] for r in self.regions}
        self.number_to_code = {r["number"]: r["code"] for r in self.regions}

    def _load_data(self, regions_list_path):
        """Load regions data"""
        # Go up from src/utils to project root, then to data/misc
        data_path = Path(__file__).parent.parent.parent / "data" / "misc"
        
        with open(data_path / "regions.json", "r", encoding="utf-8") as f:
            self._regions = json.load(f)
        
        # Create lookup dictionary
        self._region_dict = {r['code']: r for r in self._regions}
        
        # Set instance variables
        self.regions = self._regions

    def get_sorted_regions(self):
        """Get all regions sorted by name"""
        return sorted(self.regions, key=lambda x: x["name"])

    def get_region_from_code(self, code: str):
        """Get region name from code"""
        return self.code_to_name.get(code)

    def get_code_from_region(self, name: str):
        """Get region code from name"""
        return self.name_to_code.get(name)
    
    def get_region_by_code(self, code: str) -> Optional[Dict]:
        """Get full region data by code"""
        return self._region_dict.get(code)
    
    def get_region_by_number(self, number: int) -> Optional[Dict]:
        """Get region data by number"""
        code = self.number_to_code.get(number)
        return self.get_region_by_code(code) if code else None
    
    def get_all_regions(self) -> List[Dict]:
        """Get all regions"""
        return self.regions.copy()

if __name__ == "__main__":
    # Test the enhanced functionality
    country_lookup = CountryLookup()
    region_lookup = RegionLookup()
    
    print("Country tests:")
    print(f"Other country code: {country_lookup.get_code_from_country('Other')}")
    print(f"XX country name: {country_lookup.get_country_from_code('XX')}")
    print(f"Common countries count: {len(country_lookup.get_common_countries())}")
    
    print("\nRegion tests:")
    print(f"NAW region name: {region_lookup.get_region_from_code('NAW')}")
    print(f"Western North America code: {region_lookup.get_code_from_region('Western North America')}")
    print(f"Region by number 1: {region_lookup.get_region_by_number(1)}")