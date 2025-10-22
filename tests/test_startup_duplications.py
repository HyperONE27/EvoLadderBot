#!/usr/bin/env python3
"""
Test script to identify startup duplications.
"""

import sys
import os
import asyncio
import io
import contextlib

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.bot.bot_setup import initialize_backend_services
from src.bot.main import EvoLadderBot

async def test_startup_duplications():
    """Test for startup duplications"""
    print("🧪 Testing Startup Duplications")
    print("=" * 50)
    
    # Capture stdout to see what's being printed
    captured_output = io.StringIO()
    
    with contextlib.redirect_stdout(captured_output):
        try:
            # Create a mock bot instance
            import discord
            intents = discord.Intents.default()
            intents.message_content = True
            bot = EvoLadderBot(command_prefix="!", intents=intents)
            
            # Initialize backend services
            await initialize_backend_services(bot)
            
            # Get the captured output
            output = captured_output.getvalue()
            
            # Count occurrences of key messages
            storage_init_count = output.count("[Storage] Initialized with bucket: replays")
            memory_monitor_count = output.count("[Memory Monitor]")
            db_pool_count = output.count("[DB Pool] Connection pool initialized successfully")
            
            print(f"📊 Duplication Analysis:")
            print(f"  Storage init: {storage_init_count} times")
            print(f"  Memory Monitor messages: {memory_monitor_count} times")
            print(f"  DB Pool init: {db_pool_count} times")
            
            # Check for specific duplications
            if storage_init_count > 1:
                print(f"❌ Storage service initialized {storage_init_count} times (should be 1)")
            else:
                print(f"✅ Storage service initialized {storage_init_count} time (correct)")
                
            if db_pool_count > 1:
                print(f"❌ DB Pool initialized {db_pool_count} times (should be 1)")
            else:
                print(f"✅ DB Pool initialized {db_pool_count} time (correct)")
                
            # Look for duplicate memory monitor messages
            memory_lines = [line for line in output.split('\n') if '[Memory Monitor]' in line]
            unique_memory_lines = set(memory_lines)
            
            if len(memory_lines) != len(unique_memory_lines):
                print(f"❌ Duplicate memory monitor messages found:")
                for line in memory_lines:
                    if memory_lines.count(line) > 1:
                        print(f"    '{line}' appears {memory_lines.count(line)} times")
            else:
                print(f"✅ No duplicate memory monitor messages")
                
        except Exception as e:
            print(f"❌ Error during testing: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_startup_duplications())
    if success:
        print("\n🎉 Startup duplication test completed!")
    else:
        print("\n💥 Startup duplication test failed!")
        sys.exit(1)
