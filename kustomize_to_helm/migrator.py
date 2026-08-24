"""Single-Kustomization migration orchestration."""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Union

from .errors import ConfigurationError
from .helm_generator import HelmChartGenerator, normalize_chart_name, validate_chart_name
from .kustomize_parser import DEFAULT_BUILD_TIMEOUT, KustomizeParser
from .resources import find_helm_behavior_annotations
from .validation import HelmValidator

logger = logging.getLogger(__name__)


class KustomizeToHelmMigrator:
    """Migrate one rendered Kustomization to a semantically equivalent chart."""

    def __init__(
        self,
        kustomize_dir: Union[str, Path],
        output_dir: Union[str, Path],
        chart_name: Optional[str] = None,
        dry_run: bool = False,
        overwrite: bool = False,
        verify: bool = True,
        build_command: Optional[Sequence[str]] = None,
        timeout: int = DEFAULT_BUILD_TIMEOUT,
    ):
        self.kustomize_dir = Path(kustomize_dir).expanduser().resolve()
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.chart_name = (
            validate_chart_name(chart_name)
            if chart_name is not None
            else normalize_chart_name(self.kustomize_dir.name)
        )
        self.dry_run = dry_run
        self.overwrite = overwrite
        self.verify = verify
        self.timeout = timeout
        self.parser = KustomizeParser(
            self.kustomize_dir,
            build_command=build_command,
            timeout=timeout,
        )
        self.generator = HelmChartGenerator(
            self.chart_name,
            self.output_dir,
            overwrite=overwrite,
        )
        self.kustomize_data: Dict[str, Any] = {}
        self.migration_report = self._new_report()

    def _new_report(self) -> Dict[str, Any]:
        return {
            "source_directory": str(self.kustomize_dir),
            "target_directory": str(self.output_dir / self.chart_name),
            "chart_name": self.chart_name,
            "resources_migrated": 0,
            "patches_converted": 0,
            "config_maps_generated": 0,
            "secrets_generated": 0,
            "validation": "not-run",
            "warnings": [],
            "errors": [],
            "status": "pending",
        }

    def migrate(self) -> Dict[str, Any]:
        """Render, analyze, generate, and verify a chart."""
        self.migration_report = self._new_report()
        try:
            self._parse_kustomize()
            self._analyze_configuration()
            if self.dry_run:
                self.migration_report["validation"] = "dry-run"
            else:
                self._generate_helm_chart()
            self.migration_report["status"] = "success"
            return self.migration_report
        except Exception as exc:
            self.migration_report["status"] = "failed"
            message = str(exc)
            if message not in self.migration_report["errors"]:
                self.migration_report["errors"].append(message)
            logger.error("Migration failed: %s", exc)
            raise

    def _parse_kustomize(self) -> None:
        self.kustomize_data = self.parser.parse()
        resources = self.kustomize_data["resources"]
        self.migration_report.update(
            {
                "resources_migrated": len(resources),
                "patches_converted": len(self.kustomize_data["patches"]),
                "config_maps_generated": sum(
                    resource.get("kind") == "ConfigMap" for resource in resources
                ),
                "secrets_generated": sum(
                    resource.get("kind") == "Secret" for resource in resources
                ),
            }
        )
        self.migration_report["warnings"].extend(self.kustomize_data.get("warnings", []))

    def _analyze_configuration(self, fail_on_helm_annotations: bool = True) -> None:
        resources = self.kustomize_data.get("resources", [])
        if not resources:
            self.migration_report["warnings"].append(
                "Kustomize rendered no resources; the generated chart will be empty"
            )
        if any(resource.get("kind") == "Secret" for resource in resources):
            self.migration_report["warnings"].append(
                "Rendered Secret data is stored in values.yaml; protect the generated "
                "chart as sensitive"
            )
        generate_names = [
            resource.get("kind", "Unknown")
            for resource in resources
            if not resource.get("metadata", {}).get("name")
            and resource.get("metadata", {}).get("generateName")
        ]
        if generate_names:
            self.migration_report["warnings"].append(
                "Resources using metadata.generateName are not upgrade-stable in Helm: "
                + ", ".join(generate_names)
            )
        helm_annotations = find_helm_behavior_annotations(resources)
        if helm_annotations:
            message = (
                "Source resources contain Helm behavioral annotations that are inert in "
                "Kustomize but active in Helm: " + ", ".join(helm_annotations)
            )
            self.migration_report["warnings"].append(message)
            if fail_on_helm_annotations:
                raise ConfigurationError(message + ". Remove or explicitly redesign them first.")
        if any(resource.get("kind") == "CustomResourceDefinition" for resource in resources):
            self.migration_report["warnings"].append(
                "CRDs are preserved in templates so upgrades remain faithful; review your "
                "organization's CRD lifecycle policy before installation"
            )

    def _generate_helm_chart(self) -> None:
        validator = None
        if self.verify:
            if not HelmValidator.is_available():
                raise ConfigurationError(
                    "Helm was not found; install Helm or pass verify=False/--no-verify explicitly"
                )
            helm_validator = HelmValidator(timeout=self.timeout)

            def validator(staged_chart: Path) -> None:
                helm_validator.verify_equivalence(
                    staged_chart,
                    self.kustomize_data["resources"],
                    context=str(self.kustomize_dir),
                )

        self.generator.generate_chart(
            self.kustomize_data,
            pre_install_validator=validator,
        )
        if validator:
            self.migration_report["validation"] = "passed"
        elif not self.verify:
            self.migration_report["validation"] = "skipped-by-user"

    def analyze_only(self) -> Dict[str, Any]:
        """Analyze rendered output without creating a chart."""
        self.migration_report = self._new_report()
        self._parse_kustomize()
        self._analyze_configuration(fail_on_helm_annotations=False)
        return {
            "source_directory": str(self.kustomize_dir),
            "chart_name": self.chart_name,
            "renderer": self.kustomize_data.get("renderer"),
            "resources_found": len(self.kustomize_data.get("resources", [])),
            "patches_found": len(self.kustomize_data.get("patches", [])),
            "config_maps_found": self.migration_report["config_maps_generated"],
            "secrets_found": self.migration_report["secrets_generated"],
            "warnings": list(self.migration_report["warnings"]),
            "errors": list(self.migration_report["errors"]),
            "kustomization_features": sorted(self.kustomize_data.get("kustomization", {})),
            "resource_types": self._get_resource_types(),
            "migration_complexity": self._assess_migration_complexity(),
        }

    def _get_resource_types(self) -> Dict[str, int]:
        resource_types: Dict[str, int] = {}
        for resource in self.kustomize_data.get("resources", []):
            kind = resource.get("kind", "Unknown")
            resource_types[kind] = resource_types.get(kind, 0) + 1
        return dict(sorted(resource_types.items()))

    def _assess_migration_complexity(self) -> str:
        data = self.kustomize_data
        score = len(data.get("resources", []))
        score += len(data.get("patches", [])) * 2
        score += len(data.get("configMaps", []))
        score += len(data.get("secrets", []))
        source = data.get("kustomization", {})
        score += sum(3 for key in ("generators", "transformers", "validators") if key in source)
        if score < 5:
            return "Low"
        if score < 15:
            return "Medium"
        return "High"
