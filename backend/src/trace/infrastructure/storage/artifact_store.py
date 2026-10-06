"""Filesystem JSON artifact storage implementation for analysis runs."""

import json
from pathlib import Path
from typing import Any, cast
from uuid import UUID


class FileArtifactStore:
    """Manages persistence of RepositoryAnalysis JSON artifacts on the filesystem."""

    def __init__(self, base_path: Path | str = "storage/artifacts/analyses") -> None:
        self._base_path = Path(base_path)

    @property
    def base_path(self) -> Path:
        """The base storage directory path."""
        return self._base_path

    def get_artifact_path(self, run_id: UUID) -> Path:
        """Compute the deterministic artifact file path for an analysis run."""
        return self._base_path / f"{run_id}.json"

    def exists(self, run_id: UUID) -> bool:
        """Check whether an artifact file exists on disk."""
        return self.get_artifact_path(run_id).is_file()

    def write_artifact(self, run_id: UUID, analysis_data: dict[str, Any] | str) -> Path:
        """Persist analysis data as an immutable versioned JSON artifact.

        Args:
            run_id: The UUID of the analysis run.
            analysis_data: Either a dictionary payload or a pre-serialized JSON string.

        Returns:
            The Path to the written JSON artifact file.
        """
        self._base_path.mkdir(parents=True, exist_ok=True)
        artifact_path = self.get_artifact_path(run_id)

        if isinstance(analysis_data, str):
            content = analysis_data
        else:
            content = json.dumps(analysis_data, indent=2, default=str)

        # Atomic or standard write with UTF-8
        temp_path = artifact_path.with_suffix(".tmp")
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(artifact_path)

        return artifact_path

    def read_artifact(self, run_id: UUID) -> dict[str, Any]:
        """Read and parse the JSON artifact from disk.

        Args:
            run_id: The UUID of the analysis run.

        Returns:
            The parsed dictionary representation of the artifact.

        Raises:
            FileNotFoundError: If the artifact does not exist on disk.
        """
        artifact_path = self.get_artifact_path(run_id)
        if not artifact_path.is_file():
            raise FileNotFoundError(
                f"Analysis artifact not found for run {run_id} at {artifact_path}"
            )

        content = artifact_path.read_text(encoding="utf-8")
        return cast(dict[str, Any], json.loads(content))


class PlanArtifactStore(FileArtifactStore):
    """Manages persistence of UpgradePlan JSON artifacts on the filesystem."""

    def __init__(self, base_path: Path | str = ".trace/artifacts/plans") -> None:
        super().__init__(base_path=base_path)
