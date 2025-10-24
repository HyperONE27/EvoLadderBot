"""
Manual test script for interaction refactoring.

This script will send test messages to your DMs to verify:
1. Queue command captures and stores channel/message IDs
2. Match abort notifications reach both players
3. All terminal states (abort/complete/conflict) work correctly

Run this with the bot online and use /queue to test.
"""

import asyncio
import discord
from discord.ext import commands

# Test user IDs
TEST_USER_1 = 218147282875318274
TEST_USER_2 = 354878201232752640

async def test_queue_id_tracking(bot: commands.Bot):
    """
    Test that queue command properly tracks channel and message IDs.
    
    Manual test:
    1. Use /queue in your DM
    2. Select a race and join queue
    3. Check console output for "Capture message context" logs
    """
    print("\n=== Test 1: Queue ID Tracking ===")
    print("Manual steps:")
    print("1. Use /queue in your DM")
    print("2. Select a race and join queue")
    print("3. Look for console output:")
    print("   - 'capture_message_context'")
    print("   - Channel ID and Message ID should be logged")
    print()

async def test_abort_notifications_both_players(bot: commands.Bot):
    """
    Test that abort notifications reach BOTH players.
    
    Manual test:
    1. Both test users join queue
    2. Wait for match
    3. One player aborts
    4. Check that BOTH players' UIs update
    """
    print("\n=== Test 2: Abort Notifications (Both Players) ===")
    print("Manual steps:")
    print(f"1. User {TEST_USER_1} uses /queue and joins")
    print(f"2. User {TEST_USER_2} uses /queue and joins")
    print("3. Wait for match to be found")
    print("4. User 1 clicks 'Abort Match' and confirms")
    print("5. VERIFY: Both users see 'Match Aborted' UI update")
    print("6. VERIFY: Both users receive the abort embed in their DMs")
    print()

async def test_prune_immediate_response(bot: commands.Bot):
    """
    Test that /prune sends immediate response.
    
    Manual test:
    1. Use /prune in your DM
    2. You should immediately see "Analyzing Messages..." embed
    3. After analysis, it should update with confirmation buttons
    """
    print("\n=== Test 3: Prune Immediate Response ===")
    print("Manual steps:")
    print("1. Use /prune in your DM")
    print("2. VERIFY: Immediately see 'Analyzing Messages...' with disabled buttons")
    print("3. VERIFY: After ~2 seconds, message updates with actual count and enabled buttons")
    print("4. VERIFY: No timeout errors occur")
    print()

async def test_persistent_updates(bot: commands.Bot):
    """
    Test that match updates work even after long delays.
    
    Manual test:
    1. Get into a match
    2. Wait > 15 minutes (or manually set a long timeout)
    3. Report result or abort
    4. Verify UI still updates correctly
    """
    print("\n=== Test 4: Persistent Updates (Long Running) ===")
    print("Manual steps:")
    print("1. Get into a match")
    print("2. Wait > 15 minutes (interaction token expires)")
    print("3. Report result or abort")
    print("4. VERIFY: UI still updates correctly")
    print("5. VERIFY: No 'Unknown Webhook' errors in console")
    print()

async def send_test_guide_to_dm(bot: commands.Bot, user_id: int):
    """Send testing guide to user's DM."""
    try:
        user = await bot.fetch_user(user_id)
        
        embed = discord.Embed(
            title="🧪 Interaction Refactoring - Manual Test Guide",
            description="Follow these tests to verify the refactoring works correctly.",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="Test 1: Queue ID Tracking",
            value="1. Use `/queue` and join\n2. Check console for 'capture_message_context' logs",
            inline=False
        )
        
        embed.add_field(
            name="Test 2: Abort Notifications",
            value="1. Both test users join queue\n2. Get matched\n3. One aborts\n4. VERIFY: Both see UI update",
            inline=False
        )
        
        embed.add_field(
            name="Test 3: Prune Immediate Response",
            value="1. Use `/prune`\n2. VERIFY: Immediate 'Analyzing...' message\n3. VERIFY: Updates with real data",
            inline=False
        )
        
        embed.add_field(
            name="Test 4: Long-Running Updates",
            value="1. Get in match\n2. Wait >15 min\n3. Report/abort\n4. VERIFY: Still works",
            inline=False
        )
        
        embed.add_field(
            name="Expected Console Output",
            value="```\n[Matchmaker] Triggering immediate completion check for match X after abort.\n🔍 CHECK: Match X reports: p1=..., p2=...\n🚫 Match X was aborted\n  -> Notifying 2 callbacks for match X abort.\n```",
            inline=False
        )
        
        await user.send(embed=embed)
        print(f"✅ Sent test guide to user {user_id}")
        
    except Exception as e:
        print(f"❌ Failed to send test guide to user {user_id}: {e}")

async def main():
    """Main test coordinator."""
    print("=" * 60)
    print("MANUAL TEST GUIDE - Interaction Refactoring")
    print("=" * 60)
    
    # Print all test instructions
    await test_queue_id_tracking(None)
    await test_abort_notifications_both_players(None)
    await test_prune_immediate_response(None)
    await test_persistent_updates(None)
    
    print("\n" + "=" * 60)
    print("What to Look For in Console:")
    print("=" * 60)
    print()
    print("✅ GOOD - After queue join:")
    print("   capture_message_context")
    print("   capture_message_context_complete")
    print()
    print("✅ GOOD - After match abort:")
    print("   [Matchmaker] Triggering immediate completion check for match X after abort")
    print("   🔍 CHECK: Match X reports: p1=-3, p2=-1, result=-1")
    print("   🚫 Match X was aborted")
    print("   -> Notifying 2 callbacks for match X abort")
    print()
    print("❌ BAD - Any of these:")
    print("   discord.errors.NotFound: 404 Not Found (error code: 10015): Unknown Webhook")
    print("   AttributeError: 'MatchFoundView' object has no attribute 'last_interaction'")
    print("   -> Notifying 1 callbacks (should be 2!)")
    print()
    print("=" * 60)
    print("Testing Instructions:")
    print("=" * 60)
    print()
    print("The bot needs to be running for these tests.")
    print("You can run the tests in order, or focus on specific ones.")
    print()
    print("For Test 2 (abort notifications), you'll need both test accounts online.")
    print()

if __name__ == "__main__":
    asyncio.run(main())

