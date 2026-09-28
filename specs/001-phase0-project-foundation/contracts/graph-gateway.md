# Contract: GraphGateway Interface — Phase 0

**Version**: 0.1.0 | **Phase**: 0 | **Date**: 2026-09-25

This document defines the `GraphGateway` interface contract through which all Neo4j graph
database operations flow. No code outside `trace/infrastructure/graph/` MUST import the
`neo4j` driver directly (Constitution §VIII, §XIV).

---

## Interface Definition

**Module**: `trace/infrastructure/graph/gateway.py`

**Mechanism**: Python `Protocol` (structural subtyping, PEP 544)

```python
from typing import Protocol, runtime_checkable
from trace.domain.health import GraphConnectivityState

@runtime_checkable
class GraphGateway(Protocol):
    async def health_check(self) -> GraphConnectivityState: ...
```

---

## `GraphConnectivityState`

**Module**: `trace/domain/health.py`

```python
from enum import Enum

class GraphConnectivityState(str, Enum):
    NOT_CONFIGURED = "not_configured"   # NEO4J_URI absent from config
    REACHABLE      = "reachable"        # Connectivity probe succeeded
    UNREACHABLE    = "unreachable"      # NEO4J_URI present; probe failed
```

The three states are **mutually exclusive**. Exactly one is returned per call.

---

## Operation Contracts

### `health_check() → GraphConnectivityState`

Executes a connectivity probe and returns the current connectivity state.

**Returns**: `GraphConnectivityState` — always one of the three defined states.

**Guarantees**:
1. MUST NOT raise any exception to the caller.
2. MUST return `NOT_CONFIGURED` immediately (without any network call) when `NEO4J_URI` is absent.
3. MUST NOT return `REACHABLE` unless a connectivity probe actually succeeded.
4. MUST NOT fabricate connectivity state — returning `REACHABLE` when the probe was not executed is a constitution violation (§XVII).
5. Logs connection exceptions internally at `WARNING` level before returning `UNREACHABLE`.

---

## Health Probe Implementation

The production `Neo4jGraphGateway.health_check()` uses:

```python
await driver.verify_connectivity()   # raises ServiceUnavailable or AuthError on failure
return GraphConnectivityState.REACHABLE
```

Wrapped in `try/except Exception as e: log.warning(...); return GraphConnectivityState.UNREACHABLE`.

**Why `verify_connectivity()`**: This is a Bolt-level probe that validates the connection
and authentication without executing any Cypher query. It is the correct health probe
for Phase 0 where no graph schema exists.

---

## Known Implementations

| Implementation | Module | Use |
|---|---|---|
| `Neo4jGraphGateway` | `trace/infrastructure/graph/gateway.py` | Production (Bolt/asyncio) |
| `UnconfiguredGraphGateway` | `trace/infrastructure/graph/gateway.py` | When NEO4J_URI absent |
| `StubGraphGateway` | `tests/conftest.py` | Unit tests (configurable state) |

---

## Health Endpoint Integration

The `GET /health` endpoint maps `GraphConnectivityState` to `ServiceStatus` as follows:

| `GraphConnectivityState` | `ServiceStatus.status` | Effect on HTTP code |
|---|---|---|
| `NOT_CONFIGURED` | `"not_configured"` | No effect on 200/503 in Phase 0 |
| `REACHABLE` | `"reachable"` | No effect on 200/503 |
| `UNREACHABLE` | `"unreachable"` | Causes HTTP 503 |

**Phase 0 note**: Neo4j `NOT_CONFIGURED` does not trigger HTTP 503 because Neo4j graph
features are not functional until Phase 3A. This assumption is documented in `spec.md §Assumptions`
and will be revisited when Phase 3A begins.

---

## Future Operations (Phase 3A+)

When the TRACE graph schema is established in Phase 3A, the following operations will be
added to the `GraphGateway` Protocol. They MUST NOT be added in Phase 0:

```python
# Future Phase 3A operations
async def execute_query(
    cypher: str,
    parameters: dict[str, Any],
) -> list[dict[str, Any]]: ...

async def create_node(label: str, properties: dict[str, Any]) -> str: ...
async def create_relationship(...) -> str: ...
```

Adding these operations constitutes a MINOR version bump to this contract.

---

## Prohibited Patterns

- ❌ Any code outside `trace/infrastructure/graph/` importing `neo4j` driver directly
- ❌ `health_check()` returning `REACHABLE` without executing `verify_connectivity()`
- ❌ `health_check()` raising an exception instead of returning a `GraphConnectivityState`
- ❌ Creating Neo4j node labels, relationship types, or indexes in Phase 0

---

## Versioning Policy

- **PATCH**: Documentation only.
- **MINOR**: New optional operations; new `GraphConnectivityState` values (additive).
- **MAJOR**: Signature change to `health_check()`; breaking change to `GraphConnectivityState`.

Current version: **0.1.0**
