# CLI reference

The canonical project overview is in [README.md](README.md).

## Global options

```text
k2h [--verbose] [--version] COMMAND
```

`--verbose` enables diagnostic logging and tracebacks. Normal warnings and logs
are sent to stderr so JSON/YAML report output remains machine-readable.

## `k2h migrate`

```text
k2h migrate KUSTOMIZE_DIR OUTPUT_DIR [OPTIONS]
```

Important options:

- `--chart-name NAME`: explicit lowercase Helm chart name
- `--dry-run`: run Kustomize and analysis without writing
- `--force`: transactionally replace an existing chart after validation passes
- `--no-verify`: skip Helm lint and source-equivalence validation
- `--timeout SECONDS`: timeout for every external command (default: 120)
- `-f, --output-format text|json|yaml`: report format
- `--overlays-dir DIR`: enable multi-overlay mode using `KUSTOMIZE_DIR` as the base
- `--base-dir DIR`: compatibility alias that must match `KUSTOMIZE_DIR`

Examples:

```bash
k2h migrate ./base ./charts --chart-name api
k2h migrate ./base ./charts --chart-name api --dry-run -f json
k2h migrate ./base ./charts --overlays-dir ./overlays -n api
```

Exit status is non-zero for malformed YAML, failed Kustomize builds, duplicate
resource identities, unsafe destination paths, Helm lint failures, or semantic
differences between source and generated output.

## `k2h analyze`

```bash
k2h analyze KUSTOMIZE_DIR [-f text|json|yaml] [-o FILE] [--timeout SECONDS]
```

Analysis invokes Kustomize, so broken references and patches are reported even
though no chart is written.

## `k2h validate`

```bash
k2h validate CHART_DIR [--strict]
```

The command checks chart structure and YAML, runs strict Helm lint, and renders all
templates. `--strict` also makes a missing Helm executable fatal.

## `k2h init`

```bash
k2h init --chart-name api --output-dir ./charts
```

Creates a minimal empty chart. Migration itself does not require this step.
