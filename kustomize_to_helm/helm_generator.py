"""Transactional, fidelity-first Helm chart generation."""

import copy
import hashlib
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Union

import yaml

from .errors import ConfigurationError, GenerationError
from .resources import identity_text, index_resources, resource_key

logger = logging.getLogger(__name__)

_CHART_NAME_RE = re.compile(r"^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?$")
_SEMVER_RE = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


class _LiteralString(str):
    pass


class _ValuesDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def _represent_literal(dumper: yaml.SafeDumper, data: _LiteralString):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


_ValuesDumper.add_representer(_LiteralString, _represent_literal)


def validate_chart_name(name: str) -> str:
    """Validate a Helm chart name and return it unchanged."""
    if not isinstance(name, str) or not name:
        raise ConfigurationError("Chart name must be a non-empty string")
    if len(name) > 253 or not _CHART_NAME_RE.fullmatch(name):
        raise ConfigurationError(
            f"Invalid chart name {name!r}. Use lowercase letters, numbers, or '-', "
            "starting and ending with a letter or number (maximum 253 characters)."
        )
    return name


def normalize_chart_name(name: str) -> str:
    """Convert a directory name to a valid, predictable Helm chart name."""
    normalized = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    normalized = re.sub(r"-{2,}", "-", normalized)[:253].rstrip("-")
    if not normalized:
        raise ConfigurationError(f"Cannot derive a valid chart name from {name!r}")
    return validate_chart_name(normalized)


def validate_chart_version(version: str) -> str:
    """Validate the SemVer required by Helm's Chart.yaml version field."""
    if not isinstance(version, str) or not _SEMVER_RE.fullmatch(version):
        raise ConfigurationError(f"Invalid chart version {version!r}; expected semantic versioning")
    return version


class HelmChartGenerator:
    """Generate a values-driven chart whose output matches Kustomize exactly."""

    def __init__(
        self,
        chart_name: str,
        output_dir: Union[str, Path],
        overwrite: bool = False,
    ):
        self.chart_name = validate_chart_name(chart_name)
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.chart_dir = self.output_dir / self.chart_name
        self.templates_dir = self.chart_dir / "templates"
        self.overwrite = overwrite
        self.values: Dict[str, Any] = {}
        self.chart_metadata: Dict[str, Any] = {
            "apiVersion": "v2",
            "name": self.chart_name,
            "description": f"Helm chart for {self.chart_name} (migrated from Kustomize)",
            "type": "application",
            "version": "0.1.0",
            "appVersion": "1.0.0",
        }
        self.generated_values_files: List[str] = []

    def generate_chart(
        self,
        kustomize_data: Dict[str, Any],
        overlay_resources: Optional[Mapping[str, List[Dict[str, Any]]]] = None,
        pre_install_validator: Optional[Callable[[Path], None]] = None,
    ) -> None:
        """Generate the chart atomically.

        ``overlay_resources`` maps overlay names to their fully rendered resource
        sets. The base rendered set is supplied in ``kustomize_data['resources']``.
        """
        base_resources = kustomize_data.get("resources")
        if not isinstance(base_resources, list):
            raise GenerationError("kustomize_data['resources'] must be a list")
        overlays = dict(overlay_resources or {})
        for name, resources in overlays.items():
            if not isinstance(name, str) or not name:
                raise ConfigurationError(f"Invalid overlay name: {name!r}")
            if not isinstance(resources, list):
                raise GenerationError(f"Resources for overlay {name!r} must be a list")

        base_index = index_resources(base_resources)
        overlay_indexes = {name: index_resources(resources) for name, resources in overlays.items()}
        catalog, overlay_values = self._build_resource_values(base_index, overlay_indexes)
        self.values = {"resources": catalog}
        self.chart_metadata["appVersion"] = "1.0.0"
        self._update_chart_metadata(kustomize_data, base_resources)

        self.output_dir.mkdir(parents=True, exist_ok=True)
        if not self.output_dir.is_dir():
            raise GenerationError(f"Output path is not a directory: {self.output_dir}")
        if self.chart_dir.is_symlink():
            raise GenerationError(
                f"Refusing to replace symlinked chart directory: {self.chart_dir}"
            )
        if self.chart_dir.exists() and not self.overwrite:
            raise GenerationError(
                f"Chart directory already exists: {self.chart_dir}. "
                "Use overwrite/--force explicitly."
            )

        staging_root = Path(tempfile.mkdtemp(prefix=".k2h-stage-", dir=str(self.output_dir)))
        staged_chart = staging_root / self.chart_name
        try:
            self._write_chart(staged_chart, overlay_values)
            if pre_install_validator:
                pre_install_validator(staged_chart)
            self._install_staged_chart(staged_chart)
        except Exception:
            shutil.rmtree(staging_root, ignore_errors=True)
            raise
        shutil.rmtree(staging_root, ignore_errors=True)
        self.templates_dir = self.chart_dir / "templates"
        logger.info("Generated Helm chart at %s", self.chart_dir)

    def _build_resource_values(self, base_index, overlay_indexes):
        all_identities = set(base_index)
        for overlay_index in overlay_indexes.values():
            all_identities.update(overlay_index)

        representatives = dict(base_index)
        for overlay_name in sorted(overlay_indexes):
            for identity, resource in overlay_indexes[overlay_name].items():
                representatives.setdefault(identity, resource)

        catalog: Dict[str, Dict[str, Any]] = {}
        key_by_identity = {}
        for identity in sorted(all_identities):
            resource = representatives[identity]
            key = resource_key(resource)
            if key in catalog:
                raise GenerationError(
                    f"Internal resource-key collision for {identity_text(identity)}"
                )
            key_by_identity[identity] = key
            catalog[key] = {
                "enabled": identity in base_index,
                "manifest": _LiteralString(self._serialize_resource(resource)),
            }

        overlay_values: Dict[str, Dict[str, Any]] = {}
        for overlay_name, overlay_index in sorted(overlay_indexes.items()):
            changes: Dict[str, Dict[str, Any]] = {}
            for identity in sorted(all_identities):
                key = key_by_identity[identity]
                in_overlay = identity in overlay_index
                changes[key] = {"enabled": in_overlay}
                if in_overlay and overlay_index[identity] != representatives[identity]:
                    changes[key]["manifest"] = _LiteralString(
                        self._serialize_resource(overlay_index[identity])
                    )
            overlay_values[overlay_name] = {"resources": changes}
        return catalog, overlay_values

    @staticmethod
    def _serialize_resource(resource: Dict[str, Any]) -> str:
        clean = copy.deepcopy(resource)
        clean.pop("_source_file", None)
        return yaml.safe_dump(clean, sort_keys=False, default_flow_style=False).rstrip() + "\n"

    def _update_chart_metadata(self, kustomize_data, resources) -> None:
        images = kustomize_data.get("kustomization", {}).get("images", [])
        if images and isinstance(images[0], dict):
            version = images[0].get("newTag") or images[0].get("digest")
            if version:
                self.chart_metadata["appVersion"] = str(version)
                return
        for resource in resources:
            containers = (
                resource.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
            )
            if containers and isinstance(containers[0], dict):
                image = containers[0].get("image", "")
                if "@" in image:
                    self.chart_metadata["appVersion"] = image.rsplit("@", 1)[1]
                    return
                last_component = image.rsplit("/", 1)[-1]
                if ":" in last_component:
                    self.chart_metadata["appVersion"] = last_component.rsplit(":", 1)[1]
                    return

    def _write_chart(self, chart_dir: Path, overlay_values: Mapping[str, Dict[str, Any]]) -> None:
        templates_dir = chart_dir / "templates"
        templates_dir.mkdir(parents=True)
        (chart_dir / "charts").mkdir()
        self._write_yaml(chart_dir / "Chart.yaml", self.chart_metadata)
        self._write_yaml(chart_dir / "values.yaml", self.values)
        (templates_dir / "resources.yaml").write_text(self._resource_template(), encoding="utf-8")
        (templates_dir / "NOTES.txt").write_text(self._notes_template(), encoding="utf-8")
        (chart_dir / ".helmignore").write_text(self._helmignore(), encoding="utf-8")
        (chart_dir / "MIGRATION.md").write_text(
            self._migration_notes(overlay_values), encoding="utf-8"
        )

        self.generated_values_files = ["values.yaml"]
        used_filenames = {"values.yaml"}
        for overlay_name, values in sorted(overlay_values.items()):
            safe_name = self._safe_overlay_filename(overlay_name)
            filename = f"values-{safe_name}.yaml"
            filename_key = filename.casefold()
            if filename_key in {item.casefold() for item in used_filenames}:
                raise ConfigurationError(
                    f"Overlay names produce the same values filename: {overlay_name!r}"
                )
            used_filenames.add(filename)
            self._write_yaml(chart_dir / filename, values)
            self.generated_values_files.append(filename)

    @staticmethod
    def _write_yaml(path: Path, data: Dict[str, Any]) -> None:
        try:
            with path.open("w", encoding="utf-8", newline="\n") as handle:
                yaml.dump(
                    data,
                    handle,
                    Dumper=_ValuesDumper,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True,
                )
        except OSError as exc:
            raise GenerationError(f"Unable to write {path}: {exc}") from exc

    @staticmethod
    def _safe_overlay_filename(name: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip(".-")
        if not safe or safe in (".", ".."):
            raise ConfigurationError(f"Overlay name cannot be used as a values filename: {name!r}")
        if len(safe.encode("utf-8")) > 180:
            digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:10]
            safe = f"{safe[:160].rstrip('.-')}-{digest}"
        return safe

    def _install_staged_chart(self, staged_chart: Path) -> None:
        if not self.chart_dir.exists():
            os.replace(staged_chart, self.chart_dir)
            return

        backup = Path(tempfile.mkdtemp(prefix=".k2h-backup-", dir=str(self.output_dir)))
        backup_chart = backup / self.chart_name
        installed = False
        try:
            os.replace(self.chart_dir, backup_chart)
            try:
                os.replace(staged_chart, self.chart_dir)
                installed = True
            except Exception as install_error:
                try:
                    os.replace(backup_chart, self.chart_dir)
                except Exception as restore_error:
                    raise GenerationError(
                        f"Failed to install the new chart and restore the previous chart. "
                        f"The backup is preserved at {backup_chart}: {restore_error}"
                    ) from install_error
                raise
        finally:
            if installed or not backup_chart.exists():
                shutil.rmtree(backup, ignore_errors=True)

    @staticmethod
    def _resource_template() -> str:
        return """{{- range $resourceID := keys .Values.resources | sortAlpha }}
{{- $resource := index $.Values.resources $resourceID }}
{{- if $resource.enabled }}
{{- if not $resource.manifest }}
{{- fail (printf "resources.%s.manifest is required when enabled" $resourceID) }}
{{- end }}
{{ $resource.manifest }}---
{{- end }}
{{- end }}
"""

    @staticmethod
    def _notes_template() -> str:
        return """Kustomize migration installed {{ len .Values.resources }} catalogued resources.
Review MIGRATION.md before changing the generated manifest values.
"""

    @staticmethod
    def _helmignore() -> str:
        return """.DS_Store
.git/
.gitignore
.idea/
.vscode/
*.swp
*.tmp
*.orig
*~
"""

    def _migration_notes(self, overlays: Mapping[str, Dict[str, Any]]) -> str:
        lines = [
            f"# {self.chart_name} migration notes",
            "",
            "This chart was generated from the fully rendered Kustomize output. Each entry in",
            "`values.yaml` contains one complete Kubernetes manifest, which avoids lossy attempts",
            "to reinterpret patches or custom resources.",
            "",
            "Render the base with:",
            "",
            "    helm template RELEASE .",
        ]
        if overlays:
            lines.extend(["", "Render an overlay with:", ""])
            for name in sorted(overlays):
                safe = self._safe_overlay_filename(name)
                lines.append(f"    helm template RELEASE . -f values-{safe}.yaml  # {name}")
        lines.extend(
            [
                "",
                "Do not use `tpl` on manifest values: literal `{{ ... }}` content may belong to",
                "the application and is intentionally preserved verbatim.",
                "",
            ]
        )
        return "\n".join(lines)
