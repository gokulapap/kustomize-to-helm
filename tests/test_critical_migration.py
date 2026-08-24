import base64
import shutil
import tempfile
import unittest
from pathlib import Path

from kustomize_to_helm.kustomize_parser import KustomizeParser
from kustomize_to_helm.migrator import KustomizeToHelmMigrator
from kustomize_to_helm.multi_overlay_migrator import MultiOverlayMigrator
from kustomize_to_helm.resources import assert_resource_equivalence
from kustomize_to_helm.validation import HelmValidator

FIXTURE = Path(__file__).parent / "fixtures" / "critical"
HAS_KUSTOMIZE = bool(shutil.which("kustomize") or shutil.which("kubectl"))
HAS_HELM = bool(shutil.which("helm"))


def find_resource(resources, kind, name_fragment=None):
    matches = [resource for resource in resources if resource["kind"] == kind]
    if name_fragment:
        matches = [
            resource
            for resource in matches
            if name_fragment in resource.get("metadata", {}).get("name", "")
        ]
    if len(matches) != 1:
        raise AssertionError(
            f"Expected one {kind} containing {name_fragment!r}, found {len(matches)}"
        )
    return matches[0]


@unittest.skipUnless(HAS_KUSTOMIZE and HAS_HELM, "Kustomize and Helm are required")
class CriticalMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = KustomizeParser(FIXTURE / "base").parse()["resources"]
        cls.production = KustomizeParser(FIXTURE / "overlays" / "production").parse()["resources"]
        cls.canary = KustomizeParser(FIXTURE / "overlays" / "canary").parse()["resources"]

    def test_critical_source_exercises_hard_translation_cases(self):
        kinds = {resource["kind"] for resource in self.base}
        self.assertTrue(
            {
                "ClusterRole",
                "ClusterRoleBinding",
                "ConfigMap",
                "CronJob",
                "CustomResourceDefinition",
                "DaemonSet",
                "Deployment",
                "ExternalSecret",
                "HorizontalPodAutoscaler",
                "Ingress",
                "NetworkPolicy",
                "PersistentVolumeClaim",
                "PodDisruptionBudget",
                "RoleBinding",
                "Secret",
                "ServiceMonitor",
                "StatefulSet",
                "Widget",
            }.issubset(kinds)
        )

        config_map = find_resource(self.base, "ConfigMap", "runtime-config")
        self.assertEqual(config_map["data"]["TEMPLATE"], "{{ .application.mustRemainLiteral }}")
        self.assertIn("{{ must.not.be.rendered.by.helm }}", config_map["data"]["application.yaml"])
        self.assertIn("---", config_map["data"]["bootstrap.sh"])
        binary_config = find_resource(self.base, "ConfigMap", "binary-payload")
        self.assertEqual(binary_config["binaryData"]["payload.bin"], "AP8Q")

        secret = find_resource(self.base, "Secret", "api-credentials")
        decoded = base64.b64decode(secret["data"]["PASSWORD"]).decode("utf-8")
        self.assertEqual(decoded, "p@ss:w0rd=with=equals")

        deployment = find_resource(self.base, "Deployment", "api")
        containers = deployment["spec"]["template"]["spec"]["containers"]
        self.assertEqual(len(containers), 2)
        self.assertEqual(containers[0]["env"][0]["value"], "base.internal")
        self.assertIn("runtime-config", containers[0]["envFrom"][0]["configMapRef"]["name"])

        crd = find_resource(self.base, "CustomResourceDefinition", "widgets")
        self.assertNotIn("namespace", crd["metadata"])
        widget = find_resource(self.base, "Widget", "primary")
        self.assertEqual(widget["spec"]["nested"]["arbitrary"]["arrays"][0]["values"][3], None)
        external_secret = find_resource(self.base, "ExternalSecret", "api")
        self.assertIn(
            "{{ .username }}", external_secret["spec"]["target"]["template"]["data"]["config"]
        )
        ingress = find_resource(self.base, "Ingress", "api")
        self.assertEqual(ingress["spec"]["tls"][0]["secretName"], "core-api-tls")

    def test_critical_single_base_chart_is_exact(self):
        with tempfile.TemporaryDirectory() as temp:
            report = KustomizeToHelmMigrator(
                FIXTURE / "base", temp, chart_name="critical", verify=True
            ).migrate()
            self.assertEqual(report["validation"], "passed")
            actual = HelmValidator().render(Path(temp) / "critical")
            assert_resource_equivalence(self.base, actual, "critical base")

    def test_production_overlay_applies_digest_generators_and_deletions(self):
        kinds = {resource["kind"] for resource in self.production}
        self.assertNotIn("DaemonSet", kinds)
        self.assertIn("HTTPRoute", kinds)
        deployment = find_resource(self.production, "Deployment", "api")
        pod_spec = deployment["spec"]["template"]["spec"]
        self.assertEqual(deployment["spec"]["replicas"], 8)
        self.assertEqual(len(pod_spec["containers"]), 3)
        self.assertEqual(len(pod_spec["initContainers"]), 1)
        self.assertIn("@sha256:", pod_spec["containers"][0]["image"])

        stateful_set = find_resource(self.production, "StatefulSet", "database")
        limits = stateful_set["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]
        self.assertNotIn("cpu", limits)
        self.assertEqual(
            stateful_set["spec"]["persistentVolumeClaimRetentionPolicy"]["whenScaled"],
            "Delete",
        )

    def test_canary_overlay_applies_json_patches_and_resource_replacement(self):
        kinds = {resource["kind"] for resource in self.canary}
        self.assertNotIn("StatefulSet", kinds)
        self.assertIn("AnalysisRun", kinds)
        deployment = find_resource(self.canary, "Deployment", "api")
        self.assertEqual(deployment["spec"]["strategy"], {"type": "Recreate"})
        self.assertEqual(deployment["spec"]["replicas"], 1)
        pdb = find_resource(self.canary, "PodDisruptionBudget", "api")
        self.assertEqual(pdb["spec"]["minAvailable"], "50%")
        service = find_resource(self.canary, "Service", "api")
        self.assertEqual(service["spec"]["ports"][0]["port"], 8443)

    def test_every_critical_overlay_and_stacked_values_is_exact(self):
        with tempfile.TemporaryDirectory() as temp:
            report = MultiOverlayMigrator(
                FIXTURE / "base",
                FIXTURE / "overlays",
                temp,
                chart_name="critical",
                verify=True,
            ).migrate()
            self.assertEqual(report["status"], "success")
            self.assertEqual(report["validation"], "passed")
            self.assertEqual(report["overlays_processed"], 2)
            self.assertGreater(report["resource_differences"], 10)

            chart = Path(temp) / "critical"
            production_values = chart / "values-production.yaml"
            canary_values = chart / "values-canary.yaml"
            rendered_production = HelmValidator().render(chart, (production_values,))
            rendered_canary = HelmValidator().render(chart, (canary_values,))
            assert_resource_equivalence(
                self.production, rendered_production, "critical production overlay"
            )
            assert_resource_equivalence(self.canary, rendered_canary, "critical canary overlay")

            stacked = HelmValidator().render(chart, (production_values, canary_values))
            assert_resource_equivalence(self.canary, stacked, "last stacked overlay")


if __name__ == "__main__":
    unittest.main()
