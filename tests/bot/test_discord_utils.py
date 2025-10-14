"""
Tests for discord_utils module.
"""
import unittest
import json
import os
import tempfile
import shutil
from unittest.mock import patch, mock_open
import sys

# Add the src directory to the path so we can import the modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from bot.utils.discord_utils import get_rank_emote


class TestGetRankEmote(unittest.TestCase):
    """Test cases for the get_rank_emote function."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.valid_emotes_data = [
            {
                "name": "s_rank",
                "markdown": "<:s_rank:1427481074606542961>"
            },
            {
                "name": "a_rank", 
                "markdown": "<:a_rank:1427481026447540284>"
            },
            {
                "name": "b_rank",
                "markdown": "<:b_rank:1427481034525511771>"
            },
            {
                "name": "c_rank",
                "markdown": "<:c_rank:1427481041437986966>"
            },
            {
                "name": "d_rank",
                "markdown": "<:d_rank:1427481050229248031>"
            },
            {
                "name": "e_rank",
                "markdown": "<:e_rank:1427481062694715422>"
            },
            {
                "name": "f_rank",
                "markdown": "<:f_rank:1427481066762932255>"
            },
            {
                "name": "u_rank",
                "markdown": "<:u_rank:1427481081585598626>"
            }
        ]
    
    def test_valid_ranks(self):
        """Test that valid ranks return correct Discord emote markdown."""
        test_cases = [
            ("s_rank", "<:s_rank:1427481074606542961>"),
            ("a_rank", "<:a_rank:1427481026447540284>"),
            ("b_rank", "<:b_rank:1427481034525511771>"),
            ("c_rank", "<:c_rank:1427481041437986966>"),
            ("d_rank", "<:d_rank:1427481050229248031>"),
            ("e_rank", "<:e_rank:1427481062694715422>"),
            ("f_rank", "<:f_rank:1427481066762932255>"),
            ("u_rank", "<:u_rank:1427481081585598626>")
        ]
        
        with patch('builtins.open', mock_open(read_data=json.dumps(self.valid_emotes_data))):
            for rank, expected_markdown in test_cases:
                with self.subTest(rank=rank):
                    result = get_rank_emote(rank)
                    self.assertEqual(result, expected_markdown)
    
    def test_invalid_rank(self):
        """Test that invalid ranks return fallback format."""
        invalid_ranks = ["invalid_rank", "x_rank", "z_rank", "nonexistent"]
        
        with patch('builtins.open', mock_open(read_data=json.dumps(self.valid_emotes_data))):
            for rank in invalid_ranks:
                with self.subTest(rank=rank):
                    result = get_rank_emote(rank)
                    self.assertEqual(result, f":{rank}:")
    
    def test_empty_rank(self):
        """Test behavior with empty string rank."""
        with patch('builtins.open', mock_open(read_data=json.dumps(self.valid_emotes_data))):
            result = get_rank_emote("")
            self.assertEqual(result, "::")
    
    def test_none_rank(self):
        """Test behavior with None rank (should handle gracefully)."""
        with patch('builtins.open', mock_open(read_data=json.dumps(self.valid_emotes_data))):
            result = get_rank_emote(None)
            self.assertEqual(result, ":None:")
    
    def test_file_not_found(self):
        """Test behavior when emotes.json file is not found."""
        with patch('builtins.open', side_effect=FileNotFoundError):
            result = get_rank_emote("s_rank")
            self.assertEqual(result, ":s_rank:")
    
    def test_malformed_json(self):
        """Test behavior when emotes.json contains malformed JSON."""
        malformed_json = '{"invalid": json}'
        
        with patch('builtins.open', mock_open(read_data=malformed_json)):
            result = get_rank_emote("s_rank")
            self.assertEqual(result, ":s_rank:")
    
    def test_empty_json_file(self):
        """Test behavior with empty JSON file."""
        with patch('builtins.open', mock_open(read_data="[]")):
            result = get_rank_emote("s_rank")
            self.assertEqual(result, ":s_rank:")
    
    def test_json_with_missing_markdown(self):
        """Test behavior when emote exists but has no markdown field."""
        emotes_with_missing_markdown = [
            {"name": "s_rank"},  # Missing markdown field
            {"name": "a_rank", "markdown": "<:a_rank:123>"}
        ]
        
        with patch('builtins.open', mock_open(read_data=json.dumps(emotes_with_missing_markdown))):
            # Should return fallback for s_rank (missing markdown)
            result_s = get_rank_emote("s_rank")
            self.assertEqual(result_s, ":s_rank:")
            
            # Should return actual markdown for a_rank
            result_a = get_rank_emote("a_rank")
            self.assertEqual(result_a, "<:a_rank:123>")
    
    def test_case_sensitivity(self):
        """Test that rank matching is case sensitive."""
        with patch('builtins.open', mock_open(read_data=json.dumps(self.valid_emotes_data))):
            # These should not match due to case sensitivity
            result_upper = get_rank_emote("S_RANK")
            result_lower = get_rank_emote("s_rank")
            
            self.assertEqual(result_upper, ":S_RANK:")  # Fallback
            self.assertEqual(result_lower, "<:s_rank:1427481074606542961>")  # Actual match
    
    def test_unicode_ranks(self):
        """Test behavior with unicode characters in rank names."""
        unicode_emotes = [
            {"name": "rank_🏆", "markdown": "<:rank_🏆:123>"},
            {"name": "rank_⭐", "markdown": "<:rank_⭐:456>"}
        ]
        
        with patch('builtins.open', mock_open(read_data=json.dumps(unicode_emotes))):
            result = get_rank_emote("rank_🏆")
            self.assertEqual(result, "<:rank_🏆:123>")
            
            result = get_rank_emote("rank_⭐")
            self.assertEqual(result, "<:rank_⭐:456>")
    
    def test_rank_with_special_characters(self):
        """Test behavior with special characters in rank names."""
        special_emotes = [
            {"name": "rank-1", "markdown": "<:rank-1:123>"},
            {"name": "rank_2", "markdown": "<:rank_2:456>"},
            {"name": "rank.3", "markdown": "<:rank.3:789>"}
        ]
        
        with patch('builtins.open', mock_open(read_data=json.dumps(special_emotes))):
            result = get_rank_emote("rank-1")
            self.assertEqual(result, "<:rank-1:123>")
            
            result = get_rank_emote("rank_2")
            self.assertEqual(result, "<:rank_2:456>")
            
            result = get_rank_emote("rank.3")
            self.assertEqual(result, "<:rank.3:789>")


if __name__ == '__main__':
    unittest.main()
