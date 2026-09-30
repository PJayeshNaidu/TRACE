"""Fault-tolerant Python AST parser producing structured diagnostics on errors."""

import ast
from pathlib import Path
from trace.domain.analysis import AnalysisDiagnostic, DiagnosticSeverity


class PythonAstParser:
    """Parses Python source files into standard library ast.AST nodes with error diagnostics."""

    def parse_source(
        self,
        source: str,
        filename: str = "<unknown>",
    ) -> tuple[ast.AST | None, AnalysisDiagnostic | None]:
        """Parse source code string into an AST tree.

        Args:
            source: Python source code.
            filename: Normalized relative file path for diagnostics.

        Returns:
            A tuple of (parsed_ast, None) if successful, or (None, AnalysisDiagnostic)
            on syntax error.
        """
        try:
            tree = ast.parse(source, filename=filename)
            return tree, None
        except SyntaxError as exc:
            diagnostic = AnalysisDiagnostic(
                file_path=filename,
                severity=DiagnosticSeverity.ERROR,
                code="SYNTAX_ERROR",
                message=exc.msg or str(exc),
                line=exc.lineno,
                column=exc.offset,
            )
            return None, diagnostic
        except Exception as exc:
            diagnostic = AnalysisDiagnostic(
                file_path=filename,
                severity=DiagnosticSeverity.ERROR,
                code="PARSE_ERROR",
                message=str(exc),
                line=None,
                column=None,
            )
            return None, diagnostic

    def parse_file(
        self,
        file_path: Path | str,
        rel_path: str | None = None,
    ) -> tuple[ast.AST | None, AnalysisDiagnostic | None]:
        """Read and parse a Python source file from disk.

        Args:
            file_path: Absolute or relative filesystem path to read.
            rel_path: Optional relative POSIX path for reporting in diagnostics.

        Returns:
            A tuple of (parsed_ast, None) or (None, AnalysisDiagnostic).
        """
        path = Path(file_path)
        display_path = rel_path or path.as_posix()

        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                # Fallback decoding
                source = path.read_text(encoding="latin-1")
            except Exception as exc:
                return None, AnalysisDiagnostic(
                    file_path=display_path,
                    severity=DiagnosticSeverity.ERROR,
                    code="ENCODING_ERROR",
                    message=f"Failed to decode file: {exc}",
                )
        except OSError as exc:
            return None, AnalysisDiagnostic(
                file_path=display_path,
                severity=DiagnosticSeverity.ERROR,
                code="FILE_READ_ERROR",
                message=f"Failed to read file: {exc}",
            )

        return self.parse_source(source, filename=display_path)
