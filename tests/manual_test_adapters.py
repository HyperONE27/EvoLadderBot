"""
Quick test script for database adapters.

Run this to verify adapters work before migrating db_reader_writer.py
"""

from src.backend.db.adapters import get_adapter
from src.bot.config import DATABASE_TYPE

print("="*70)
print("TESTING DATABASE ADAPTERS")
print("="*70)

# Get the configured adapter
adapter = get_adapter(DATABASE_TYPE)

print(f"\nDatabase Type: {DATABASE_TYPE}")
print(f"Adapter: {adapter.__class__.__name__}")
print(f"Connection: {adapter.get_connection_string()}")

# Test query conversion
test_queries = [
    "SELECT * FROM players WHERE discord_uid = :uid",
    "INSERT INTO players (discord_uid, discord_username) VALUES (:uid, :username)",
    "UPDATE players SET player_name = :name WHERE discord_uid = :uid",
]

print("\n" + "-"*70)
print("QUERY CONVERSION TESTS")
print("-"*70)

for query in test_queries:
    converted = adapter.convert_query(query)
    print(f"\nOriginal:  {query[:80]}")
    print(f"Converted: {converted[:80]}")
    if DATABASE_TYPE == "postgresql":
        assert "%(uid)s" in converted or "%(name)s" in converted or "%(username)s" in converted
        print("[OK] PostgreSQL placeholders detected")
    else:
        assert ":uid" in converted or ":name" in converted or ":username" in converted
        print("[OK] SQLite placeholders preserved")

# Test actual query execution
print("\n" + "-"*70)
print("DATABASE CONNECTION TEST")
print("-"*70)

try:
    # Test a simple query
    results = adapter.execute_query("SELECT COUNT(*) as count FROM players")
    player_count = results[0]["count"] if results else 0
    
    print(f"\n[OK] Query executed successfully")
    print(f"[OK] Players in database: {player_count}")
    
    # Test connection context manager
    with adapter.get_connection() as conn:
        print(f"[OK] Connection context manager works")
    
    print("\n" + "="*70)
    print("[SUCCESS] ALL ADAPTER TESTS PASSED")
    print("="*70 + "\n")
    
except Exception as e:
    print(f"\n[ERROR] Test failed: {e}")
    import traceback
    traceback.print_exc()
    print("\n" + "="*70)
    print("[FAILED] ADAPTER TESTS FAILED")
    print("="*70 + "\n")

