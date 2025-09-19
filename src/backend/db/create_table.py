"""Script to create database tables."""
import asyncio
import os
from dotenv import load_dotenv
from sqlalchemy import text
from .database import async_engine, init_db
from .models import Base, MapPool

# Default map pool for initial setup
DEFAULT_MAPS = [
    "Eclipse",
    "Polypoid",
    "Goldenaura", 
    "Heartbreak Ridge",
    "Neo Sylphid",
    "Radiance",
    "Vermeer",
    "Butter",
    "Dominator",
]


async def create_tables():
    """Create all database tables."""
    print("Creating database tables...")
    await init_db()
    print("✅ Tables created successfully!")


async def populate_initial_data():
    """Populate initial data like map pool."""
    from .database import get_db_session
    
    async with get_db_session() as session:
        # Check if map pool already exists
        result = await session.execute(text("SELECT COUNT(*) FROM map_pool"))
        count = result.scalar()
        
        if count == 0:
            print("Populating initial map pool...")
            for idx, map_name in enumerate(DEFAULT_MAPS):
                map_entry = MapPool(
                    map_name=map_name,
                    is_active=True,
                    order_index=idx
                )
                session.add(map_entry)
            
            await session.commit()
            print(f"✅ Added {len(DEFAULT_MAPS)} maps to the pool!")
        else:
            print(f"ℹ️ Map pool already contains {count} maps.")


async def main():
    """Main function to set up the database."""
    load_dotenv()
    
    # Create tables
    await create_tables()
    
    # Populate initial data
    await populate_initial_data()
    
    print("\n🎉 Database setup complete!")


if __name__ == "__main__":
    asyncio.run(main())
