"""Kustomize input validation and rendering.

The Kustomize CLI is deliberately the source of truth. Reimplementing its patch,
generator, transformer, hashing, and OpenAPI behavior in Python creates charts
that look plausible while silently changing workloads.
"""

import copy
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import yaml

from .errors import BuildError, ConfigurationError
from .resources import index_resources

logger = logging.getLogger(__name__)

KUSTOMIZATION_FILENAMES = ("kustomization.yaml", "kustomization.yml", "Kustomization")
DEFAULT_BUILD_TIMEOUT = 120
DEFAULT_MAX_OUTPUT_BYTES = 50 * 1024 * 1024


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise ConfigurationError("YAML mapping keys must be scalar values") from exc
        if duplicate:
            raise ConfigurationError(
                f"Duplicate YAML key {key!r} at line {key_node.start_mark.line + 1}"
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


class KustomizeParser:
    """Validate a Kustomization and render its final Kubernetes resources."""

    def __init__(
        self,
        kustomize_dir: Union[str, Path],
        build_command: Optional[Sequence[str]] = None,
        timeout: int = DEFAULT_BUILD_TIMEOUT,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    ):
        self.kustomize_dir = Path(kustomize_dir).expanduser().resolve()
        self.timeout = timeout
        self.max_output_bytes = max_output_bytes
        if timeout <= 0:
            raise ConfigurationError("Kustomize build timeout must be greater than zero")
        if max_output_bytes <= 0:
            raise ConfigurationError("Maximum build output size must be greater than zero")
        if not self.kustomize_dir.exists():
            raise ConfigurationError(f"Kustomize directory does not exist: {self.kustomize_dir}")
        if not self.kustomize_dir.is_dir():
            raise ConfigurationError(f"Kustomize path is not a directory: {self.kustomize_dir}")

        self.kustomization_file = self._find_kustomization_file()
        if isinstance(build_command, (str, bytes)):
            raise ConfigurationError(
                "build_command must be a sequence of arguments, not a shell command string"
            )
        self.build_command = (
            [str(argument) for argument in build_command]
            if build_command is not None
            else self._discover_build_command()
        )
        if not self.build_command:
            raise ConfigurationError("Kustomize build command cannot be empty")
        if any(not argument for argument in self.build_command):
            raise ConfigurationError("Kustomize build command arguments cannot be empty")

        self.kustomization_data: Dict[str, Any] = {}
        self.resources: List[Dict[str, Any]] = []
        self.patches: List[Any] = []
        self.config_maps: List[Dict[str, Any]] = []
        self.secrets: List[Dict[str, Any]] = []
        self.warnings: List[str] = []
        self._parsed = False

    def _find_kustomization_file(self) -> Path:
        matches = []
        for filename in KUSTOMIZATION_FILENAMES:
            candidate = self.kustomize_dir / filename
            if not candidate.is_file():
                continue
            if not any(candidate.samefile(existing) for existing in matches):
                matches.append(candidate)
        if not matches:
            raise ConfigurationError(
                f"No kustomization.yaml, kustomization.yml, or Kustomization file found in "
                f"{self.kustomize_dir}"
            )
        if len(matches) > 1:
            names = ", ".join(path.name for path in matches)
            raise ConfigurationError(
                f"Multiple Kustomization files found in {self.kustomize_dir}: {names}"
            )
        return matches[0]

    @staticmethod
    def _discover_build_command() -> List[str]:
        kustomize = shutil.which("kustomize")
        if kustomize:
            return [kustomize, "build"]
        kubectl = shutil.which("kubectl")
        if kubectl:
            return [kubectl, "kustomize"]
        raise ConfigurationError(
            "Neither 'kustomize' nor 'kubectl' was found on PATH. Install Kustomize "
            "or pass an explicit build command through the Python API."
        )

    def parse(self) -> Dict[str, Any]:
        """Parse metadata and return the fully rendered resource set."""
        self.warnings = []
        self.kustomization_data = self._load_kustomization()
        self._record_feature_metadata()
        self.resources = self._build_resources()
        self._parsed = True

        return {
            "kustomization": copy.deepcopy(self.kustomization_data),
            "resources": copy.deepcopy(self.resources),
            "patches": copy.deepcopy(self.patches),
            "configMaps": copy.deepcopy(self.config_maps),
            "secrets": copy.deepcopy(self.secrets),
            "namespace": self.kustomization_data.get("namespace"),
            "namePrefix": self.kustomization_data.get("namePrefix", ""),
            "nameSuffix": self.kustomization_data.get("nameSuffix", ""),
            "commonLabels": copy.deepcopy(self.kustomization_data.get("commonLabels", {})),
            "commonAnnotations": copy.deepcopy(
                self.kustomization_data.get("commonAnnotations", {})
            ),
            "images": copy.deepcopy(self.kustomization_data.get("images", [])),
            "replicas": copy.deepcopy(self.kustomization_data.get("replicas", [])),
            "warnings": list(self.warnings),
            "renderer": " ".join(self.build_command),
        }

    def _load_kustomization(self) -> Dict[str, Any]:
        logger.info("Reading Kustomization: %s", self.kustomization_file)
        try:
            content = self.kustomization_file.read_text(encoding="utf-8")
            data = yaml.load(content, Loader=_UniqueKeyLoader)
        except OSError as exc:
            raise ConfigurationError(
                f"Cannot read Kustomization file {self.kustomization_file}: {exc}"
            ) from exc
        except yaml.YAMLError as exc:
            raise ConfigurationError(f"Invalid YAML in {self.kustomization_file}: {exc}") from exc

        if data is None:
            raise ConfigurationError(f"Kustomization file is empty: {self.kustomization_file}")
        if not isinstance(data, dict):
            raise ConfigurationError("Kustomization document must be a YAML mapping")
        kind = data.get("kind")
        if kind is not None and kind != "Kustomization":
            raise ConfigurationError(
                f"Expected kind 'Kustomization', found {kind!r} in {self.kustomization_file}"
            )
        return data

    def _record_feature_metadata(self) -> None:
        data = self.kustomization_data
        self.patches = []
        for field in ("patches", "patchesStrategicMerge", "patchesJson6902"):
            entries = data.get(field, [])
            if entries is None:
                continue
            if not isinstance(entries, list):
                raise ConfigurationError(f"Kustomization field '{field}' must be a list")
            self.patches.extend(
                {"field": field, "entry": copy.deepcopy(entry)} for entry in entries
            )

        self.config_maps = self._validated_generator_list("configMapGenerator")
        self.secrets = self._validated_generator_list("secretGenerator")
        for deprecated in ("bases", "patchesStrategicMerge", "patchesJson6902", "commonLabels"):
            if deprecated in data:
                self.warnings.append(
                    f"Kustomize field '{deprecated}' is deprecated; it was rendered faithfully but "
                    "should be modernized at the source"
                )
        for plugin_field in ("generators", "transformers", "validators"):
            if plugin_field in data:
                self.warnings.append(
                    f"Kustomize field '{plugin_field}' may require plugin flags "
                    "not enabled by default"
                )

    def _validated_generator_list(self, field: str) -> List[Dict[str, Any]]:
        entries = self.kustomization_data.get(field, [])
        if entries is None:
            return []
        if not isinstance(entries, list):
            raise ConfigurationError(f"Kustomization field '{field}' must be a list")
        result = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise ConfigurationError(f"{field}[{index}] must be a mapping")
            if not isinstance(entry.get("name"), str) or not entry["name"].strip():
                raise ConfigurationError(f"{field}[{index}] is missing a non-empty name")
            result.append(copy.deepcopy(entry))
        return result

    def _build_resources(self) -> List[Dict[str, Any]]:
        command = [*self.build_command, str(self.kustomize_dir)]
        logger.info("Rendering Kustomize resources with: %s", " ".join(command))
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
            raise BuildError(
                f"Kustomize build timed out after {self.timeout} seconds for {self.kustomize_dir}"
            ) from exc
        except OSError as exc:
            raise BuildError(f"Unable to execute {' '.join(self.build_command)}: {exc}") from exc

        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            if len(stderr) > 4000:
                stderr = stderr[:4000] + "…"
            raise BuildError(
                f"Kustomize build failed for {self.kustomize_dir} "
                f"(exit {completed.returncode}): {stderr or 'no error output'}"
            )
        stderr = (completed.stderr or "").strip()
        if stderr:
            if len(stderr) > 2000:
                stderr = stderr[:2000] + "…"
            self.warnings.append(f"Kustomize build warning: {stderr}")
        output_size = len(completed.stdout.encode("utf-8"))
        if output_size > self.max_output_bytes:
            raise BuildError(
                f"Kustomize build produced {output_size} bytes, exceeding the configured "
                f"limit of {self.max_output_bytes} bytes"
            )

        try:
            documents = list(yaml.load_all(completed.stdout, Loader=_UniqueKeyLoader))
        except (yaml.YAMLError, ConfigurationError) as exc:
            raise BuildError(f"Kustomize produced invalid YAML: {exc}") from exc
        resources = [document for document in documents if document is not None]
        index_resources(resources)
        return resources

    def get_all_resources(self) -> List[Dict[str, Any]]:
        """Return rendered resources, parsing lazily when needed."""
        if not self._parsed:
            self.parse()
        return copy.deepcopy(self.resources)
