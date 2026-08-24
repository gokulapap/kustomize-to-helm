"""Compatibility helpers for callers that inspect parameterizable fields.

Chart generation itself is fidelity-first and does not rewrite manifests. This
module therefore performs only conservative extraction and never changes names,
selectors, references, or custom-resource fields.
"""

import copy
from typing import Any, Dict, List

from .resources import resource_key


class TemplateConverter:
    """Conservatively copy resources and expose common fields by resource."""

    def __init__(self, chart_name: str):
        self.chart_name = chart_name

    def convert_resource(
        self, resource: Dict[str, Any], extracted_values: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Return a clean deep copy; lossy implicit templating is intentionally avoided."""
        converted = copy.deepcopy(resource)
        converted.pop("_source_file", None)
        return converted

    def extract_parameterizable_values(self, resources: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract common workload fields without collisions between resources."""
        extracted: Dict[str, Any] = {"workloads": {}}
        for resource in resources:
            values = self._extract_resource(resource)
            if values:
                extracted["workloads"][resource_key(resource)] = values
        if not extracted["workloads"]:
            return {}
        return extracted

    def _extract_resource(self, resource: Dict[str, Any]) -> Dict[str, Any]:
        values: Dict[str, Any] = {}
        spec = resource.get("spec", {})
        if not isinstance(spec, dict):
            return values
        if "replicas" in spec:
            values["replicas"] = copy.deepcopy(spec["replicas"])

        pod_spec = spec.get("template", {}).get("spec", {})
        containers = pod_spec.get("containers", []) if isinstance(pod_spec, dict) else []
        if isinstance(containers, list) and containers:
            container_values = []
            for container in containers:
                if not isinstance(container, dict):
                    continue
                item = {
                    key: copy.deepcopy(container[key])
                    for key in (
                        "name",
                        "image",
                        "imagePullPolicy",
                        "resources",
                    )
                    if key in container
                }
                if item:
                    container_values.append(item)
            if container_values:
                values["containers"] = container_values

        if resource.get("kind") == "Service":
            values["service"] = {
                key: copy.deepcopy(spec[key]) for key in ("type", "ports") if key in spec
            }
        if resource.get("kind") in ("ConfigMap", "Secret"):
            for field in ("data", "stringData", "binaryData", "type"):
                if field in resource:
                    values[field] = copy.deepcopy(resource[field])
        return values
