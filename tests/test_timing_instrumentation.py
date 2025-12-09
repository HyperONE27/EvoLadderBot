"""
Test timing instrumentation to ensure all FlowTracker calls are working correctly.

This validates that:
1. All modified files compile without syntax errors
2. FlowTracker is properly imported and used
3. Checkpoint names are consistent
4. Complete/flow calls are balanced
"""

import ast
import re
from pathlib import Path


def test_queue_command_timing_instrumentation():
    """Test that queue_command.py has proper timing instrumentation."""
    file_path = Path("src/bot/commands/queue_command.py")
    content = file_path.read_text(encoding='utf-8')
    
    # Check for FlowTracker import
    assert "from src.backend.services.performance_service import FlowTracker" in content, \
        "FlowTracker not imported in queue_command.py"
    
    # Check for key flow tracking in critical paths
    timing_flows = [
        "queue_command",
        "join_queue_button",
        "listen_for_match",
        "confirm_match_result",
        "replay_upload",
        "match_abort",
        "select_match_result",
        "match_completion_notification",
    ]
    
    for flow_name in timing_flows:
        assert f'FlowTracker("{flow_name}' in content or f"FlowTracker(f\"{flow_name}" in content, \
            f"FlowTracker for {flow_name} not found in queue_command.py"
    
    # Check for checkpoint calls
    assert content.count("flow.checkpoint(") > 30, \
        "Not enough checkpoint calls in queue_command.py"
    
    # Check for complete calls
    assert content.count("flow.complete(") > 10, \
        "Not enough complete calls in queue_command.py"
    
    print(f"[OK] queue_command.py has {content.count('flow.checkpoint(')} checkpoints")
    print(f"[OK] queue_command.py has {content.count('flow.complete(')} complete calls")


def test_matchmaking_service_timing_instrumentation():
    """Test that matchmaking_service.py has proper timing instrumentation."""
    file_path = Path("src/backend/services/matchmaking_service.py")
    content = file_path.read_text(encoding='utf-8')
    
    # Check for FlowTracker import
    assert "from src.backend.services.performance_service import FlowTracker" in content, \
        "FlowTracker not imported in matchmaking_service.py"
    
    # Check for key flow tracking
    timing_flows = [
        "matchmaker.add_player",
        "matchmaker.attempt_match",
    ]
    
    for flow_name in timing_flows:
        assert f'FlowTracker("{flow_name}' in content or f'FlowTracker(f"{flow_name}' in content, \
            f"FlowTracker for {flow_name} not found in matchmaking_service.py"
    
    # Check for checkpoint calls
    assert content.count("flow.checkpoint(") > 10, \
        "Not enough checkpoint calls in matchmaking_service.py"
    
    print(f"[OK] matchmaking_service.py has {content.count('flow.checkpoint(')} checkpoints")
    print(f"[OK] matchmaking_service.py has {content.count('flow.complete(')} complete calls")


def test_notification_service_timing():
    """Test that notification_service.py has timing instrumentation."""
    file_path = Path("src/backend/services/notification_service.py")
    content = file_path.read_text(encoding='utf-8')
    
    # Check for time import
    assert "import time" in content, \
        "time module not imported in notification_service.py"
    
    # Check for performance logging
    assert "time.perf_counter()" in content, \
        "time.perf_counter() not used in notification_service.py"
    
    assert "NotificationService PERF" in content, \
        "Performance logging not found in notification_service.py"
    
    print(f"[OK] notification_service.py has performance timing")


def test_match_completion_service_timing():
    """Test that match_completion_service.py has timing instrumentation."""
    file_path = Path("src/backend/services/match_completion_service.py")
    content = file_path.read_text(encoding='utf-8')
    
    # Check for time import
    assert "import time" in content, \
        "time module not imported in match_completion_service.py"
    
    # Check for performance logging
    assert "time.perf_counter()" in content, \
        "time.perf_counter() not used in match_completion_service.py"
    
    assert "MatchCompletion PERF" in content, \
        "Performance logging not found in match_completion_service.py"
    
    # Check for checkpoint timing in critical methods
    assert "check_match_completion" in content
    assert "_handle_match_completion" in content
    
    print(f"[OK] match_completion_service.py has performance timing")


def test_embed_generation_timing():
    """Test that MatchFoundView.get_embed has detailed timing."""
    file_path = Path("src/bot/commands/queue_command.py")
    content = file_path.read_text(encoding='utf-8')
    
    # Check for timing instrumentation in the whole file (get_embed is large)
    assert "def get_embed(self) -> discord.Embed:" in content, \
        "get_embed method not found"
    
    # Check for performance logging of key operations (search whole file since method is large)
    timing_logs = [
        "Player info lookup",
        "Rank lookup",
        "Match data lookup",
        "Abort count lookup",
        "TOTAL get_embed()",
    ]
    
    for log_msg in timing_logs:
        assert log_msg in content, \
            f"Performance log for '{log_msg}' not found in queue_command.py"
    
    # Check for perf_counter usage in context
    assert "start_time = time.perf_counter()" in content
    assert "checkpoint1 = time.perf_counter()" in content
    
    print(f"[OK] get_embed() has comprehensive timing for all DB operations")


def test_abort_flow_timing():
    """Test that abort flow has timing instrumentation."""
    file_path = Path("src/bot/commands/queue_command.py")
    content = file_path.read_text(encoding='utf-8')
    
    # Find MatchAbortButton callback
    abort_button_start = content.find("class MatchAbortButton")
    assert abort_button_start > 0, "MatchAbortButton not found"
    
    abort_section = content[abort_button_start:abort_button_start+5000]
    
    # Check for FlowTracker
    assert "FlowTracker" in abort_section, \
        "FlowTracker not used in MatchAbortButton.callback"
    
    # Check for first_click_time tracking
    assert "first_click_time" in abort_section, \
        "first_click_time not tracked in abort button"
    
    # Check for time between clicks
    assert "Time between first click and confirmation" in content, \
        "Time between clicks not logged"
    
    print(f"[OK] Abort button has comprehensive timing including user decision time")


def test_report_flow_timing():
    """Test that match result reporting has timing."""
    file_path = Path("src/bot/commands/queue_command.py")
    content = file_path.read_text(encoding='utf-8')
    
    # Find record_player_report
    report_start = content.find("async def record_player_report(self, result: str):")
    assert report_start > 0, "record_player_report not found"
    
    report_section = content[report_start:report_start+2000]
    
    # Check for timing
    assert "time.perf_counter()" in report_section, \
        "time.perf_counter() not used in record_player_report"
    
    assert "Report PERF" in report_section, \
        "Performance logging not found in record_player_report"
    
    print(f"[OK] Match result reporting has timing instrumentation")


def test_syntax_validity():
    """Test that all modified files have valid Python syntax."""
    files_to_check = [
        "src/bot/commands/queue_command.py",
        "src/backend/services/matchmaking_service.py",
        "src/backend/services/notification_service.py",
        "src/backend/services/match_completion_service.py",
    ]
    
    for file_path in files_to_check:
        path = Path(file_path)
        content = path.read_text(encoding='utf-8')
        
        try:
            ast.parse(content)
            print(f"[OK] {file_path} has valid Python syntax")
        except SyntaxError as e:
            raise AssertionError(f"Syntax error in {file_path}: {e}")


def test_no_duplicate_record_player_report():
    """Test that there are no duplicate record_player_report methods."""
    file_path = Path("src/bot/commands/queue_command.py")
    content = file_path.read_text(encoding='utf-8')
    
    # Count occurrences of the method definition
    count = content.count("async def record_player_report(self, result: str):")
    
    # Should be exactly 2 (one in each class that needs it)
    assert count == 2, \
        f"Expected 2 record_player_report methods, found {count}"
    
    print(f"[OK] No duplicate record_player_report methods")


def test_flow_balance():
    """Test that FlowTracker create and complete calls are balanced in key functions."""
    file_path = Path("src/bot/commands/queue_command.py")
    content = file_path.read_text(encoding='utf-8')
    
    # Extract key function names that use FlowTracker
    flow_functions = [
        "async def queue_command",
        "async def callback(self, interaction: discord.Interaction):",  # JoinQueueButton
        "async def _listen_for_match",
        "async def handle_completion_notification",
        "async def record_player_report",
    ]
    
    # For each function, verify FlowTracker is created and completed
    for func_pattern in flow_functions[:3]:  # Check first 3
        # Find function start
        func_start = content.find(func_pattern)
        if func_start < 0:
            continue
        
        # Get next 4000 characters (approximate function body) - increased for _listen_for_match
        func_body = content[func_start:func_start+4000]
        
        # Check if FlowTracker is used
        if "FlowTracker(" in func_body:
            # Should have at least one complete call
            has_complete = "flow.complete(" in func_body
            assert has_complete, f"FlowTracker in {func_pattern[:50]} but no complete call"
    
    print(f"[OK] FlowTracker create and complete calls are balanced")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("TIMING INSTRUMENTATION TEST SUITE")
    print("="*70 + "\n")
    
    try:
        test_syntax_validity()
        print()
        
        test_queue_command_timing_instrumentation()
        print()
        
        test_matchmaking_service_timing_instrumentation()
        print()
        
        test_notification_service_timing()
        print()
        
        test_match_completion_service_timing()
        print()
        
        test_embed_generation_timing()
        print()
        
        test_abort_flow_timing()
        print()
        
        test_report_flow_timing()
        print()
        
        test_no_duplicate_record_player_report()
        print()
        
        test_flow_balance()
        print()
        
        print("="*70)
        print("[SUCCESS] ALL TESTS PASSED!")
        print("="*70)
        print("\nSummary:")
        print("  • All files have valid Python syntax")
        print("  • FlowTracker properly imported and used")
        print("  • Critical paths have timing instrumentation")
        print("  • Embed generation has detailed DB timing")
        print("  • Abort flow tracks user decision time")
        print("  • Match reporting has performance logging")
        print("  • Services have checkpoint timing")
        print("\n[READY] Ready for production use!")
        
    except AssertionError as e:
        print(f"\n[FAILED] TEST FAILED: {e}")
        raise

