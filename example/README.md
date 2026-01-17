# Orchestration Architecture Example

This example demonstrates a basic orchestration backend architecture with centralized state and stateless services.

## Architecture Overview

The architecture is organized into three main components:

### 1. **Orchestrator** (`orchestrator/`)
The orchestrator owns all state and controls the flow of operations:

- **`state_manager.py`** - Centralized state owner. All state lives here and is modified only through defined methods.
- **`transition_manager.py`** - Defines allowed state transitions and enforces them.
- **`service_orchestrator.py`** - Coordinates calls to stateless services and manages the overall workflow.
- **`__init__.py`** - Main orchestrator that brings all components together.

### 2. **Services** (`services/`)
Stateless services that perform pure operations:

- **`task_validator.py`** - Validates task data (no state, pure functions)
- **`task_processor.py`** - Processes tasks (no state, pure functions)
- **`task_persistence.py`** - Persists results (no state, pure functions)

### 3. **Core** (`core/`)
Shared types and configuration:

- **`types.py`** - Task and result type definitions
- **`config.py`** - Configuration including valid state transitions

### 4. **API** (`api/`)
HTTP API server to demonstrate the orchestration:

- **`server.py`** - Simple HTTP server with demo functionality

## Key Principles

1. **Centralized State**: All state lives in `StateManager`. Only the orchestrator can modify it.

2. **Stateless Services**: Services are pure functions with no internal state. They operate on data passed to them.

3. **Controlled Transitions**: The `TransitionManager` defines valid state changes. Invalid transitions are rejected.

4. **Orchestrated Flow**: The `ServiceOrchestrator` controls when and how services are called, ensuring proper sequencing.

## Task Lifecycle

```
CREATED → VALIDATED → PROCESSING → COMPLETED
    ↓        ↓           ↓           ↓
  FAILED    FAILED     FAILED     (terminal)
```

## Running the Example

```bash
cd example/backend/api
python server.py
```

This will run a demo showing:
1. Task creation
2. Task processing through the orchestration pipeline
3. Final state inspection

## Key Benefits

- **Clear Separation**: State management is separate from business logic
- **Controlled Flow**: All state transitions are validated and controlled
- **Testable Services**: Stateless services are easy to unit test
- **Observable**: Centralized state makes the system easy to debug and monitor
- **Scalable**: Stateless services can be scaled independently

## File Structure
```
example/
├── backend/
│   ├── orchestrator/     # State-owning orchestration logic
│   │   ├── state_manager.py
│   │   ├── transition_manager.py
│   │   ├── service_orchestrator.py
│   │   └── __init__.py
│   ├── services/         # Stateless service implementations
│   │   ├── task_validator.py
│   │   ├── task_processor.py
│   │   └── task_persistence.py
│   ├── core/            # Shared types and config
│   │   ├── types.py
│   │   └── config.py
│   └── api/             # API demonstration
│       └── server.py
└── README.md
```
