"""Exact structural comparison for fully rendered Kustomize overlays."""

from typing import Any, Dict, List, Set

from .errors import ConfigurationError
from .resources import identity_text, index_resources


class OverlayAnalyzer:
    """Describe resources and fields added, removed, or changed by overlays."""

    def __init__(self):
        self.resources_by_overlay: Dict[str, List[Dict[str, Any]]] = {}
        self.differences: Dict[str, Dict[str, Any]] = {}
        self.parameterizable_paths: Set[str] = set()

    def analyze_differences(self, overlay_resources: Dict[str, List[Dict[str, Any]]]) -> None:
        if "base" not in overlay_resources:
            raise ConfigurationError("Overlay analysis requires a 'base' resource set")
        self.resources_by_overlay = overlay_resources
        self.differences = {}
        self.parameterizable_paths = set()
        base = index_resources(overlay_resources["base"])

        for overlay_name in sorted(name for name in overlay_resources if name != "base"):
            overlay = index_resources(overlay_resources[overlay_name])
            changes: Dict[str, Any] = {}
            for identity in sorted(set(base) | set(overlay)):
                key = identity_text(identity)
                if identity not in base:
                    changes[key] = {"change": "added", "resource": overlay[identity]}
                elif identity not in overlay:
                    changes[key] = {"change": "removed"}
                elif base[identity] != overlay[identity]:
                    fields: Dict[str, Any] = {}
                    self._deep_compare(base[identity], overlay[identity], "", fields)
                    changes[key] = {"change": "modified", "fields": fields}
                    self.parameterizable_paths.update(fields)
            self.differences[overlay_name] = changes

    def _deep_compare(self, base: Any, overlay: Any, path: str, result: Dict[str, Any]) -> None:
        if type(base) is not type(overlay):
            result[path or "$resource"] = overlay
            return
        if isinstance(base, dict):
            for key in sorted(set(base) | set(overlay), key=str):
                new_path = f"{path}.{key}" if path else str(key)
                if key not in overlay:
                    result[new_path] = {"$delete": True}
                elif key not in base:
                    result[new_path] = overlay[key]
                else:
                    self._deep_compare(base[key], overlay[key], new_path, result)
            return
        if isinstance(base, list):
            if base != overlay:
                result[path] = overlay
            return
        if base != overlay:
            result[path] = overlay

    def get_parameterizable_differences(self) -> Dict[str, Dict[str, Any]]:
        """Return full, lossless differences grouped by overlay."""
        return self.differences

    def get_analysis_summary(self) -> Dict[str, Any]:
        return {
            "overlays_analyzed": len(self.differences),
            "total_differences": sum(len(changes) for changes in self.differences.values()),
            "parameterizable_paths": sorted(self.parameterizable_paths),
            "differences_by_overlay": {
                name: len(changes) for name, changes in sorted(self.differences.items())
            },
        }
