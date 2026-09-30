"""Static code analysis subsystem for TRACE."""

from trace.analysis.analyzer import AnalysisContext, CodeAnalyzer, PythonCodeAnalyzer
from trace.analysis.extractor import ExtractedSymbols, SymbolExtractor, derive_module_qualified_name
from trace.analysis.parser import PythonAstParser
from trace.analysis.scanner import RepositoryScanner, ScanResult

__all__ = [
    "AnalysisContext",
    "CodeAnalyzer",
    "ExtractedSymbols",
    "PythonAstParser",
    "PythonCodeAnalyzer",
    "RepositoryScanner",
    "ScanResult",
    "SymbolExtractor",
    "derive_module_qualified_name",
]
