# Test Plan: High-Risk Regression Characterization Suite (Expanded V2)

## 1. Objective

This document outlines a sparse but wide-coverage test suite designed to characterize the current behavior of the bot's highest-risk areas. The goal is to create a safety net that can reliably detect regressions in critical user-facing flows and backend services before they reach production.

The tests will heavily utilize mocking to isolate components and simulate complex user interactions and backend states without requiring a live Discord connection or database. This expanded version (V2) adds coverage for match result reporting, replay uploads, startup/shutdown sequences, and other core commands.

---

## 2. Test Structure

All characterization tests will be located in the `tests/characterize/` directory.

-   `tests/characterize/TEST_PLAN.md` (This document)
-   `tests/characterize/test_prune_flow.py`
-   `tests/characterize/test_queue_flow.py`
-   `tests/characterize/test_match_flow.py` **(New)**
-   `tests/characterize/test_data_service.py`
-   `tests/characterize/test_startup_shutdown.py` **(New)**
-   `tests/characterize/test_race_conditions.py`
-   `tests/characterize/test_other_commands.py` **(New)**

---

## 3. Mocking Strategy Guide

We will use Python's `unittest.mock` library, specifically `patch`, `MagicMock`, and `AsyncMock`.

-   **`@patch('path.to.dependency')`**: Used to replace a class or function within a specific test. This is the primary tool for isolating components.
-   **`AsyncMock`**: Used to mock `async def` methods. It allows us to `await` the mock and assert that it was called.
-   **`MagicMock`**: Used for synchronous objects and methods.
-   **`side_effect`**: Used to make a mock raise an exception or return different values on subsequent calls.
-   **`return_value`**: Used to specify what a mocked function or method should return.

### Core Mocks

A set of standard mocks will be used across multiple test files.

#### Mocking `discord.Interaction`

This is the most important mock. It simulates a user's interaction with a command or component.

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def mock_interaction():
    """Creates a comprehensive, reusable mock of discord.Interaction."""
    interaction = AsyncMock(spec=discord.Interaction)
    
    # User and channel info
    interaction.user = MagicMock(spec=discord.User)
    interaction.user.id = 123456789
    interaction.user.name = "TestUser"
    interaction.channel = AsyncMock(spec=discord.TextChannel)
    interaction.channel.id = 987654321
    
    # Core response methods
    interaction.response = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.edit_message = AsyncMock()
    
    # Follow-up and original response methods
    interaction.followup = AsyncMock()
    interaction.followup.send = AsyncMock()
    
    # This is critical for the persistent message editing pattern
    mock_message = AsyncMock(spec=discord.Message)
    mock_message.id = 1122334455
    interaction.original_response = AsyncMock(return_value=mock_message)
    
    return interaction
```

#### Mocking Backend Services

Services like `DataAccessService` should be patched at the point of import within the module being tested.

```python
# In test_prune_flow.py
from unittest.mock import patch, MagicMock

@patch('src.bot.commands.prune_command.DataAccessService')
def test_prune_with_mocked_das(mock_das_class):
    # The class is replaced. We can control the instance it returns.
    mock_das_instance = MagicMock()
    mock_das_class.get_instance.return_value = mock_das_instance
    
    # Now, configure the instance's methods
    mock_das_instance.get_player_info.return_value = {"player_name": "TestUser", ...}
    
    # ... run test ...
```

---

## 4. Test Suite Details

### `test_prune_flow.py`

-   **Objective**: Characterize the `/prune` command's interaction with the Discord API.
-   **Key Risk**: Interaction timeouts and incorrect message deletion logic.

| Test Case | Mocking Strategy | Success Criteria |
| :--- | :--- | :--- |
| **`test_prune_sends_immediate_deferral`** | - Mock `interaction`.<br>- Mock `interaction.channel.history` to return an async iterator. | 1. `interaction.response.defer()` is called **exactly once**.<br>2. `interaction.followup.send()` is called for the initial "Analyzing" embed. |
| **`test_prune_handles_no_messages`** | - Mock `interaction`.<br>- Mock `channel.history` to be empty. | 1. The flow completes by editing the initial message to show "No Messages to Prune". |
| **`test_prune_confirmation_flow`** | - Mock `interaction`.<br>- Mock `channel.history` with mock messages.<br>- Mock `message.delete` on the message objects. | 1. The initial message is edited to show the confirmation embed and buttons.<br>2. Simulating a confirm click correctly calls `message.delete()` for each targeted message. |
| **`test_prune_protects_active_queue_message`** (Strengthened) | - Mock `channel.history` with a message whose ID is registered via `register_active_queue_message`. | 1. The registered message is **not** included in the `messages_to_delete` list.<br>2. The confirmation embed shows a count that excludes the protected message. |
| **`test_prune_protects_very_old_queue_message`** (Strengthened) | - Mock `channel.history` with a queue-related message older than the `QUEUE_MESSAGE_PROTECTION_DAYS` cutoff. | 1. The old queue message **is** included in the `messages_to_delete` list. |


### `test_queue_flow.py`

-   **Objective**: Characterize the matchmaking queue lifecycle from a user's perspective.
-   **Key Risks**: State management, task cleanup, and symmetrical UI updates.

| Test Case | Mocking Strategy | Success Criteria |
| :--- | :--- | :--- |
| **`test_queue_happy_path`** | - Mock `interaction`.<br>- Mock `DataAccessService` to provide preferences.<br>- Mock `notification_service.subscribe` to return a mock `asyncio.Queue`.<br>- Mock `match_completion_service` callbacks. | 1. `JoinQueueButton` callback creates `QueueSearchingView`.<br>2. `_listen_for_match` is started.<br>3. Pushing a mock `MatchResult` to the queue creates a `MatchFoundView`.<br>4. The original message is edited to show the match view. |
| **`test_cancel_queue_button_cleans_up`** (Strengthened) | - Mock `interaction`.<br>- Mock `matchmaker.remove_player`. | 1. Simulating a "Cancel Queue" click calls `matchmaker.remove_player`.<br>2. The view's `deactivate()` method is called.<br>3. The original message is edited back to the initial `QueueView`. |
| **`test_queue_view_timeout_cleans_up_tasks`** | - Create a `QueueSearchingView` with a short timeout.<br>- Mock `matchmaker.remove_player`. | 1. The view's `on_timeout` method is called.<br>2. `matchmaker.remove_player` is called.<br>3. `deactivate()` is called, which cancels background tasks.<br>4. No orphaned `asyncio.Task` objects are left. |
| **`test_player_cannot_double_queue`** (Strengthened) | - Mock `queue_searching_view_manager.has_view` to return `True`. | 1. The `/queue` command immediately responds with a "You are already in a queue" error embed. |

### `test_match_flow.py` (New File)

-   **Objective**: Characterize the in-match UI flows for aborts, result reporting, and replay uploads.
-   **Key Risks**: Asymmetrical UI updates, conflicting state, and upload handling.

| Test Case | Mocking Strategy | Success Criteria |
| :--- | :--- | :--- |
| **`test_abort_is_symmetrical`** | - Simulate two users matched.<br>- Mock `matchmaker.abort_match`.<br>- Mock `match_completion_service.check_match_completion` to trigger callbacks. | 1. Two `MatchFoundView` instances are created.<br>2. When one user aborts, `handle_completion_notification` is called on **both** view instances.<br>3. `_edit_original_message` is called for both views with an "aborted" embed. |
| **`test_result_reporting_flow`** | - Mock `DataAccessService.submit_match_result`. | 1. Selecting a result from the dropdown enables the "Confirm" button.<br>2. Clicking "Confirm" calls `DataAccessService.submit_match_result`.<br>3. The UI updates to show "Waiting for opponent...". |
| **`test_conflicting_results_flow`** | - Simulate one player reporting WIN and the other reporting WIN.<br>- Mock `match_completion_service` to trigger the conflict callback. | 1. The `handle_completion_notification` method is called on both views with `event_type="conflict"`.<br>2. Both players' embeds are updated to show the conflict state and instructions. |
| **`test_replay_upload_flow`** | - Mock `interaction` to include a mock `discord.Attachment`.<br>- Mock `attachment.read()` to return mock replay data.<br>- Mock `replay_service.process_replay`. | 1. The "Upload Replay" button callback is invoked.<br>2. `replay_service.process_replay` is called with the replay data.<br>3. The UI updates to show "Replay processed". |
| **`test_invalid_replay_upload`** | - Mock `replay_service.process_replay` to raise a `ReplayParsingError`. | 1. The view catches the exception.<br>2. A follow-up message is sent to the user indicating the replay was invalid. |

### `test_data_service.py`

-   **Objective**: Characterize the `DataAccessService`'s durability and concurrency safety.
-   **Key Risks**: Race conditions, data loss, and blocking I/O.

| Test Case | Mocking Strategy | Success Criteria |
| :--- | :--- | :--- |
| **`test_singleton_is_async_safe`** | - Use `asyncio.gather` to call `DataAccessService()` concurrently.<br>- Patch the `_initialize` method to track call count. | 1. `_initialize` is called **exactly once**.<br>2. All coroutines receive the exact same object instance. |
| **`test_writes_are_queued_and_non_blocking`** (Strengthened) | - Mock the internal `_write_queue`. | 1. Calling a write method (e.g., `create_player`) returns in <5ms.<br>2. The `_write_queue.put_nowait` method was called with the correct `WriteJob`. |
| **`test_failed_write_is_logged`** (Strengthened) | - Mock `_process_write_job` to raise a database exception.<br>- Mock the failed writes logger. | 1. The `_db_writer_worker` catches the exception.<br>2. The failed `WriteJob` is written to the configured failed writes log file. |
| **`test_read_after_write_consistency`** (Strengthened) | - Call `create_player`.<br>- Immediately call `get_player_info`. | 1. The write call updates the in-memory Polars DataFrame immediately.<br>2. The subsequent read call returns the correct, newly written data without needing to wait for the DB write. |

### `test_startup_shutdown.py` (New File)

-   **Objective**: Characterize the bot's startup data loading and graceful shutdown.
-   **Key Risks**: Incomplete data loading, data loss from unflushed write queues.

| Test Case | Mocking Strategy | Success Criteria |
| :--- | :--- | :--- |
| **`test_startup_initializes_das`** | - Mock `DataAccessService.initialize_async`.<br>- Run the bot's `main.on_ready` event handler. | 1. `DataAccessService.initialize_async` is called exactly once during startup. |
| **`test_das_loads_all_tables_on_init`** | - Mock `DatabaseReader` methods (`get_all_players`, etc.) to return mock data.<br>- Call `DataAccessService.initialize_async`. | 1. All `get_all_*` methods on the `DatabaseReader` are called.<br>2. The internal DataFrames (`_players_df`, `_mmrs_df`, etc.) are populated with the mock data. |
| **`test_shutdown_flushes_write_queue`** | - Mock `DataAccessService._write_queue` to contain several mock jobs.<br>- Mock `_process_write_job`.<br>- Call `DataAccessService.shutdown()`. | 1. The `shutdown` method waits until the `_write_queue` is empty.<br>2. `_process_write_job` is called for every item that was in the queue. |

### `test_race_conditions.py`

-   **Objective**: Characterize the atomicity of critical state transitions.
-   **Key Risks**: Inconsistent state from concurrent operations.

| Test Case | Mocking Strategy | Success Criteria |
| :--- | :--- | :--- |
| **`test_abort_and_complete_race`** | - Use `asyncio.gather` to concurrently run `check_match_completion` for abort and complete events.<br>- Mock `DataAccessService` to control the match state. | 1. An `asyncio.Lock` for the `match_id` is acquired.<br>2. `DataAccessService.update_match_status` is called only once to set the first terminal state.<br>3. The second operation sees the terminal state and does not proceed. |
| **`test_player_queues_during_match_is_rejected`** (Strengthened) | - Simulate a player being in an active `MatchFoundView`.<br>- Have that same player invoke the `/queue` command. | 1. The `queue_command` checks `match_results` or a similar active match registry.<br>2. The command returns an error embed without creating a `QueueView`. |

### `test_other_commands.py` (New File)

-   **Objective**: Provide baseline coverage for other important user-facing commands.
-   **Key Risks**: Incorrect data display, command failures with no user feedback.

| Test Case | Mocking Strategy | Success Criteria |
| :--- | :--- | :--- |
| **`test_leaderboard_command`** | - Mock `DataAccessService.get_leaderboard_data` to return a sample leaderboard. | 1. The command correctly formats the leaderboard data into an embed with ranks, names, and MMR. |
| **`test_leaderboard_empty_state`** | - Mock `DataAccessService.get_leaderboard_data` to return an empty list. | 1. The command sends a clean embed stating that the leaderboard is empty. |
| **`test_stats_command`** | - Mock `DataAccessService.get_player_stats` to return sample stats for a user. | 1. The command correctly formats the stats (W-L, MMR, rank, etc.) into an embed. |
| **`test_stats_for_new_player`** | - Mock `DataAccessService.get_player_stats` to return `None` or empty data. | 1. The command sends an embed indicating the player has no stats yet. |
