"""
Database migration script: Add admin_actions table for audit logging.

This script creates the admin_actions table used by the AdminService to log
all administrative actions for audit trail purposes.

Run this script once to add the table to your database.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.backend.db.database_adapter import get_database_adapter


def create_admin_actions_table():
    """Create the admin_actions table and indexes."""
    
    adapter = get_database_adapter()
    
    print("Creating admin_actions table...")
    
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS admin_actions (
        id                  SERIAL PRIMARY KEY,
        admin_discord_uid   BIGINT NOT NULL,
        admin_username      TEXT NOT NULL,
        action_type         TEXT NOT NULL,
        target_player_uid   BIGINT,
        target_match_id     INTEGER,
        action_details      JSONB NOT NULL,
        reason              TEXT,
        performed_at        TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        
        FOREIGN KEY (admin_discord_uid) REFERENCES players(discord_uid)
    );
    """
    
    adapter.execute_write(create_table_sql, {})
    print("✅ admin_actions table created")
    
    print("Creating indexes...")
    
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_admin_actions_performed_at ON admin_actions(performed_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_admin_actions_admin ON admin_actions(admin_discord_uid)",
        "CREATE INDEX IF NOT EXISTS idx_admin_actions_target_player ON admin_actions(target_player_uid)",
        "CREATE INDEX IF NOT EXISTS idx_admin_actions_target_match ON admin_actions(target_match_id)",
        "CREATE INDEX IF NOT EXISTS idx_admin_actions_type ON admin_actions(action_type)"
    ]
    
    for index_sql in indexes:
        adapter.execute_write(index_sql, {})
    
    print("✅ Indexes created")
    print("\n✅ Migration complete!")
    print("\nAdmin actions will now be logged to the admin_actions table.")
    print("You can query this table to view audit history.")


def verify_table():
    """Verify the table was created successfully."""
    adapter = get_database_adapter()
    
    result = adapter.execute_query(
        """
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'admin_actions'
        ORDER BY ordinal_position
        """,
        {}
    )
    
    if result:
        print("\nTable structure:")
        for row in result:
            print(f"  - {row['column_name']}: {row['data_type']}")
    else:
        print("❌ Table verification failed - table not found")


if __name__ == "__main__":
    try:
        create_admin_actions_table()
        verify_table()
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)

