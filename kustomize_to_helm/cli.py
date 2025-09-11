"""
CLI Module for Kustomize to Helm Migration Framework

Provides command-line interface for the migration tool.
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Optional

import click
import yaml

from .migrator import KustomizeToHelmMigrator
from . import __version__


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )


@click.group()
@click.version_option(version=__version__)
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.pass_context
def cli(ctx, verbose):
    """Kustomize to Helm Migration Framework
    
    A comprehensive tool for converting Kustomize configurations to Helm charts.
    """
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose
    setup_logging(verbose)


@cli.command()
@click.argument('kustomize_dir', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.argument('output_dir', type=click.Path(file_okay=False, dir_okay=True))
@click.option('--chart-name', '-n', help='Name for the Helm chart (defaults to kustomize directory name)')
@click.option('--base-dir', '-b', type=click.Path(exists=True, file_okay=False, dir_okay=True), 
              help='Base directory path (for multi-overlay setups)')
@click.option('--overlays-dir', '-o', type=click.Path(exists=True, file_okay=False, dir_okay=True),
              help='Overlays directory path (for multi-overlay setups)')
@click.option('--dry-run', is_flag=True, help='Analyze without creating files')
@click.option('--force', is_flag=True, help='Overwrite existing chart directory')
@click.option('--output-format', '-f', type=click.Choice(['json', 'yaml', 'text']), default='text', 
              help='Output format for migration report')
@click.pass_context
def migrate(ctx, kustomize_dir, output_dir, chart_name, base_dir, overlays_dir, dry_run, force, output_format):
    """Migrate Kustomize configuration to Helm chart.
    
    KUSTOMIZE_DIR: Path to directory containing kustomization.yaml (used when not using base/overlays)
    OUTPUT_DIR: Directory where Helm chart will be created
    
    For multi-overlay setups, use --base-dir and --overlays-dir instead of KUSTOMIZE_DIR.
    This will generate a base Helm chart with separate values files for each overlay.
    """
    verbose = ctx.obj.get('verbose', False)
    
    try:
        # Check if this is a multi-overlay setup
        if base_dir and overlays_dir:
            # Multi-overlay migration
            base_path = Path(base_dir).resolve()
            overlays_path = Path(overlays_dir).resolve()
            output_path = Path(output_dir).resolve()
            
            if not chart_name:
                chart_name = base_path.name
            
            chart_output_path = output_path / chart_name
            
            # Check if chart directory already exists
            if chart_output_path.exists() and not force and not dry_run:
                click.echo(f"Error: Chart directory '{chart_output_path}' already exists. Use --force to overwrite.", err=True)
                sys.exit(1)
            
            # Create output directory if it doesn't exist
            if not dry_run:
                output_path.mkdir(parents=True, exist_ok=True)
            
            # Import the new multi-overlay migrator
            from .multi_overlay_migrator import MultiOverlayMigrator
            
            # Initialize multi-overlay migrator
            migrator = MultiOverlayMigrator(
                base_dir=base_path,
                overlays_dir=overlays_path,
                output_dir=output_path,
                chart_name=chart_name,
                dry_run=dry_run
            )
            
            click.echo(f"Starting multi-overlay migration from base '{base_path}' and overlays '{overlays_path}' to Helm chart '{chart_name}'...")
            
        else:
            # Single kustomize directory migration (original behavior)
            kustomize_path = Path(kustomize_dir).resolve()
            output_path = Path(output_dir).resolve()
            
            if not chart_name:
                chart_name = kustomize_path.name
            
            chart_output_path = output_path / chart_name
            
            # Check if chart directory already exists
            if chart_output_path.exists() and not force and not dry_run:
                click.echo(f"Error: Chart directory '{chart_output_path}' already exists. Use --force to overwrite.", err=True)
                sys.exit(1)
            
            # Create output directory if it doesn't exist
            if not dry_run:
                output_path.mkdir(parents=True, exist_ok=True)
            
            # Initialize single migrator
            migrator = KustomizeToHelmMigrator(
                kustomize_dir=kustomize_path,
                output_dir=output_path,
                chart_name=chart_name,
                dry_run=dry_run
            )
            
            click.echo(f"Starting migration from '{kustomize_path}' to Helm chart '{chart_name}'...")
        
        if dry_run:
            click.echo("Running in dry-run mode (no files will be created)...")
        
        report = migrator.migrate()
        
        # Display results
        _display_migration_report(report, output_format)
        
        if report['status'] == 'success':
            if not dry_run:
                click.echo(f"\n✅ Migration completed successfully!")
                click.echo(f"📦 Helm chart created at: {chart_output_path}")
                click.echo(f"\nNext steps:")
                click.echo(f"  1. Review the generated chart: cd {chart_output_path}")
                click.echo(f"  2. Customize values.yaml as needed")
                click.echo(f"  3. Test the chart: helm install {chart_name} {chart_output_path}")
            else:
                click.echo(f"\n✅ Dry-run completed successfully!")
                click.echo(f"📋 Analysis complete. Ready for migration.")
        else:
            click.echo(f"\n❌ Migration failed!")
            sys.exit(1)
            
    except Exception as e:
        if verbose:
            raise
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('kustomize_dir', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option('--output-format', '-f', type=click.Choice(['json', 'yaml', 'text']), default='text',
              help='Output format for analysis report')
@click.option('--output-file', '-o', type=click.Path(), help='Save analysis to file')
@click.pass_context
def analyze(ctx, kustomize_dir, output_format, output_file):
    """Analyze Kustomize configuration without migration.
    
    KUSTOMIZE_DIR: Path to directory containing kustomization.yaml
    """
    verbose = ctx.obj.get('verbose', False)
    
    try:
        kustomize_path = Path(kustomize_dir).resolve()
        
        # Initialize migrator
        migrator = KustomizeToHelmMigrator(
            kustomize_dir=kustomize_path,
            output_dir=Path('/tmp'),  # Not used in analysis mode
            chart_name=kustomize_path.name,
            dry_run=True
        )
        
        click.echo(f"Analyzing Kustomize configuration at '{kustomize_path}'...")
        
        # Perform analysis
        report = migrator.analyze_only()
        
        # Output results
        if output_file:
            _save_report_to_file(report, output_file, output_format)
            click.echo(f"Analysis saved to: {output_file}")
        else:
            _display_analysis_report(report, output_format)
            
    except Exception as e:
        if verbose:
            raise
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--chart-name', '-n', prompt='Chart name', help='Name for the new Helm chart')
@click.option('--output-dir', '-o', type=click.Path(), default='.', help='Output directory')
@click.option('--description', '-d', help='Chart description')
@click.option('--version', default='0.1.0', help='Chart version')
@click.option('--app-version', default='1.0.0', help='Application version')
def init(chart_name, output_dir, description, version, app_version):
    """Initialize a new Helm chart template for migration.
    
    Creates a basic Helm chart structure that can be used as a target for migration.
    """
    try:
        output_path = Path(output_dir).resolve()
        chart_path = output_path / chart_name
        
        if chart_path.exists():
            click.echo(f"Error: Directory '{chart_path}' already exists.", err=True)
            sys.exit(1)
        
        # Create basic chart structure
        templates_dir = chart_path / 'templates'
        templates_dir.mkdir(parents=True)
        
        # Create Chart.yaml
        chart_yaml = {
            'apiVersion': 'v2',
            'name': chart_name,
            'description': description or f'A Helm chart for {chart_name}',
            'type': 'application',
            'version': version,
            'appVersion': app_version
        }
        
        with open(chart_path / 'Chart.yaml', 'w') as f:
            yaml.dump(chart_yaml, f, default_flow_style=False)
        
        # Create basic values.yaml
        values_yaml = {
            'replicaCount': 1,
            'image': {
                'repository': 'nginx',
                'pullPolicy': 'IfNotPresent',
                'tag': 'latest'
            },
            'service': {
                'type': 'ClusterIP',
                'port': 80
            }
        }
        
        with open(chart_path / 'values.yaml', 'w') as f:
            yaml.dump(values_yaml, f, default_flow_style=False)
        
        # Create .helmignore
        helmignore_content = """# Patterns to ignore when building packages.
# This supports shell glob matching, relative path matching, and
# negation (prefixed with !). Only one pattern per line.
.DS_Store
# Common VCS dirs
.git/
.gitignore
.bzr/
.bzrignore
.hg/
.hgignore
.svn/
# Common backup files
*.swp
*.bak
*.tmp
*.orig
*~
# Various IDEs
.project
.idea/
*.tmproj
.vscode/
"""
        
        with open(chart_path / '.helmignore', 'w') as f:
            f.write(helmignore_content)
        
        click.echo(f"✅ Helm chart '{chart_name}' initialized at: {chart_path}")
        click.echo(f"\nNext steps:")
        click.echo(f"  1. Use 'k2h migrate' to populate this chart from Kustomize configuration")
        click.echo(f"  2. Or manually add templates to the templates/ directory")
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('chart_dir', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option('--strict', is_flag=True, help='Enable strict validation')
def validate(chart_dir, strict):
    """Validate a Helm chart for common issues.
    
    CHART_DIR: Path to Helm chart directory
    """
    try:
        chart_path = Path(chart_dir).resolve()
        
        click.echo(f"Validating Helm chart at '{chart_path}'...")
        
        issues = []
        warnings = []
        
        # Check for required files
        required_files = ['Chart.yaml', 'values.yaml']
        for required_file in required_files:
            if not (chart_path / required_file).exists():
                issues.append(f"Missing required file: {required_file}")
        
        # Check Chart.yaml
        chart_yaml_path = chart_path / 'Chart.yaml'
        if chart_yaml_path.exists():
            try:
                with open(chart_yaml_path, 'r') as f:
                    chart_data = yaml.safe_load(f)
                
                required_fields = ['apiVersion', 'name', 'version']
                for field in required_fields:
                    if field not in chart_data:
                        issues.append(f"Chart.yaml missing required field: {field}")
                
                if chart_data.get('apiVersion') not in ['v1', 'v2']:
                    warnings.append(f"Chart.yaml apiVersion should be 'v1' or 'v2', found: {chart_data.get('apiVersion')}")
                        
            except yaml.YAMLError as e:
                issues.append(f"Invalid YAML in Chart.yaml: {e}")
        
        # Check templates directory
        templates_dir = chart_path / 'templates'
        if not templates_dir.exists():
            warnings.append("No templates directory found")
        elif not any(templates_dir.iterdir()):
            warnings.append("Templates directory is empty")
        else:
            # Validate template files
            for template_file in templates_dir.glob('*.yaml'):
                if template_file.name.startswith('_'):
                    continue  # Skip helper templates
                
                try:
                    with open(template_file, 'r') as f:
                        content = f.read()
                        # Basic template syntax check
                        if '{{' in content and '}}' in content:
                            # Contains Helm templates - basic validation
                            if strict:
                                # More strict validation could be added here
                                pass
                except Exception as e:
                    issues.append(f"Error reading template {template_file.name}: {e}")
        
        # Display results
        if issues:
            click.echo("\n❌ Validation Issues:")
            for issue in issues:
                click.echo(f"  • {issue}")
        
        if warnings:
            click.echo("\n⚠️  Warnings:")
            for warning in warnings:
                click.echo(f"  • {warning}")
        
        if not issues and not warnings:
            click.echo("✅ Chart validation passed!")
        elif not issues:
            click.echo("\n✅ Chart validation passed with warnings.")
        else:
            click.echo(f"\n❌ Chart validation failed with {len(issues)} issue(s).")
            sys.exit(1)
            
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def _display_migration_report(report: dict, output_format: str) -> None:
    """Display migration report in specified format."""
    if output_format == 'json':
        click.echo(json.dumps(report, indent=2))
    elif output_format == 'yaml':
        click.echo(yaml.dump(report, default_flow_style=False))
    else:  # text format
        click.echo(f"\n📊 Migration Report")
        click.echo(f"{'='*50}")
        
        # Handle both single and multi-overlay reports
        if 'source_directory' in report:
            # Single directory migration
            click.echo(f"Source: {report['source_directory']}")
        elif 'source_base_directory' in report:
            # Multi-overlay migration
            click.echo(f"Base: {report['source_base_directory']}")
            click.echo(f"Overlays: {report['source_overlays_directory']}")
        
        click.echo(f"Target: {report['target_directory']}")
        click.echo(f"Chart Name: {report['chart_name']}")
        click.echo(f"Status: {report['status'].upper()}")
        click.echo()
        
        click.echo(f"📦 Resources Processed:")
        click.echo(f"  • Resources migrated: {report['resources_migrated']}")
        
        # Multi-overlay specific stats
        if 'overlays_processed' in report:
            click.echo(f"  • Overlays processed: {report['overlays_processed']}")
            click.echo(f"  • Parameters extracted: {report['parameters_extracted']}")
            click.echo(f"  • Values files generated: {report['values_files_generated']}")
        else:
            # Single directory stats
            click.echo(f"  • Patches converted: {report.get('patches_converted', 0)}")
            click.echo(f"  • ConfigMaps generated: {report.get('config_maps_generated', 0)}")
            click.echo(f"  • Secrets generated: {report.get('secrets_generated', 0)}")
        
        if report.get('warnings'):
            click.echo(f"\n⚠️  Warnings ({len(report['warnings'])}):")
            for warning in report['warnings']:
                click.echo(f"  • {warning}")
        
        if report.get('errors'):
            click.echo(f"\n❌ Errors ({len(report['errors'])}):")
            for error in report['errors']:
                click.echo(f"  • {error}")


def _display_analysis_report(report: dict, output_format: str) -> None:
    """Display analysis report in specified format."""
    if output_format == 'json':
        click.echo(json.dumps(report, indent=2))
    elif output_format == 'yaml':
        click.echo(yaml.dump(report, default_flow_style=False))
    else:  # text format
        click.echo(f"\n🔍 Analysis Report")
        click.echo(f"{'='*50}")
        click.echo(f"Source: {report['source_directory']}")
        click.echo(f"Chart Name: {report['chart_name']}")
        click.echo(f"Migration Complexity: {report['migration_complexity']}")
        click.echo()
        
        click.echo(f"📦 Resources Found:")
        click.echo(f"  • Total resources: {report['resources_found']}")
        click.echo(f"  • Patches: {report['patches_found']}")
        click.echo(f"  • ConfigMaps: {report['config_maps_found']}")
        click.echo(f"  • Secrets: {report['secrets_found']}")
        
        if report.get('resource_types'):
            click.echo(f"\n📋 Resource Types:")
            for resource_type, count in report['resource_types'].items():
                click.echo(f"  • {resource_type}: {count}")
        
        if report.get('kustomization_features'):
            click.echo(f"\n🔧 Kustomization Features:")
            for feature in report['kustomization_features']:
                click.echo(f"  • {feature}")
        
        if report.get('warnings'):
            click.echo(f"\n⚠️  Potential Issues ({len(report['warnings'])}):")
            for warning in report['warnings']:
                click.echo(f"  • {warning}")
        
        if report.get('errors'):
            click.echo(f"\n❌ Errors ({len(report['errors'])}):")
            for error in report['errors']:
                click.echo(f"  • {error}")


def _save_report_to_file(report: dict, output_file: Path, output_format: str) -> None:
    """Save report to file in specified format."""
    output_path = Path(output_file)
    
    with open(output_path, 'w') as f:
        if output_format == 'json':
            json.dump(report, f, indent=2)
        elif output_format == 'yaml':
            yaml.dump(report, f, default_flow_style=False)
        else:  # text format
            # Convert to text and save
            f.write("Analysis Report\n")
            f.write("=" * 50 + "\n")
            for key, value in report.items():
                f.write(f"{key}: {value}\n")


def main():
    """Main entry point for the CLI."""
    cli()


if __name__ == '__main__':
    main()
