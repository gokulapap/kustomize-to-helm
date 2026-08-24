"""Helm chart linting, rendering, and semantic validation."""

import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import yaml

from .errors import ConfigurationError, ValidationError
from .resources import assert_resource_equivalence, index_resources


class HelmValidator:
    """Validate charts with Helm and return their rendered resources."""

    def __init__(
        self,
        helm_binary: Optional[Union[str, Path]] = None,
        timeout: int = 120,
    ):
        binary = str(helm_binary) if helm_binary else shutil.which("helm")
        if not binary:
            raise ConfigurationError(
                "Helm was not found on PATH. Install Helm to lint and verify generated charts."
            )
        self.helm_binary = binary
        self.timeout = timeout
        if timeout <= 0:
            raise ConfigurationError("Helm command timeout must be greater than zero")

    @staticmethod
    def is_available() -> bool:
        return shutil.which("helm") is not None

    def lint(
        self, chart_dir: Union[str, Path], values_files: Sequence[Union[str, Path]] = ()
    ) -> None:
        chart_path = self._validate_chart_path(chart_dir)
        command = [self.helm_binary, "lint", str(chart_path), "--strict"]
        for values_file in values_files:
            command.extend(("--values", str(Path(values_file).resolve())))
        self._run(command, "Helm lint")

    def render(
        self,
        chart_dir: Union[str, Path],
        values_files: Sequence[Union[str, Path]] = (),
        release_name: str = "k2h-validation",
    ) -> List[Dict[str, Any]]:
        chart_path = self._validate_chart_path(chart_dir)
        command = [
            self.helm_binary,
            "template",
            release_name,
            str(chart_path),
            "--include-crds",
        ]
        for values_file in values_files:
            command.extend(("--values", str(Path(values_file).resolve())))
        output = self._run(command, "Helm template")
        try:
            documents = list(yaml.safe_load_all(output))
        except yaml.YAMLError as exc:
            raise ValidationError(f"Helm produced invalid YAML: {exc}") from exc
        resources = [document for document in documents if document is not None]
        index_resources(resources)
        return resources

    def verify_equivalence(
        self,
        chart_dir: Union[str, Path],
        expected_resources: List[Dict[str, Any]],
        values_files: Sequence[Union[str, Path]] = (),
        context: str = "Kustomize output",
    ) -> None:
        self.lint(chart_dir, values_files)
        actual = self.render(chart_dir, values_files)
        assert_resource_equivalence(expected_resources, actual, context)

    @staticmethod
    def inspect_structure(chart_dir: Union[str, Path]) -> Dict[str, List[str]]:
        chart_path = Path(chart_dir).expanduser().resolve()
        issues: List[str] = []
        warnings: List[str] = []
        if not chart_path.is_dir():
            return {"issues": [f"Chart directory does not exist: {chart_path}"], "warnings": []}
        for filename in ("Chart.yaml", "values.yaml"):
            if not (chart_path / filename).is_file():
                issues.append(f"Missing required file: {filename}")
        templates = chart_path / "templates"
        if not templates.is_dir():
            issues.append("Missing templates directory")
        elif not any(path.is_file() for path in templates.iterdir()):
            warnings.append("Templates directory is empty")

        chart_yaml = chart_path / "Chart.yaml"
        if chart_yaml.is_file():
            try:
                data = yaml.safe_load(chart_yaml.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    issues.append("Chart.yaml must contain a mapping")
                else:
                    for field in ("apiVersion", "name", "version"):
                        if not data.get(field):
                            issues.append(f"Chart.yaml missing required field: {field}")
                    if data.get("apiVersion") not in ("v1", "v2"):
                        issues.append("Chart.yaml apiVersion must be v1 or v2")
            except (OSError, yaml.YAMLError) as exc:
                issues.append(f"Invalid Chart.yaml: {exc}")
        values_yaml = chart_path / "values.yaml"
        if values_yaml.is_file():
            try:
                data = yaml.safe_load(values_yaml.read_text(encoding="utf-8"))
                if data is not None and not isinstance(data, dict):
                    issues.append("values.yaml must contain a mapping")
            except (OSError, yaml.YAMLError) as exc:
                issues.append(f"Invalid values.yaml: {exc}")
        return {"issues": issues, "warnings": warnings}

    @staticmethod
    def _validate_chart_path(chart_dir: Union[str, Path]) -> Path:
        chart_path = Path(chart_dir).expanduser().resolve()
        if not chart_path.is_dir():
            raise ValidationError(f"Chart directory does not exist: {chart_path}")
        return chart_path

    def _run(self, command: List[str], operation: str) -> str:
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValidationError(f"{operation} timed out after {self.timeout} seconds") from exc
        except OSError as exc:
            raise ValidationError(f"Unable to run {operation}: {exc}") from exc
        if completed.returncode != 0:
            details = (completed.stderr or completed.stdout or "no error output").strip()
            if len(details) > 4000:
                details = details[:4000] + "…"
            raise ValidationError(f"{operation} failed (exit {completed.returncode}): {details}")
        return completed.stdout
