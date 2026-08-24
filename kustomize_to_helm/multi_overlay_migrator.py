"""Base-plus-overlays migration orchestration."""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Union

from .errors import ConfigurationError
from .helm_generator import HelmChartGenerator, normalize_chart_name, validate_chart_name
from .kustomize_parser import DEFAULT_BUILD_TIMEOUT, KustomizeParser
from .overlay_analyzer import OverlayAnalyzer
from .resources import find_helm_behavior_annotations, resource_identity
from .validation import HelmValidator

logger = logging.getLogger(__name__)


class MultiOverlayMigrator:
    """Migrate a base and every immediate overlay to one verified Helm chart."""

    def __init__(
        self,
        base_dir: Union[str, Path],
        overlays_dir: Union[str, Path],
        output_dir: Union[str, Path],
        chart_name: Optional[str] = None,
        dry_run: bool = False,
        overwrite: bool = False,
        verify: bool = True,
        build_command: Optional[Sequence[str]] = None,
        timeout: int = DEFAULT_BUILD_TIMEOUT,
    ):
        self.base_dir = Path(base_dir).expanduser().resolve()
        self.overlays_dir = Path(overlays_dir).expanduser().resolve()
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.chart_name = (
            validate_chart_name(chart_name)
            if chart_name is not None
            else normalize_chart_name(self.base_dir.name)
        )
        self.dry_run = dry_run
        self.overwrite = overwrite
        self.verify = verify
        self.build_command = build_command
        self.timeout = timeout

        if not self.overlays_dir.is_dir():
            raise ConfigurationError(f"Overlays directory does not exist: {self.overlays_dir}")
        self.base_parser = KustomizeParser(
            self.base_dir,
            build_command=build_command,
            timeout=timeout,
        )
        self.overlay_parsers: Dict[str, KustomizeParser] = {}
        self.overlay_analyzer = OverlayAnalyzer()
        self.generator = HelmChartGenerator(
            self.chart_name,
            self.output_dir,
            overwrite=overwrite,
        )
        self.base_data: Dict[str, Any] = {}
        self.overlay_data: Dict[str, Dict[str, Any]] = {}
        self.overlay_names = []
        self.migration_report = self._new_report()

    def _new_report(self) -> Dict[str, Any]:
        return {
            "source_base_directory": str(self.base_dir),
            "source_overlays_directory": str(self.overlays_dir),
            "target_directory": str(self.output_dir / self.chart_name),
            "chart_name": self.chart_name,
            "overlays_processed": 0,
            "base_resources": 0,
            "resources_migrated": 0,
            "values_files_generated": 0,
            "parameters_extracted": 0,
            "resource_differences": 0,
            "validation": "not-run",
            "warnings": [],
            "errors": [],
            "status": "pending",
        }

    def migrate(self) -> Dict[str, Any]:
        self.migration_report = self._new_report()
        try:
            self._parse_base()
            self._discover_and_parse_overlays()
            self._analyze_overlay_differences()
            if self.dry_run:
                self.migration_report["validation"] = "dry-run"
            else:
                self._generate_chart()
            self.migration_report["status"] = "success"
            return self.migration_report
        except Exception as exc:
            self.migration_report["status"] = "failed"
            if str(exc) not in self.migration_report["errors"]:
                self.migration_report["errors"].append(str(exc))
            logger.error("Multi-overlay migration failed: %s", exc)
            raise

    def _parse_base(self) -> None:
        self.base_data = self.base_parser.parse()
        resources = self.base_data["resources"]
        self.migration_report["base_resources"] = len(resources)
        self.migration_report["warnings"].extend(self.base_data.get("warnings", []))

    def _discover_and_parse_overlays(self) -> None:
        overlay_dirs = sorted(
            (
                path
                for path in self.overlays_dir.iterdir()
                if path.is_dir() and not path.name.startswith(".")
            ),
            key=lambda path: path.name,
        )
        if not overlay_dirs:
            raise ConfigurationError(f"No overlay directories found in {self.overlays_dir}")

        failures = []
        for overlay_dir in overlay_dirs:
            try:
                parser = KustomizeParser(
                    overlay_dir,
                    build_command=self.build_command,
                    timeout=self.timeout,
                )
                data = parser.parse()
            except Exception as exc:
                failures.append(f"{overlay_dir.name}: {exc}")
                continue
            self.overlay_parsers[overlay_dir.name] = parser
            self.overlay_data[overlay_dir.name] = data
            self.migration_report["warnings"].extend(
                f"Overlay {overlay_dir.name}: {warning}" for warning in data.get("warnings", [])
            )

        if failures:
            raise ConfigurationError("Failed to render overlays: " + " | ".join(failures))
        self.overlay_names = sorted(self.overlay_data)
        self.migration_report["overlays_processed"] = len(self.overlay_names)

    def _analyze_overlay_differences(self) -> None:
        resources = {"base": self.base_data["resources"]}
        resources.update(
            {name: self.overlay_data[name]["resources"] for name in self.overlay_names}
        )
        self.overlay_analyzer.analyze_differences(resources)
        summary = self.overlay_analyzer.get_analysis_summary()
        self.migration_report["parameters_extracted"] = len(summary["parameterizable_paths"])
        self.migration_report["resource_differences"] = summary["total_differences"]
        identities = {
            resource_identity(resource)
            for resource_set in resources.values()
            for resource in resource_set
        }
        self.migration_report["resources_migrated"] = len(identities)

        all_resources = [resource for items in resources.values() for resource in items]
        if any(resource.get("kind") == "Secret" for resource in all_resources):
            self.migration_report["warnings"].append(
                "Rendered Secret data is stored in values files; protect the generated "
                "chart as sensitive"
            )
        helm_annotations = find_helm_behavior_annotations(all_resources)
        if helm_annotations:
            raise ConfigurationError(
                "Source resources contain Helm behavioral annotations that are inert in "
                "Kustomize but active in Helm: "
                + ", ".join(helm_annotations)
                + ". Remove or explicitly redesign them first."
            )
        if any(resource.get("kind") == "CustomResourceDefinition" for resource in all_resources):
            self.migration_report["warnings"].append(
                "CRDs are preserved in templates so upgrades remain faithful; review your "
                "organization's CRD lifecycle policy before installation"
            )

    def _generate_chart(self) -> None:
        overlay_resources = {
            name: self.overlay_data[name]["resources"] for name in self.overlay_names
        }
        pre_install_validator = None
        if self.verify:
            if not HelmValidator.is_available():
                raise ConfigurationError(
                    "Helm was not found; install Helm or pass verify=False/--no-verify explicitly"
                )
            helm_validator = HelmValidator(timeout=self.timeout)

            def pre_install_validator(staged_chart: Path) -> None:
                helm_validator.verify_equivalence(
                    staged_chart,
                    self.base_data["resources"],
                    context=f"base {self.base_dir}",
                )
                for overlay_name in self.overlay_names:
                    values_file = (
                        staged_chart
                        / f"values-{self.generator._safe_overlay_filename(overlay_name)}.yaml"
                    )
                    helm_validator.verify_equivalence(
                        staged_chart,
                        self.overlay_data[overlay_name]["resources"],
                        values_files=(values_file,),
                        context=f"overlay {overlay_name}",
                    )

        self.generator.generate_chart(
            self.base_data,
            overlay_resources=overlay_resources,
            pre_install_validator=pre_install_validator,
        )
        self.migration_report["values_files_generated"] = len(self.generator.generated_values_files)
        if pre_install_validator:
            self.migration_report["validation"] = "passed"
        elif not self.verify:
            self.migration_report["validation"] = "skipped-by-user"
