"""TRACE — Transformation Risk Analysis & Change Evaluation."""

from importlib import metadata

try:
    __version__ = metadata.version("trace")
except metadata.PackageNotFoundError:
    __version__ = "unknown"

__all__ = ["__version__"]
