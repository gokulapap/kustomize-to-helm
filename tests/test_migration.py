import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from kustomize_to_helm.cli import cli
from kustomize_to_helm.errors import BuildError, ConfigurationError, GenerationError
from kustomize_to_helm.helm_generator import HelmChartGenerator, validate_chart_name
from kustomize_to_helm.kustomize_parser import KustomizeParser
from kustomize_to_helm.migrator import KustomizeToHelmMigrator
from kustomize_to_helm.multi_overlay_migrator import MultiOverlayMigrator
from kustomize_to_helm.resources import assert_resource_equivalence
from kustomize_to_helm.validation import HelmValidator

FIXTURES = Path(__file__).parent / "fixtures" / "application"
HAS_KUSTOMIZE = bool(shutil.which("kustomize") or shutil.which("kubectl"))
HAS_HELM = bool(shutil.which("helm"))


@unittest.skipUnless(HAS_KUSTOMIZE, "Kustomize is required for integration tests")
class ParserTests(unittest.TestCase):
    def test_build_command_must_be_an_argument_sequence(self):
        with self.assertRaises(ConfigurationError):
            KustomizeParser(FIXTURES / "base", build_command="kustomize build")
        with self.assertRaises(ConfigurationError):
            KustomizeParser(FIXTURES / "base", build_command=[])

    def test_build_applies_generators_and_preserves_sensitive_values(self):
        data = KustomizeParser(FIXTURES / "base").parse()
        kinds = [resource["kind"] for resource in data["resources"]]
        self.assertEqual(kinds.count("ConfigMap"), 1)
        self.assertEqual(kinds.count("Secret"), 1)
        config_map = next(item for item in data["resources"] if item["kind"] == "ConfigMap")
        secret = next(item for item in data["resources"] if item["kind"] == "Secret")
        self.assertEqual(config_map["data"]["template"], "{{ untouched }}")
        self.assertEqual(secret["data"]["password"], "Y29ycmVjdC1ob3JzZQ==")

    def test_overlay_build_applies_patch_image_replica_and_delete(self):
        resources = KustomizeParser(FIXTURES / "overlays" / "dev").parse()["resources"]
        self.assertNotIn("Service", {resource["kind"] for resource in resources})
        deployment = next(item for item in resources if item["kind"] == "Deployment")
        self.assertEqual(deployment["metadata"]["namespace"], "development")
        self.assertEqual(deployment["spec"]["replicas"], 4)
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["image"], "registry.example.com:5000/platform/nginx:2.0")
        self.assertEqual(container["resources"]["requests"]["cpu"], "100m")

    def test_bad_reference_is_a_hard_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / "kustomization.yaml").write_text(
                "resources:\n  - missing.yaml\n", encoding="utf-8"
            )
            with self.assertRaises(BuildError):
                KustomizeParser(path).parse()

    def test_duplicate_kustomization_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / "kustomization.yaml").write_text(
                "kind: Kustomization\nresources: []\nresources: []\n", encoding="utf-8"
            )
            with self.assertRaises(ConfigurationError):
                KustomizeParser(path).parse()


class GeneratorUnitTests(unittest.TestCase):
    def test_invalid_chart_names_are_rejected(self):
        for name in ("Bad_Name", "bad.name", "-bad", "bad-", ""):
            with self.subTest(name=name), self.assertRaises(ConfigurationError):
                validate_chart_name(name)

    def test_duplicate_resource_identity_is_rejected(self):
        resource = {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "same"}}
        with tempfile.TemporaryDirectory() as temp:
            generator = HelmChartGenerator("valid", temp)
            with self.assertRaises(ConfigurationError):
                generator.generate_chart({"resources": [resource, resource], "kustomization": {}})

    def test_failed_pre_install_validation_preserves_existing_chart(self):
        resource = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "safe"},
        }
        with tempfile.TemporaryDirectory() as temp:
            chart = Path(temp) / "valid"
            chart.mkdir()
            sentinel = chart / "keep.txt"
            sentinel.write_text("original", encoding="utf-8")
            generator = HelmChartGenerator("valid", temp, overwrite=True)

            def fail_validation(_staged_chart):
                raise RuntimeError("validation failed")

            with self.assertRaisesRegex(RuntimeError, "validation failed"):
                generator.generate_chart(
                    {"resources": [resource], "kustomization": {}},
                    pre_install_validator=fail_validation,
                )
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "original")

    def test_overlay_filename_collisions_are_rejected(self):
        resource = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "safe"},
        }
        with tempfile.TemporaryDirectory() as temp:
            generator = HelmChartGenerator("valid", temp)
            with self.assertRaises(ConfigurationError):
                generator.generate_chart(
                    {"resources": [resource], "kustomization": {}},
                    overlay_resources={"DEV": [resource], "dev": [resource]},
                )


class CliUnitTests(unittest.TestCase):
    def test_init_rejects_invalid_semver_without_partial_chart(self):
        with tempfile.TemporaryDirectory() as temp:
            result = CliRunner().invoke(
                cli,
                [
                    "init",
                    "--chart-name",
                    "sample",
                    "--output-dir",
                    temp,
                    "--version",
                    "not-semver",
                ],
            )
            self.assertNotEqual(result.exit_code, 0)
            self.assertFalse((Path(temp) / "sample").exists())


@unittest.skipUnless(HAS_KUSTOMIZE and HAS_HELM, "Kustomize and Helm are required")
class MigrationIntegrationTests(unittest.TestCase):
    def test_single_migration_is_equivalent_and_literal_templates_survive(self):
        with tempfile.TemporaryDirectory() as temp:
            migrator = KustomizeToHelmMigrator(
                FIXTURES / "base", temp, chart_name="sample", verify=True
            )
            report = migrator.migrate()
            self.assertEqual(report["status"], "success")
            self.assertEqual(report["validation"], "passed")
            chart = Path(temp) / "sample"
            rendered = HelmValidator().render(chart)
            expected = KustomizeParser(FIXTURES / "base").parse()["resources"]
            assert_resource_equivalence(expected, rendered, "test base")
            rendered_config = next(item for item in rendered if item["kind"] == "ConfigMap")
            self.assertEqual(rendered_config["data"]["template"], "{{ untouched }}")

    def test_multi_overlay_migration_handles_add_change_and_remove(self):
        with tempfile.TemporaryDirectory() as temp:
            migrator = MultiOverlayMigrator(
                FIXTURES / "base",
                FIXTURES / "overlays",
                temp,
                chart_name="sample",
                verify=True,
            )
            report = migrator.migrate()
            self.assertEqual(report["overlays_processed"], 1)
            self.assertEqual(report["values_files_generated"], 2)
            self.assertEqual(report["validation"], "passed")
            chart = Path(temp) / "sample"
            actual = HelmValidator().render(chart, (chart / "values-dev.yaml",))
            expected = KustomizeParser(FIXTURES / "overlays" / "dev").parse()["resources"]
            assert_resource_equivalence(expected, actual, "test overlay")

    def test_existing_chart_requires_force_and_force_removes_stale_files(self):
        with tempfile.TemporaryDirectory() as temp:
            first = KustomizeToHelmMigrator(FIXTURES / "base", temp, chart_name="sample")
            first.migrate()
            stale = Path(temp) / "sample" / "stale.txt"
            stale.write_text("stale", encoding="utf-8")
            with self.assertRaises(GenerationError):
                KustomizeToHelmMigrator(FIXTURES / "base", temp, chart_name="sample").migrate()
            self.assertTrue(stale.exists())
            KustomizeToHelmMigrator(
                FIXTURES / "base", temp, chart_name="sample", overwrite=True
            ).migrate()
            self.assertFalse(stale.exists())

    def test_cli_json_output_is_machine_readable(self):
        with tempfile.TemporaryDirectory() as temp:
            result = CliRunner().invoke(
                cli,
                [
                    "migrate",
                    str(FIXTURES / "base"),
                    temp,
                    "--chart-name",
                    "sample",
                    "--output-format",
                    "json",
                ],
            )
            self.assertEqual(result.exit_code, 0, result.output)
            report = json.loads(result.stdout)
            self.assertEqual(report["validation"], "passed")

    def test_cli_uses_positional_source_as_overlay_base(self):
        with tempfile.TemporaryDirectory() as temp:
            result = CliRunner().invoke(
                cli,
                [
                    "migrate",
                    str(FIXTURES / "base"),
                    temp,
                    "--overlays-dir",
                    str(FIXTURES / "overlays"),
                    "--chart-name",
                    "sample",
                    "--output-format",
                    "json",
                ],
            )
            self.assertEqual(result.exit_code, 0, result.output)
            report = json.loads(result.stdout)
            self.assertEqual(report["overlays_processed"], 1)

    def test_missing_helm_requires_explicit_no_verify(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(HelmValidator, "is_available", return_value=False):
                with self.assertRaises(ConfigurationError):
                    KustomizeToHelmMigrator(FIXTURES / "base", temp, chart_name="sample").migrate()
            self.assertFalse((Path(temp) / "sample").exists())

            with patch.object(HelmValidator, "is_available", return_value=False):
                report = KustomizeToHelmMigrator(
                    FIXTURES / "base",
                    temp,
                    chart_name="sample",
                    verify=False,
                ).migrate()
            self.assertEqual(report["validation"], "skipped-by-user")

    def test_stacked_overlay_values_use_the_last_overlay_enablement(self):
        resource = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "only-a"},
        }
        with tempfile.TemporaryDirectory() as temp:
            generator = HelmChartGenerator("sample", temp)
            generator.generate_chart(
                {"resources": [], "kustomization": {}},
                overlay_resources={"a": [resource], "b": []},
            )
            chart = Path(temp) / "sample"
            rendered = HelmValidator().render(
                chart,
                (chart / "values-a.yaml", chart / "values-b.yaml"),
            )
            self.assertEqual(rendered, [])

    def test_helm_behavior_annotations_are_reported_and_block_migration(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.mkdir()
            (source / "kustomization.yaml").write_text(
                "resources:\n  - configmap.yaml\n", encoding="utf-8"
            )
            (source / "configmap.yaml").write_text(
                """apiVersion: v1
kind: ConfigMap
metadata:
  name: hook-like
  annotations:
    helm.sh/hook: pre-install
data: {}
""",
                encoding="utf-8",
            )
            migrator = KustomizeToHelmMigrator(
                source,
                Path(temp) / "output",
                chart_name="blocked",
                verify=False,
            )
            analysis = migrator.analyze_only()
            self.assertTrue(
                any("Helm behavioral annotations" in warning for warning in analysis["warnings"])
            )
            with self.assertRaisesRegex(ConfigurationError, "Helm behavioral annotations"):
                migrator.migrate()
            self.assertFalse((Path(temp) / "output" / "blocked").exists())


if __name__ == "__main__":
    unittest.main()
