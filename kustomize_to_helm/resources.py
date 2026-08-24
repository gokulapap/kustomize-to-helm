"""Helpers for validating, identifying, and comparing Kubernetes resources."""

import copy
import hashlib
import re
from typing import Any, Dict, Iterable, List, Mapping, Tuple

from .errors import ConfigurationError, ValidationError

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_HELM_BEHAVIOR_ANNOTATIONS = {"helm.sh/hook", "helm.sh/resource-policy"}


def resource_identity(resource: Mapping[str, Any]) -> Tuple[str, str, str, str]:
    """Return a stable Kubernetes identity tuple for a resource."""
    api_version = resource.get("apiVersion")
    kind = resource.get("kind")
    metadata = resource.get("metadata")
    if not isinstance(api_version, str) or not api_version.strip():
        raise ConfigurationError("Rendered resource is missing a non-empty apiVersion")
    if not isinstance(kind, str) or not kind.strip():
        raise ConfigurationError("Rendered resource is missing a non-empty kind")
    if not isinstance(metadata, dict):
        raise ConfigurationError(f"Rendered {kind} resource is missing metadata")

    name = metadata.get("name")
    generate_name = metadata.get("generateName")
    if not isinstance(name, str) or not name.strip():
        if isinstance(generate_name, str) and generate_name.strip():
            name = f"generate:{generate_name}"
        else:
            raise ConfigurationError(f"Rendered {kind} resource is missing metadata.name")

    namespace = metadata.get("namespace", "")
    if namespace is None:
        namespace = ""
    if not isinstance(namespace, str):
        raise ConfigurationError(f"Rendered {kind}/{name} has a non-string metadata.namespace")
    return api_version, kind, namespace, name


def identity_text(identity: Tuple[str, str, str, str]) -> str:
    """Return a readable identity string suitable for errors and reports."""
    api_version, kind, namespace, name = identity
    scope = f"{namespace}/" if namespace else ""
    return f"{api_version}:{kind}:{scope}{name}"


def resource_key(resource: Mapping[str, Any]) -> str:
    """Create a readable, collision-resistant Helm values key."""
    identity = resource_identity(resource)
    readable = "-".join(part for part in (identity[1], identity[2], identity[3]) if part)
    slug = _SLUG_RE.sub("-", readable.lower()).strip("-") or "resource"
    digest = hashlib.sha256("\0".join(identity).encode("utf-8")).hexdigest()[:10]
    return f"{slug[:50].rstrip('-')}-{digest}"


def index_resources(
    resources: Iterable[Mapping[str, Any]],
) -> Dict[Tuple[str, str, str, str], Dict[str, Any]]:
    """Validate and index resources, rejecting identities Helm cannot manage safely."""
    indexed: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
    for position, resource in enumerate(resources, start=1):
        if not isinstance(resource, dict):
            raise ConfigurationError(
                f"Rendered YAML document {position} must be a mapping, got "
                f"{type(resource).__name__}"
            )
        identity = resource_identity(resource)
        if identity in indexed:
            raise ConfigurationError(
                f"Duplicate rendered resource identity: {identity_text(identity)}"
            )
        indexed[identity] = copy.deepcopy(resource)
    return indexed


def canonical_resources(
    resources: Iterable[Mapping[str, Any]],
) -> Dict[Tuple[str, str, str, str], Dict[str, Any]]:
    """Return resources in a comparison-friendly mapping."""
    return index_resources(resources)


def assert_resource_equivalence(
    expected: Iterable[Mapping[str, Any]],
    actual: Iterable[Mapping[str, Any]],
    context: str,
) -> None:
    """Raise a concise error when two rendered resource sets differ."""
    expected_index = canonical_resources(expected)
    actual_index = canonical_resources(actual)
    expected_ids = set(expected_index)
    actual_ids = set(actual_index)

    missing = sorted(expected_ids - actual_ids)
    unexpected = sorted(actual_ids - expected_ids)
    changed = sorted(
        identity
        for identity in expected_ids & actual_ids
        if expected_index[identity] != actual_index[identity]
    )
    if not (missing or unexpected or changed):
        return

    details: List[str] = []
    if missing:
        details.append("missing=" + ", ".join(identity_text(item) for item in missing[:5]))
    if unexpected:
        details.append("unexpected=" + ", ".join(identity_text(item) for item in unexpected[:5]))
    if changed:
        details.append("changed=" + ", ".join(identity_text(item) for item in changed[:5]))
    raise ValidationError(f"Helm render differs from {context}: {'; '.join(details)}")


def find_helm_behavior_annotations(resources: Iterable[Mapping[str, Any]]) -> List[str]:
    """Find source annotations that become active only after migration to Helm."""
    findings = []
    for resource in resources:
        metadata = resource.get("metadata", {})
        annotations = metadata.get("annotations", {}) if isinstance(metadata, dict) else {}
        if not isinstance(annotations, dict):
            continue
        special = sorted(_HELM_BEHAVIOR_ANNOTATIONS & set(annotations))
        if special:
            findings.append(f"{identity_text(resource_identity(resource))} ({', '.join(special)})")
    return findings
