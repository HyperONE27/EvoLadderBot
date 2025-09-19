"""Main entry point to start the EvoLadderBot."""
import asyncio
import os
import sys
from dotenv import load_dotenv

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def main():
    """Main startup function."""
    # Load environment variables
    load_dotenv()
    
    # Check for required environment variables
    if not os.getenv("EVOLADDERBOT_TOKEN"):
        print("❌ Error: EVOLADDERBOT_TOKEN not found in environment!")
        print("Please create a .env file with your Discord bot token.")
        print("See env.example for the required format.")
        return
    
    if not os.getenv("DATABASE_URL"):
        print("❌ Error: DATABASE_URL not found in environment!")
        print("Please create a .env file with your database connection string.")
        print("See env.example for the required format.")
        return
    
    print("🚀 Starting EvoLadderBot...")
    
    # Initialize database
    print("📊 Initializing database...")
    try:
        from src.backend.db import init_db
        await init_db()
        print("✅ Database initialized!")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return
    
    # Check if we need to populate initial data
    try:
        from src.backend.db.create_table import populate_initial_data
        await populate_initial_data()
    except Exception as e:
        print(f"⚠️ Could not populate initial data: {e}")
    
    # Start the bot
    print("🤖 Starting Discord bot...")
    from src.bot.interface.interface_main import bot
    
    token = os.getenv("EVOLADDERBOT_TOKEN")
    
    try:
        await bot.start(token)
    except KeyboardInterrupt:
        print("\n👋 Shutting down bot...")
    except Exception as e:
        print(f"❌ Bot error: {e}")
    finally:
        await bot.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
