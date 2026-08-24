# kustomize-to-helm

`kustomize-to-helm` (`k2h`) is a fidelity-first migration framework that turns a
Kustomize base—or a base plus all of its overlays—into a Helm chart and proves
that Helm renders the same Kubernetes resources.

The important design choice is simple: **Kustomize renders the source of truth**.
The framework does not attempt to reimplement strategic merge patches, JSON
patches, transformers, name references, generator hashes, image rewrites, or CRD
semantics in Python. It asks Kustomize for the final manifests, creates a
values-driven Helm resource catalog, runs `helm lint`, renders the chart, and
compares every resource to the Kustomize output before replacing the destination.

## What it handles

- Strategic merge, JSON 6902, and unified `patches`
- Name prefixes/suffixes, namespaces, labels, annotations, images, and replicas
- ConfigMap and Secret generators, including file/env inputs and hash suffixes
- Multiple containers, ports, arbitrary custom resources, and multi-document YAML
- Overlay-added, overlay-modified, renamed, and overlay-removed resources
- Literal application content containing `{{ ... }}` without evaluating it as Helm
- Duplicate YAML keys, broken references, build timeouts, duplicate Kubernetes
  identities, invalid chart names, missing tools, and unsafe overwrite attempts
- Transactional `--force`: the old chart stays intact until the replacement passes
  validation

## Requirements

- Python 3.8+
- [Kustomize](https://kubectl.docs.kubernetes.io/installation/kustomize/) on `PATH`,
  or `kubectl` with `kubectl kustomize`
- [Helm 3](https://helm.sh/docs/intro/install/) on `PATH` for the default lint and
  equivalence verification

Install locally:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
k2h --version
```

## Single configuration

```bash
k2h analyze ./kustomize
k2h migrate ./kustomize ./charts --chart-name my-app
helm template test ./charts/my-app
```

Use `--dry-run` to build and analyze without writing. A pre-existing chart is a
hard error unless `--force` is supplied. `--force` replaces it transactionally.

## Base plus overlays

Given:

```text
app/
├── base/
│   └── kustomization.yaml
└── overlays/
    ├── dev/kustomization.yaml
    └── prod/kustomization.yaml
```

Run:

```bash
k2h migrate ./app/base ./charts \
  --overlays-dir ./app/overlays \
  --chart-name my-app
```

This creates `values.yaml`, `values-dev.yaml`, and `values-prod.yaml`. Each file is
verified against its corresponding Kustomize build:

```bash
helm template test ./charts/my-app -f ./charts/my-app/values-dev.yaml
```

Every immediate, non-hidden directory below `--overlays-dir` is treated as an
overlay. A broken overlay fails the complete migration; it is never silently
skipped.

## Generated chart model

`values.yaml` contains a stable key for each Kubernetes identity:

```yaml
resources:
  deployment-default-api-2f89d8c1a0:
    enabled: true
    manifest: |
      apiVersion: apps/v1
      kind: Deployment
      # ...complete rendered resource...
```

Overlay values explicitly enable or disable every catalogued resource, so even
stacked values files are deterministic. They replace the complete manifest string
only for changed resources. Storing changed manifests as strings is intentional:
Helm's normal deep map merge cannot represent field deletion faithfully.

This model prioritizes safe migration over guessing which fields should become a
shared value. After equivalence is established, teams can refactor selected
manifest fields into conventional Helm values under normal review and testing.

## Validation and machine-readable reports

```bash
k2h validate ./charts/my-app --strict
k2h migrate ./kustomize ./charts -f json
k2h analyze ./kustomize -f yaml -o analysis.yaml
```

JSON and YAML modes write only the report to stdout; logs and warnings go to
stderr. Migration validation compares parsed Kubernetes objects by
`apiVersion`, `kind`, namespace, and name, then compares their complete content.

## Python API

```python
from kustomize_to_helm import KustomizeToHelmMigrator

migrator = KustomizeToHelmMigrator(
    kustomize_dir="./kustomize",
    output_dir="./charts",
    chart_name="my-app",
    overwrite=False,
    verify=True,
)
report = migrator.migrate()
```

For custom Kustomize flags, pass a command prefix through the API, for example
`build_command=["kustomize", "build", "--enable-helm"]`. The source directory is
appended by the framework. Alpha/exec plugins are not enabled automatically
because they may execute code.

## Security and limitations

- Rendered Secrets are necessarily copied into chart values. Treat the output as
  sensitive and use an external secret system before committing when appropriate.
- Remote Kustomize resources require network access and remain subject to upstream
  availability and pinning. Pin remote references for reproducible migrations.
- Verification proves local rendered-object equivalence. It does not reproduce API
  server defaulting, admission webhooks, cluster capabilities, or live-state drift.
- Resources using `metadata.generateName` are accepted with a warning because they
  are not upgrade-stable in Helm.
- Source `helm.sh/hook` and `helm.sh/resource-policy` annotations block migration:
  they are inert under Kustomize but change lifecycle behavior under Helm, so they
  require an explicit manual redesign instead of a misleading equivalence result.
- Helm verification may be skipped only when `--no-verify` is explicit. The
  skipped check is prominently recorded in the report.

## Development

```bash
python -m unittest discover -s tests -v
python -m compileall -q kustomize_to_helm
ruff check .
```

The critical integration fixture covers RBAC name references, generated
ConfigMaps/Secrets and hashes, replacements, strategic and JSON patches, field and
resource deletion, image digests with registry ports, multiple containers,
StatefulSets and PVC templates, HPA/PDB/NetworkPolicy, Ingress and Gateway API,
CRDs and arbitrary custom resources, components, multiline data, and literal Helm
tokens. Both production and canary overlays—as well as stacked values files—must
render identically to Kustomize. Integration tests automatically skip when
Kustomize or Helm is unavailable.
