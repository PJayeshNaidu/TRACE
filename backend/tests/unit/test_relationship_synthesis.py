"""Unit tests for relationship synthesis and call resolution."""

from trace.analysis.extractor import SymbolExtractor
from trace.analysis.parser import PythonAstParser
from trace.domain.analysis import (
    CallResolutionStatus,
    EntityKind,
    RelationshipKind,
)


def test_call_resolution_and_no_speculative_edges():
    """Verify resolvable calls generate CALLS edges and dynamic calls do NOT generate fake edges."""
    code = """
from helper import external_helper

def local_target():
    return 1

def caller(dynamic_obj, flag):
    # Resolvable internal call
    local_target()

    # Resolvable external call
    external_helper()

    # Unresolvable dynamic call: getattr
    getattr(dynamic_obj, "run")()

    # Unresolvable dynamic call: parameter call
    dynamic_obj()
"""
    parser = PythonAstParser()
    tree, diag = parser.parse_source(code, filename="test_mod.py")
    assert tree is not None

    extractor = SymbolExtractor(internal_packages={"test_mod"})
    extracted = extractor.extract(tree, file_path="test_mod.py", total_lines=20)

    caller_calls = [c for c in extracted.calls if c.caller_qualified_name == "test_mod.caller"]
    assert len(caller_calls) == 5

    # Internal call
    int_call = next(c for c in caller_calls if c.callee_expression == "local_target")
    assert int_call.resolution_status == CallResolutionStatus.RESOLVED_INTERNAL
    assert int_call.resolved_target == "test_mod.local_target"

    # External call
    ext_call = next(c for c in caller_calls if c.callee_expression == "external_helper")
    assert ext_call.resolution_status == CallResolutionStatus.RESOLVED_EXTERNAL
    assert ext_call.resolved_target == "helper.external_helper"

    # Dynamic calls (getattr inner call, outer dynamic invocation, and parameter call)
    dyn_calls = [
        c for c in caller_calls if c.resolution_status == CallResolutionStatus.UNRESOLVED_DYNAMIC
    ]
    assert len(dyn_calls) == 3

    # CALLS relationships: ONLY 2 should exist (for the 2 resolved calls)!
    # 0 edges for dynamic calls per Constitution §I (Evidence over Hallucination)
    call_rels = [
        r for r in extracted.relationships if r.relationship_type == RelationshipKind.CALLS
    ]
    assert len(call_rels) == 2

    target_ids = {r.target_identifier for r in call_rels}
    assert "test_mod.local_target" in target_ids
    assert "helper.external_helper" in target_ids


def test_extends_hierarchy():
    """Verify class inheritance generates EXTENDS relationships."""
    code = """
class Base:
    pass

class Derived(Base):
    pass
"""
    parser = PythonAstParser()
    tree, _ = parser.parse_source(code, filename="mod.py")
    extractor = SymbolExtractor()
    extracted = extractor.extract(tree, file_path="mod.py", total_lines=10)

    extends_rels = [
        r for r in extracted.relationships if r.relationship_type == RelationshipKind.EXTENDS
    ]
    assert len(extends_rels) == 1
    rel = extends_rels[0]
    assert rel.source_identifier == "mod.Derived"
    assert rel.target_identifier == "Base"
    assert rel.source_type == EntityKind.CLASS
    assert rel.target_type == EntityKind.CLASS
