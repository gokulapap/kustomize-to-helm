# kustomize-to-helm

`kustomize-to-helm` converts a Kustomize application into a Helm chart.

The command-line tool is called `k2h`.

Its main goal is safety. A migration should not look correct while quietly
changing your Kubernetes resources. The tool therefore builds the source with
Kustomize, creates the Helm chart, renders that chart with Helm, and compares the
two results before reporting success.

## How it works

For a normal migration, the tool follows these steps:

1. Run `kustomize build` on the source.
2. Read and validate every rendered Kubernetes resource.
3. Generate a Helm chart from those final resources.
4. Run strict `helm lint` on the generated chart.
5. Run `helm template`.
6. Compare the complete Helm output with the Kustomize output.

If a resource is missing, added unexpectedly, or changed, the migration fails.
The destination is not replaced until validation passes.

The YAML text may use different whitespace, quotes, or key ordering. The parsed
Kubernetes objects—including names, namespaces, fields, lists, and values—must be
the same.

## What it supports

The tool works with final resources rendered by Kustomize, so it can preserve:

- strategic merge, JSON 6902, and unified patches;
- name prefixes, suffixes, namespaces, labels, and annotations;
- image names, tags, digests, and replica changes;
- ConfigMap and Secret generators, including generated name hashes;
- base and overlay resource additions, changes, renames, and deletions;
- Deployments, StatefulSets, DaemonSets, Jobs, CronJobs, and Services;
- RBAC, Ingress, Gateway API, autoscaling, policies, and storage resources;
- CRDs and arbitrary custom resources;
- multiple containers, init containers, volumes, probes, and security settings;
- multiline data and application text containing literal `{{ ... }}` expressions.

The framework does not try to recreate Kustomize behavior in Python. Kustomize
itself produces the source manifests used for migration.

## Requirements

- Python 3.8 or newer
- `kustomize` on `PATH`, or `kubectl` with `kubectl kustomize`
- Helm 3 on `PATH`

Helm is required for the normal verified migration. You can explicitly use
`--no-verify`, but that removes the equivalence guarantee.

## Installation

```bash
git clone <repository-url>
cd kustomize-to-helm

python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .

k2h --version
```

## Migrate one Kustomize configuration

First, inspect the source:

```bash
k2h analyze ./kustomize
```

Then create the chart:

```bash
k2h migrate ./kustomize ./charts --chart-name my-app
```

The generated chart is written to:

```text
charts/my-app/
```

Render it normally with Helm:

```bash
helm template my-release ./charts/my-app
```

## Migrate a base with overlays

Example source structure:

```text
app/
├── base/
│   └── kustomization.yaml
└── overlays/
    ├── dev/
    │   └── kustomization.yaml
    └── production/
        └── kustomization.yaml
```

Run:

```bash
k2h migrate ./app/base ./charts \
  --overlays-dir ./app/overlays \
  --chart-name my-app
```

The chart will contain separate values files:

```text
charts/my-app/
├── Chart.yaml
├── values.yaml
├── values-dev.yaml
├── values-production.yaml
├── MIGRATION.md
└── templates/
    ├── NOTES.txt
    └── resources.yaml
```

Render an environment with its values file:

```bash
helm template my-release ./charts/my-app \
  -f ./charts/my-app/values-production.yaml
```

Every immediate, non-hidden directory under `--overlays-dir` is treated as an
overlay. If one overlay is broken, the complete migration fails. Broken overlays
are never silently skipped.

## Why manifests are stored in values

Each Kubernetes resource is stored as a complete manifest in `values.yaml`:

```yaml
resources:
  deployment-api-2f89d8c1a0:
    enabled: true
    manifest: |
      apiVersion: apps/v1
      kind: Deployment
      metadata:
        name: api
      # ...the rest of the rendered resource...
```

This is intentional. Normal Helm map merging cannot faithfully represent every
field deletion, list replacement, generated resource, or custom resource.

Overlay files enable or disable the correct resources and replace only the
manifests that changed. This keeps the first migration accurate. After the chart
is verified, teams can gradually move selected fields into conventional Helm
values under their normal review process.

## Safe overwrite behavior

The tool will not overwrite an existing chart unless you pass `--force`:

```bash
k2h migrate ./kustomize ./charts --chart-name my-app --force
```

The replacement is transactional. The existing chart remains in place while the
new chart is generated and validated. If validation fails, the old chart is kept.

## Useful commands

Run without writing files:

```bash
k2h migrate ./kustomize ./charts --chart-name my-app --dry-run
```

Produce a JSON report:

```bash
k2h migrate ./kustomize ./charts --chart-name my-app --output-format json
```

Validate an existing chart:

```bash
k2h validate ./charts/my-app --strict
```

Replace an existing chart:

```bash
k2h migrate ./kustomize ./charts --chart-name my-app --force
```

Skip Helm verification explicitly:

```bash
k2h migrate ./kustomize ./charts --chart-name my-app --no-verify
```

## Errors the tool handles

The migration stops with a clear error for cases such as:

- invalid or duplicate YAML keys;
- missing files and broken Kustomize references;
- failed or timed-out Kustomize builds;
- duplicate Kubernetes resource identities;
- invalid Helm chart names or versions;
- overlay values filename collisions;
- failed Helm lint or rendering;
- any difference between Helm and Kustomize output;
- an existing destination without `--force`;
- failed validation during an overwrite.

The tool also blocks source `helm.sh/hook` and `helm.sh/resource-policy`
annotations. These annotations do nothing in Kustomize but change resource
lifecycle behavior in Helm, so automatically migrating them would be misleading.

## Secrets and CRDs

Rendered Secret data is copied into the generated values files. Treat the chart
as sensitive and use your normal secret-management process before committing it.

CRDs are kept in the chart templates so the generated output stays equal to the
Kustomize output. Review your organization's CRD installation and upgrade policy
before deploying the chart.

## What verification cannot cover

The tool verifies local rendered output. It cannot reproduce behavior that only
happens inside a Kubernetes cluster, including:

- API server default values;
- admission and mutation webhooks;
- cluster-specific API availability;
- changes made to live resources after installation.

Remote Kustomize resources also depend on network access and upstream
availability. Pin remote versions when possible.

Executable or alpha Kustomize plugins are not enabled automatically because they
may run code. Python callers can provide an explicit build command when those
features are required and trusted.

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
print(report["status"])
print(report["validation"])
```

To supply trusted custom Kustomize flags:

```python
migrator = KustomizeToHelmMigrator(
    kustomize_dir="./kustomize",
    output_dir="./charts",
    build_command=["kustomize", "build", "--enable-helm"],
)
```

The source directory is appended to the command by the framework.

## Tests

Run all checks locally:

```bash
ruff check .
python -m compileall -q kustomize_to_helm tests
python -m unittest discover -s tests -v
```

The test suite includes simple, failure, and critical-complexity migrations. The
critical fixture covers production and canary overlays, generated Secrets and
ConfigMaps, CRDs, custom resources, RBAC references, patches, deletion, image
digests, multiple containers, StatefulSets, policies, Gateway API, multiline
data, and literal Helm expressions.

The integration tests compare the complete parsed Kustomize and Helm outputs.
They skip automatically when Kustomize or Helm is not installed.
