# API Contract: TRACE Phase 4 — F05: Impact Analysis & Risk Evaluation Engine

**Base Path**: `/api/v1/impact`  
**Version**: `1.0.0`

---

## 1. Endpoints

### `POST /api/v1/impact/evaluate`
Triggers an impact analysis and risk evaluation run between two Git references.

#### Request Body (`application/json`)
```json
{
  "repository_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "base_ref": "HEAD~1",
  "target_ref": "HEAD",
  "llm_config": {
    "enabled": false,
    "api_key": null,
    "model": "anthropic/claude-3.5-sonnet"
  }
}
```

#### Response (`201 Created` / `application/json`)
Returns the complete 4-key unified payload:
```json
{
  "analysis_metadata": {
    "analysis_id": "8c412f8e-8a21-4f93-b672-0051187d9a10",
    "repository": "https://github.com/vignesh-naik-720/python-proj.git",
    "base_commit": "a4e6bb0a1a9e28b6aa9fafb433ac479da45c9cd3",
    "current_commit": "76216a36e310467f2e6f5f03a35d7780394dd6ba",
    "reasoning_mode": "HEURISTIC",
    "total_changed_entities": 2,
    "total_deleted_files": 0,
    "total_impacted_downstream_files": 1,
    "total_callers_at_risk": 2
  },
  "impact_analysis": {
    "summary": "Detected 2 changed entities and 0 deleted files impacting 1 downstream files.",
    "detailed_impacts": [
      {
        "file": "main.py",
        "entity": "calculate_tax",
        "entity_type": "function",
        "lines_affected": [1, 3],
        "diff_snippet": "-def calculate_tax(subtotal):\n+def calculate_tax(subtotal, rate=0.08):",
        "change_summary": "Method signature / parameter definitions modified.",
        "remediation_guidance": "Audit all call sites of `calculate_tax` to ensure argument compatibility with the updated parameter list.",
        "justification": "Core function `calculate_tax` in `main.py` modified (lines 1-3); modifies parameter signature. Directly impacts upstream callers (`calculate_total`, `process_payment`). Propagates risk to 1 downstream dependent file.",
        "outbound_calls": [],
        "inbound_callers": ["calculate_total", "process_payment"],
        "callers_at_risk": [
          {
            "qualified_name": "calculate_total",
            "file_path": "main.py",
            "distance": 1,
            "call_chain": ["calculate_total", "calculate_tax"]
          },
          {
            "qualified_name": "process_payment",
            "file_path": "main.py",
            "distance": 2,
            "call_chain": ["process_payment", "calculate_total", "calculate_tax"]
          }
        ],
        "downstream_dependent_files": ["main.py"]
      }
    ]
  },
  "dependency_graph": {
    "nodes": [
      {
        "changed_entity": "calculate_tax",
        "file": "main.py",
        "downstream_dependent_files": ["main.py"],
        "inbound_callers": ["calculate_total", "process_payment"],
        "outbound_calls": []
      }
    ],
    "edges": [
      {
        "caller": "calculate_total",
        "callee": "calculate_tax",
        "relationship": "direct_call"
      },
      {
        "caller": "process_payment",
        "callee": "calculate_total",
        "relationship": "direct_call"
      }
    ],
    "mermaid": "graph TD\n  subgraph Modified [Modified Entities]\n    calculate_tax[\"calculate_tax (main.py)\"]:::modifiedNode\n  end\n  subgraph AtRisk [At-Risk Callers]\n    calculate_total[\"calculate_total (Depth 1)\"]:::riskNode\n    process_payment[\"process_payment (Depth 2)\"]:::riskNode\n  end\n  calculate_total --> calculate_tax\n  process_payment --> calculate_total\n  classDef modifiedNode fill:#ef4444,stroke:#b91c1c,color:#ffffff,stroke-width:2px;\n  classDef riskNode fill:#f59e0b,stroke:#d97706,color:#ffffff,stroke-width:2px;"
  },
  "risk_analysis": {
    "risk_level": "LOW",
    "key_risk_factors": [
      {
        "factor": "Isolated Component Modification",
        "severity": "LOW",
        "justification": "Changes are localized with minimal downstream callers or cross-module dependencies."
      }
    ],
    "ci_cd_recommendations": [
      "Standard test suite execution is sufficient."
    ],
    "actionable_remediation_plan": [
      {
        "step_number": 1,
        "category": "Contract Changes",
        "action_description": "Audit call sites of calculate_tax for argument compatibility.",
        "affected_targets": ["calculate_tax"]
      },
      {
        "step_number": 2,
        "category": "Direct Callers",
        "action_description": "Execute regression tests covering direct upstream caller calculate_total.",
        "affected_targets": ["calculate_total"]
      },
      {
        "step_number": 3,
        "category": "Integration Validation",
        "action_description": "Run integration test suite across downstream file main.py.",
        "affected_targets": ["main.py"]
      }
    ],
    "ai_directive": {
      "executive_summary": "Detected 2 changed code entities impacting 2 upstream callers.",
      "where_to_change": ["main.py"],
      "what_to_change": ["Verify call sites and imports in calculate_total (main.py)"],
      "precautions": ["Execute unit tests covering modified functions and direct callers."]
    }
  }
}
```

---

### `GET /api/v1/impact/{analysis_id}`
Retrieves a previously computed impact evaluation by its ID.

#### Response (`200 OK`)
Returns identical payload to `POST /api/v1/impact/evaluate`.

#### Error Responses
- `404 Not Found`: If `analysis_id` does not exist.
