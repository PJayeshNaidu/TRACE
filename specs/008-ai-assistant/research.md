# Research & Architectural Decisions: Feature 008 — AI Assistant (TRACE F10)

**Feature Branch**: `008-ai-assistant` | **Date**: 2026-10-05 | **Spec Reference**: [spec.md](spec.md)

This document records the architectural investigations, trade-off analyses, and design decisions for implementing the **TRACE F10 Contextual Q&A Layer**.

---

## Decision 1: Deterministic Symbol Extraction & Multi-Hop Cypher Retrieval vs Vector DBs

### Context
The assistant must answer questions like *"Why is component X affected?"*, *"What depends on X?"*, or *"Show all callers of X"*. We need a strategy to identify target symbols and retrieve factual context from the repository without hallucination.

### Decision
Use **deterministic regex & exact symbol-table indexing** combined with **parameterized Neo4j Cypher queries ($G$ and $G^T$ 1-hop and 2-hop traversals)** and relational SQL queries against PostgreSQL. Do **NOT** use Pinecone, Chroma, pgvector, or vector embedding pipelines in V1.

### Rationale
1. **Zero Hallucination on Graph Topology (TRACE Constitution Principle I & II)**: Vector embeddings capture semantic similarity, not exact structural call chains. A semantic search might retrieve `process_payment_v2` because the docstrings are similar, but fail to report that `web_api` directly calls `process_payment_v1`. Graph traversal ($CALLS$, $IMPORTS$, $DEPENDS_ON$) is 100% deterministic and auditable.
2. **Zero Infrastructure Overhead**: TRACE already runs PostgreSQL and Neo4j. Adding a vector store increases container memory footprint, requires embedding computation on every analysis run, and adds operational failure modes.
3. **Speed and Precision**: For code symbols (e.g. `trace.services.planner.UpgradePlanService.generate_plan`), exact and token-boundary regex matching against the AST symbol registry yields exact matches in $< 5\text{ms}$.

### Alternatives Evaluated
- **Vector DB / RAG Pipeline (Chroma / Pinecone)**: Rejected for V1. High setup overhead, non-deterministic similarity ranking, slow indexing on large repos, and prone to retrieving irrelevant code chunks.
- **Full Repository Context Dumping**: Rejected. Passing entire file contents exceeds free-tier model context limits (1,500 tokens) and causes severe rate limiting.

---

## Decision 2: OpenRouter Free-Tier Prompt Engineering & Compact Token Budgeting (< 1,500 tokens)

### Context
The assistant must operate reliably on free-tier models (default: `mistralai/mistral-7b-instruct:free` via OpenRouter). Free models have strict rate limits (typically 20 requests/minute) and smaller context windows where instruction following degrades rapidly if context is noisy.

### Decision
Implement a **Compact Context Pruner & Token Budgeter** in `backend/src/trace/services/assistant/retrieval.py` that limits the assembled JSON evidence bundle to **< 1,500 tokens (approx. 5,000–6,000 characters)**:
1. **Target Subgraph Pruning**: Extract only the target symbol, direct 1-hop callers, 1-hop callees, and at most top-5 2-hop transitive paths.
2. **Tabular Metric Aggregation**: Compress F05 risk factors into compact key-value dictionaries (e.g., `{"risk": "HIGH", "score": 78, "factors": ["breaking_signature", "fan_in_12"]}`).
3. **Strict System Prompt & Schema Guard**:
   ```text
   You are TRACE Code Intelligence Assistant. Synthesize a concise answer using ONLY the supplied JSON evidence.
   If evidence is missing, state it clearly. Do not invent code dependencies.
   ```
4. **Dialogue Turn Trimming**: Keep at most the last 2 conversation turns (user/assistant pairs).

### Rationale
- Small free models (7B parameters) excel when given dense, highly structured JSON facts with clear boundaries, rather than unstructured multi-thousand-line code dumps.
- Strict token budgeting guarantees responses return within 2–3 seconds and prevents HTTP 429 rate limit exhaustion.

### Alternatives Evaluated
- **Multi-Agent LangGraph Debate Workflow**: Rejected. Spawning multiple subagents consumes too many tokens and multiplies latency by 4x–5x, causing timeouts on free-tier APIs.
- **Raw Diff Dumping**: Rejected. Diffs for medium PRs often exceed 10,000 lines. The retrieval layer must only extract AST delta metadata (e.g. `parameters_added: ['timeout']`).

---

## Decision 3: Typed Structured Sources Attribution

### Context
Users must be able to verify every assertion made by the assistant against concrete repository evidence.

### Decision
The assistant service compiles a structured `list[EvidenceSource]` during retrieval and attaches it directly to `AssistantQueryResponse`:
```python
class EvidenceSource(BaseModel):
    type: Literal["graph", "risk", "plan", "diff"]
    identifier: str
    summary: str
    metadata: dict[str, Any]
```
In the Observatory UI, each source renders as an interactive Neo-Brutalist badge with direct deep-links / hover inspect cards.

### Rationale
- Decouples raw evidence from narrative text. Even if the LLM produces a stylistic variation, the user always sees the exact database IDs, Cypher paths, and task IDs used to generate the answer.
- Complies with Constitution Principle IV (Explainability and Evidence).

---

## Decision 4: Deterministic Fallback Mode (Zero LLM Dependency)

### Context
If the user does not provide an OpenRouter API key, or if the OpenRouter endpoint experiences an outage (HTTP 502/503/429), the assistant must not crash or display an unhelpful error screen.

### Decision
Implement a deterministic heuristic fallback synthesizer in `backend/src/trace/services/assistant/synthesis.py`:
- If `settings.openrouter_api_key` is not configured or an API call fails after 3 retries, the service formats the retrieved JSON evidence into clean markdown summary cards (e.g., caller tables, risk checklists, prerequisite lists).
- Set `model_used="deterministic-fallback"`.

### Rationale
- Guarantees 100% testability offline (Constitution Principle VII) and 100% uptime in local / air-gapped environments.

---

## Decision 5: Non-Destructive Neo-Brutalist UI & Canvas Isolation

### Context
The TRACE Observatory interface in `frontend/app.py` has a delicate Force-Directed Graph canvas renderer implemented in lines 51–643 and 870–1239. Adding the AI Assistant must not touch or break these canvas blocks.

### Decision
1. **Zero Canvas Mutation**: Lines 51–643 and 870–1239 in `frontend/app.py` are strictly treated as immutable black boxes.
2. **Dedicated Observatory Tab / Expandable Drawer**: Add an independent `"🤖 AI Assistant (F10)"` tab alongside `"Code Intelligence"`, `"Version Analyzer"`, `"Impact & Risk"`, and `"Upgrade Planner"`, plus a contextual query drawer in the sidebar.
3. **Neo-Brutalist Styling**: Style the assistant interface with 2px solid `#000000` borders, sharp 0px radius corners, hard `#000000` offset box-shadows (`3px 3px 0px #000`), and high-contrast color badges.
