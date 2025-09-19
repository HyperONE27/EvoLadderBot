"""Region mapping service for server selection."""
import json
import pandas as pd
from pathlib import Path
from typing import Optional, Tuple, Dict, List


class RegionMappingService:
    """Service for determining optimal game servers based on player regions."""
    
    def __init__(self):
        """Initialize the region mapping service."""
        self._load_cross_table()
        self._load_regions()
    
    def _load_cross_table(self):
        """Load the cross-table data for server selection."""
        # Try to load from Excel file first, fallback to creating default
        try:
            data_path = Path(__file__).parent.parent.parent.parent / "data" / "misc"
            xlsx_path = data_path / "cross_table.xlsx"
            
            if xlsx_path.exists():
                self.cross_table = pd.read_excel(xlsx_path, index_col=0)
            else:
                # Create a default cross-table if file doesn't exist
                self.cross_table = self._create_default_cross_table()
        except Exception:
            self.cross_table = self._create_default_cross_table()
    
    def _load_regions(self):
        """Load region data."""
        data_path = Path(__file__).parent.parent.parent.parent / "data" / "misc"
        with open(data_path / "regions.json", "r", encoding="utf-8") as f:
            regions_list = json.load(f)
        
        # Create lookup dictionaries
        self.regions_by_code = {r["code"]: r for r in regions_list}
        self.regions_by_number = {r["number"]: r for r in regions_list}
    
    def _create_default_cross_table(self) -> pd.DataFrame:
        """Create a default cross-table for server selection."""
        # Default servers based on geographic proximity
        # This is a simplified version - actual cross-table should be more nuanced
        regions = ["NAW", "NAC", "NAE", "CAM", "SAM", "EUW", "EUE", "AFR", 
                  "MEA", "SEA", "KRJ", "CHN", "THM", "OCE", "USB", "FER"]
        
        # Initialize with all NAC (Central North America) as default
        data = {}
        for region in regions:
            data[region] = ["NAC"] * len(regions)
        
        df = pd.DataFrame(data, index=regions)
        
        # Set up some logical server selections
        # North America regions prefer NAC
        for na_region in ["NAW", "NAC", "NAE"]:
            df.loc[na_region, na_region] = na_region
        
        # Europe regions prefer EUW
        for eu_region in ["EUW", "EUE"]:
            df.loc[eu_region, eu_region] = eu_region
            df.loc["EUW", "EUE"] = "EUW"
            df.loc["EUE", "EUW"] = "EUW"
        
        # Asia regions prefer KRJ
        for asia_region in ["KRJ", "CHN", "THM", "SEA"]:
            df.loc[asia_region, asia_region] = asia_region
            df.loc["KRJ", ["CHN", "THM", "SEA"]] = "KRJ"
            df.loc[["CHN", "THM", "SEA"], "KRJ"] = "KRJ"
        
        # Oceania prefers OCE
        df.loc["OCE", "OCE"] = "OCE"
        df.loc["OCE", ["SEA", "THM"]] = "SEA"
        df.loc[["SEA", "THM"], "OCE"] = "SEA"
        
        # South America prefers SAM
        df.loc["SAM", "SAM"] = "SAM"
        df.loc["SAM", ["NAE", "CAM"]] = "NAE"
        
        return df
    
    def get_best_server(self, region1: str, region2: str) -> str:
        """
        Get the best server for two players based on their regions.
        
        Args:
            region1: Region code of player 1
            region2: Region code of player 2
            
        Returns:
            Region code of the best server
        """
        if region1 not in self.cross_table.index or region2 not in self.cross_table.columns:
            # Fallback to NAC if regions not found
            return "NAC"
        
        return self.cross_table.loc[region1, region2]
    
    def get_server_name(self, server_code: str) -> str:
        """Get the full name of a server from its code."""
        region = self.regions_by_code.get(server_code, {})
        return region.get("name", f"Unknown ({server_code})")
    
    def get_all_servers(self) -> List[Dict[str, str]]:
        """Get all available servers."""
        return [
            {"code": code, "name": region["name"]}
            for code, region in self.regions_by_code.items()
        ]
    
    def estimate_ping_quality(self, region1: str, region2: str, server: str) -> str:
        """
        Estimate the ping quality for a match.
        
        Returns one of: "Excellent", "Good", "Fair", "Poor"
        """
        # Simple heuristic based on geographic distance
        # In reality, this would use actual latency data
        
        # If both players are in the same region as the server
        if region1 == server and region2 == server:
            return "Excellent"
        
        # If one player is in the server region
        if region1 == server or region2 == server:
            return "Good"
        
        # Check if regions are geographically close
        close_regions = {
            "NAW": ["NAC", "NAE"],
            "NAC": ["NAW", "NAE"], 
            "NAE": ["NAC", "NAW", "CAM"],
            "EUW": ["EUE"],
            "EUE": ["EUW"],
            "KRJ": ["CHN", "THM"],
            "CHN": ["KRJ", "THM", "SEA"],
            "THM": ["CHN", "KRJ", "SEA"],
            "SEA": ["THM", "CHN", "OCE"],
            "OCE": ["SEA"],
        }
        
        region1_close = close_regions.get(region1, [])
        region2_close = close_regions.get(region2, [])
        
        if (server in region1_close or region1 in close_regions.get(server, [])) and \
           (server in region2_close or region2 in close_regions.get(server, [])):
            return "Fair"
        
        return "Poor"
