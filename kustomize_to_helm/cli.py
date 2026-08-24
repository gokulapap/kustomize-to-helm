"""Command-line interface for kustomize-to-helm."""

import json
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

import click
import yaml

from . import __version__
from .errors import MigrationError
from .helm_generator import validate_chart_name, validate_chart_version
from .migrator import KustomizeToHelmMigrator
from .multi_overlay_migrator import MultiOverlayMigrator
from .validation import HelmValidator


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
        force=True,
    )


@click.group()
@click.version_option(version=__version__)
@click.option("--verbose", "-v", is_flag=True, help="Show debug logging and tracebacks.")
@click.pass_context
def cli(ctx, verbose):
    """Convert rendered Kustomize configurations into verified Helm charts."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    setup_logging(verbose)


@cli.command()
@click.argument("kustomize_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("output_dir", type=click.Path(file_okay=False, path_type=Path))
@click.option("--chart-name", "-n", help="Helm chart name; defaults to the source directory.")
@click.option(
    "--base-dir",
    "-b",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Base directory for a base-plus-overlays migration.",
)
@click.option(
    "--overlays-dir",
    "-o",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Directory whose immediate subdirectories are Kustomize overlays.",
)
@click.option("--dry-run", is_flag=True, help="Render and analyze without writing a chart.")
@click.option("--force", is_flag=True, help="Transactionally replace an existing chart directory.")
@click.option("--no-verify", is_flag=True, help="Skip Helm lint and semantic equivalence checks.")
@click.option(
    "--timeout",
    type=click.IntRange(min=1),
    default=120,
    show_default=True,
    help="Timeout in seconds for each Kustomize or Helm command.",
)
@click.option(
    "--output-format",
    "-f",
    type=click.Choice(["json", "yaml", "text"]),
    default="text",
    show_default=True,
)
@click.pass_context
def migrate(
    ctx,
    kustomize_dir,
    output_dir,
    chart_name,
    base_dir,
    overlays_dir,
    dry_run,
    force,
    no_verify,
    timeout,
    output_format,
):
    """Migrate KUSTOMIZE_DIR into a chart below OUTPUT_DIR."""
    verbose = ctx.obj.get("verbose", False)
    if base_dir and not overlays_dir:
        raise click.UsageError("--base-dir requires --overlays-dir")
    if base_dir and base_dir.resolve() != kustomize_dir.resolve():
        raise click.UsageError("KUSTOMIZE_DIR and --base-dir must refer to the same directory")
    try:
        if overlays_dir:
            migrator = MultiOverlayMigrator(
                base_dir=base_dir or kustomize_dir,
                overlays_dir=overlays_dir,
                output_dir=output_dir,
                chart_name=chart_name,
                dry_run=dry_run,
                overwrite=force,
                verify=not no_verify,
                timeout=timeout,
            )
        else:
            migrator = KustomizeToHelmMigrator(
                kustomize_dir=kustomize_dir,
                output_dir=output_dir,
                chart_name=chart_name,
                dry_run=dry_run,
                overwrite=force,
                verify=not no_verify,
                timeout=timeout,
            )
        report = migrator.migrate()
        _display_migration_report(report, output_format)
    except Exception as exc:
        if verbose:
            raise
        raise click.ClickException(str(exc)) from exc


@cli.command()
@click.argument("kustomize_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--output-format",
    "-f",
    type=click.Choice(["json", "yaml", "text"]),
    default="text",
    show_default=True,
)
@click.option("--output-file", "-o", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--timeout", type=click.IntRange(min=1), default=120, show_default=True)
@click.pass_context
def analyze(ctx, kustomize_dir, output_format, output_file, timeout):
    """Render and analyze KUSTOMIZE_DIR without generating a chart."""
    verbose = ctx.obj.get("verbose", False)
    try:
        migrator = KustomizeToHelmMigrator(
            kustomize_dir=kustomize_dir,
            output_dir=Path.cwd(),
            dry_run=True,
            timeout=timeout,
        )
        report = migrator.analyze_only()
        if output_file:
            _save_report_to_file(report, output_file, output_format)
        else:
            _display_analysis_report(report, output_format)
    except Exception as exc:
        if verbose:
            raise
        raise click.ClickException(str(exc)) from exc


@cli.command()
@click.option("--chart-name", "-n", prompt="Chart name")
@click.option("--output-dir", "-o", type=click.Path(path_type=Path), default=Path("."))
@click.option("--description", "-d")
@click.option("--version", default="0.1.0", show_default=True)
@click.option("--app-version", default="1.0.0", show_default=True)
def init(chart_name, output_dir, description, version, app_version):
    """Initialize an empty Helm chart scaffold."""
    staging_root = None
    try:
        validate_chart_name(chart_name)
        validate_chart_version(version)
        output_path = output_dir.expanduser().resolve()
        output_path.mkdir(parents=True, exist_ok=True)
        chart_path = output_path / chart_name
        if chart_path.exists():
            raise click.ClickException(f"Directory already exists: {chart_path}")
        staging_root = Path(tempfile.mkdtemp(prefix=".k2h-init-", dir=str(output_path)))
        staged_chart = staging_root / chart_name
        templates = staged_chart / "templates"
        templates.mkdir(parents=True)
        chart = {
            "apiVersion": "v2",
            "name": chart_name,
            "description": description or f"A Helm chart for {chart_name}",
            "type": "application",
            "version": version,
            "appVersion": app_version,
        }
        (staged_chart / "Chart.yaml").write_text(
            yaml.safe_dump(chart, sort_keys=False), encoding="utf-8"
        )
        (staged_chart / "values.yaml").write_text("{}\n", encoding="utf-8")
        (staged_chart / ".helmignore").write_text(".git/\n.DS_Store\n*.tmp\n", encoding="utf-8")
        os.replace(staged_chart, chart_path)
        click.echo(str(chart_path))
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    finally:
        if staging_root:
            shutil.rmtree(staging_root, ignore_errors=True)


@cli.command()
@click.argument("chart_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--strict", is_flag=True, help="Fail if Helm is unavailable.")
def validate(chart_dir, strict):
    """Validate chart structure, lint it, and render every template."""
    result = HelmValidator.inspect_structure(chart_dir)
    issues = result["issues"]
    warnings = result["warnings"]
    if not issues:
        if HelmValidator.is_available():
            try:
                validator = HelmValidator()
                validator.lint(chart_dir)
                validator.render(chart_dir)
                for values_file in sorted(chart_dir.glob("values-*.yaml")):
                    validator.lint(chart_dir, (values_file,))
                    validator.render(chart_dir, (values_file,))
            except MigrationError as exc:
                issues.append(str(exc))
        elif strict:
            issues.append("Helm is unavailable, so strict validation cannot run")
        else:
            warnings.append("Helm is unavailable; lint and render checks were skipped")

    for warning in warnings:
        click.echo(f"Warning: {warning}", err=True)
    if issues:
        raise click.ClickException("; ".join(issues))
    click.echo("Chart validation passed")


def _display_migration_report(report: Dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        click.echo(json.dumps(report, indent=2, sort_keys=True))
        return
    if output_format == "yaml":
        click.echo(yaml.safe_dump(report, sort_keys=False).rstrip())
        return

    click.echo("Migration completed successfully")
    click.echo(f"Chart: {report['target_directory']}")
    click.echo(f"Resources: {report['resources_migrated']}")
    if "overlays_processed" in report:
        click.echo(f"Overlays: {report['overlays_processed']}")
        click.echo(f"Values files: {report['values_files_generated']}")
    click.echo(f"Validation: {report['validation']}")
    for warning in report.get("warnings", []):
        click.echo(f"Warning: {warning}", err=True)


def _display_analysis_report(report: Dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        click.echo(json.dumps(report, indent=2, sort_keys=True))
    elif output_format == "yaml":
        click.echo(yaml.safe_dump(report, sort_keys=False).rstrip())
    else:
        click.echo(f"Source: {report['source_directory']}")
        click.echo(f"Resources: {report['resources_found']}")
        click.echo(f"Complexity: {report['migration_complexity']}")
        for kind, count in report["resource_types"].items():
            click.echo(f"  {kind}: {count}")
        for warning in report.get("warnings", []):
            click.echo(f"Warning: {warning}", err=True)


def _save_report_to_file(report: Dict[str, Any], output_file: Path, output_format: str) -> None:
    output_path = output_file.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "json":
        content = json.dumps(report, indent=2, sort_keys=True) + "\n"
    elif output_format == "yaml":
        content = yaml.safe_dump(report, sort_keys=False)
    else:
        content = "\n".join(f"{key}: {value}" for key, value in report.items()) + "\n"
    output_path.write_text(content, encoding="utf-8")


def main():
    cli()


if __name__ == "__main__":
    main()
