"""Specialized pattern detectors for TRACE static code analysis."""

from trace.analysis.detectors.api import APIDetector
from trace.analysis.detectors.config import ConfigDetector
from trace.analysis.detectors.database import DatabaseDetector
from trace.analysis.detectors.dependency import DependencyDetector
from trace.analysis.detectors.documentation import DocumentationDetector
from trace.analysis.detectors.service import ServiceDetector
from trace.analysis.detectors.test import TestDetector
from typing import Any


def get_default_detectors() -> tuple[Any, ...]:
    """Instantiate the standard suite of 7 pattern detectors."""
    return (
        ServiceDetector(),
        APIDetector(),
        ConfigDetector(),
        DatabaseDetector(),
        TestDetector(),
        DocumentationDetector(),
        DependencyDetector(),
    )


__all__ = [
    "APIDetector",
    "ConfigDetector",
    "DatabaseDetector",
    "DependencyDetector",
    "DocumentationDetector",
    "ServiceDetector",
    "TestDetector",
    "get_default_detectors",
]
