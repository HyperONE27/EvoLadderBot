# Database Abstraction Implementation Plan

## Goal
Enable transparent switching between SQLite (local dev) and PostgreSQL (production) using the same codebase.

## Current State Analysis

### ✅ What's Already Compatible
- **Schema Design**: Both schemas use compatible types (TEXT, INTEGER, BOOLEAN, TIMESTAMP)
- **Query Logic**: Named parameters and SQL logic can work for both
- **Data Models**: Services already use typed data, not database-specific types

### ⚠️ What Needs Abstraction

#### 1. **Connection Management**
- SQLite: `sqlite3.connect(path)`
- PostgreSQL: `psycopg2.connect(connection_string)`

#### 2. **Parameter Placeholders**
- SQLite: Uses `?` for positional, `:name` for named
- PostgreSQL (psycopg2): Uses `%s` for positional, `%(name)s` for named

#### 3. **Row Handling**
- SQLite: `sqlite3.Row` object
- PostgreSQL: `psycopg2.extras.RealDictRow` or tuple

#### 4. **Auto-increment IDs**
- SQLite: `INTEGER PRIMARY KEY AUTOINCREMENT`
- PostgreSQL: `SERIAL` or `GENERATED ALWAYS AS IDENTITY`

#### 5. **RETURNING Clauses**
- SQLite: Doesn't support `RETURNING` (use `cursor.lastrowid`)
- PostgreSQL: Supports `RETURNING id, created_at` etc.

---

## Implementation Strategy

### Phase 1: Create Database Adapter Layer (2-3 hours)

**Goal**: Abstract connection and query execution

**Files to Create**:
```
src/backend/db/
├── adapters/
│   ├── __init__.py
│   ├── base_adapter.py          # Abstract base class
│   ├── sqlite_adapter.py        # SQLite implementation
│   └── postgresql_adapter.py    # PostgreSQL implementation
```

**Key Components**:

1. **Base Adapter Interface**
```python
class DatabaseAdapter(ABC):
    @abstractmethod
    def connect(self) -> Connection
    
    @abstractmethod
    def execute_query(self, query: str, params: dict) -> List[dict]
    
    @abstractmethod
    def execute_write(self, query: str, params: dict) -> int  # returns row count
    
    @abstractmethod
    def execute_insert(self, query: str, params: dict) -> int  # returns last ID
    
    @abstractmethod
    def format_placeholder(self, name: str) -> str  # :name or %(name)s
```

2. **SQLite Adapter**
- Uses `sqlite3`
- Converts `Row` to `dict`
- Handles `:named` placeholders
- Uses `cursor.lastrowid` for inserts

3. **PostgreSQL Adapter**
- Uses `psycopg2`
- Uses `RealDictCursor` for dict results
- Handles `%(named)s` placeholders
- Uses `RETURNING id` for inserts

### Phase 2: Update Database Base Class (1 hour)

**File**: `src/backend/db/db_reader_writer.py`

**Changes**:
```python
from src.backend.db.adapters import get_adapter
from src.bot.config import DATABASE_TYPE

class Database:
    def __init__(self):
        self.adapter = get_adapter(DATABASE_TYPE)
    
    @contextmanager
    def get_connection(self):
        conn = self.adapter.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
```

### Phase 3: Query Placeholder Abstraction (2-3 hours)

**Two Approaches** (choose one):

#### Approach A: Query Templating (Simpler)
Keep all queries as-is with named parameters, convert at runtime:

```python
def _convert_query(self, query: str, db_type: str) -> str:
    """Convert :name placeholders to database-specific format"""
    if db_type == "postgresql":
        # Convert :name to %(name)s
        return re.sub(r':(\w+)', r'%(\1)s', query)
    return query  # SQLite uses :name natively
```

#### Approach B: Query Builder (More robust, but more work)
Create a light query builder that generates database-specific SQL:

```python
class Query:
    def where(self, field: str, value: Any):
        placeholder = self.adapter.format_placeholder(field)
        self.conditions.append(f"{field} = {placeholder}")
        self.params[field] = value
```

**Recommendation**: **Approach A** - Simpler, less code change, good enough

### Phase 4: Update All Queries (3-4 hours)

**Current**: ~50+ methods in `DatabaseReader` and `DatabaseWriter`

**Strategy**: Update incrementally, method by method

**Example transformation**:

Before:
```python
def get_player(self, discord_uid: int) -> Optional[dict]:
    with self.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM players WHERE discord_uid = :discord_uid
        """, {"discord_uid": discord_uid})
        row = cur.fetchone()
        return dict(row) if row else None
```

After:
```python
def get_player(self, discord_uid: int) -> Optional[dict]:
    query = "SELECT * FROM players WHERE discord_uid = :discord_uid"
    results = self.adapter.execute_query(query, {"discord_uid": discord_uid})
    return results[0] if results else None
```

### Phase 5: Handle Database-Specific Features (1-2 hours)

**Features to handle**:

1. **Boolean Values**
   - SQLite: 0/1 integers
   - PostgreSQL: true/false booleans
   - Solution: Adapter normalizes to Python bool

2. **Timestamps**
   - SQLite: ISO strings
   - PostgreSQL: TIMESTAMP type
   - Solution: Both parse to Python datetime

3. **RETURNING Clauses** (for inserts)
   - SQLite: Use `cursor.lastrowid`
   - PostgreSQL: Use `RETURNING id`
   - Solution: Adapter abstracts via `execute_insert()`

### Phase 6: Testing Strategy (2-3 hours)

**Test Files**:
```
tests/backend/db/
├── test_adapter_sqlite.py
├── test_adapter_postgresql.py
├── test_database_reader.py       # Run against both DBs
└── test_database_writer.py       # Run against both DBs
```

**Testing Approach**:
1. Unit tests for each adapter
2. Integration tests that run against BOTH databases
3. Use pytest fixtures to switch DB type
4. Docker container for PostgreSQL in CI

```python
@pytest.fixture(params=["sqlite", "postgresql"])
def db_type(request):
    return request.param

def test_get_player(db_type):
    # Test works with both databases
    reader = DatabaseReader(db_type=db_type)
    player = reader.get_player(12345)
    assert player["discord_uid"] == 12345
```

### Phase 7: Migration Scripts (1 hour)

**Create**:
```
src/backend/db/migrations/
├── migrate_sqlite_to_postgres.py   # Copy data from SQLite → PostgreSQL
└── init_postgres.py                # Initialize PostgreSQL from scratch
```

---

## Implementation Order

### Priority 1: Core Infrastructure (Day 1: 6-8 hours)
- [x] Phase 1: Create adapter layer
- [x] Phase 2: Update Database base class  
- [x] Phase 3: Query placeholder conversion

### Priority 2: Query Migration (Day 2-3: 8-12 hours)
- [x] Phase 4: Update all queries (incremental)
- [x] Phase 5: Handle DB-specific features

### Priority 3: Validation (Day 4: 4-6 hours)
- [x] Phase 6: Testing
- [x] Phase 7: Migration scripts

**Total Estimated Time**: 18-26 hours of focused work

---

## Benefits After Implementation

### Development Workflow
```bash
# Local development with SQLite
DATABASE_TYPE=sqlite
SQLITE_DB_PATH=evoladder.db

# Local testing with PostgreSQL
DATABASE_TYPE=postgresql
DATABASE_URL=postgresql://localhost:5432/evoladder_test

# Production (Railway + Supabase)
DATABASE_TYPE=postgresql
DATABASE_URL=postgresql://...supabase.co:5432/postgres
```

### Zero Code Changes Required
Switch databases by changing **one environment variable**: `DATABASE_TYPE`

### Future-Proof Architecture
- Easy to add MySQL, MariaDB, etc.
- Can run parallel databases (SQLite backup + PostgreSQL primary)
- Simplified testing with in-memory SQLite

---

## Risk Mitigation

### Testing Strategy
- Run full test suite against BOTH databases before deploying
- Keep SQLite as fallback during transition
- Test data migration thoroughly

### Rollback Plan
- Keep current SQLite code in git history
- Can revert if PostgreSQL issues arise
- Adapter pattern allows quick database switching

### Data Safety
- Never delete SQLite file until PostgreSQL proven stable
- Export SQLite data before migration
- Test migration on copy of production data first

---

## Decision Points

### Question 1: Query Approach
**Recommendation**: Approach A (Template conversion)
- Faster to implement
- Less code change
- Good enough for our use case

### Question 2: ORM vs Adapter
**Recommendation**: Adapter pattern (not full ORM)
- Less refactoring needed
- Maintains existing query logic
- Better performance for our needs
- Can migrate to ORM later if needed

### Question 3: Migration Timing
**Recommendation**: Incremental migration
- Update adapters first
- Migrate one service at a time
- Test each service thoroughly
- Reduces risk of breaking changes

---

## Success Criteria

✅ **Must Have**:
- [ ] Bot runs on SQLite locally
- [ ] Bot runs on PostgreSQL on Railway
- [ ] All existing tests pass on both databases
- [ ] No query syntax errors
- [ ] Data integrity maintained

✅ **Should Have**:
- [ ] < 5% performance difference between databases
- [ ] Migration script successfully copies all data
- [ ] Clear error messages for DB connection issues
- [ ] Comprehensive test coverage (>80%)

✅ **Nice to Have**:
- [ ] Automatic database type detection
- [ ] Query performance monitoring
- [ ] Database connection pooling
- [ ] Read replica support (future)

---

## Next Steps

1. **Review and approve this plan**
2. **Start with Phase 1**: Create adapter layer
3. **Test adapter with simple queries**
4. **Incrementally migrate existing queries**
5. **Deploy to Railway with PostgreSQL**

Ready to start? 🚀

