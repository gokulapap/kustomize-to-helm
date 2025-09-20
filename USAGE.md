# Kustomize to Helm Migration Framework - Usage Guide

This guide provides comprehensive instructions for using the Kustomize to Helm migration framework.

## Quick Start

### Installation

```bash
cd kustomize-to-helm
pip install -r requirements.txt
pip install -e .
```

### Basic Usage

```bash
# Migrate a Kustomize configuration to Helm
k2h migrate /path/to/kustomize/dir /path/to/output/dir

# Analyze before migrating
k2h analyze /path/to/kustomize/dir

# Test the framework
python test_migration.py
```

## Command Reference

### `k2h migrate`

Migrate Kustomize configuration to Helm chart.

```bash
k2h migrate [OPTIONS] KUSTOMIZE_DIR OUTPUT_DIR
```

**Arguments:**
- `KUSTOMIZE_DIR`: Path to directory containing kustomization.yaml
- `OUTPUT_DIR`: Directory where Helm chart will be created

**Options:**
- `--chart-name, -n TEXT`: Name for the Helm chart (defaults to directory name)
- `--base-dir, -b DIRECTORY`: Base directory path (for multi-overlay setups)
- `--overlays-dir, -o DIRECTORY`: Overlays directory path (for multi-overlay setups)
- `--dry-run`: Analyze without creating files
- `--force`: Overwrite existing chart directory
- `--output-format, -f [json|yaml|text]`: Output format for migration report (default: text)

**Examples:**
```bash
# Basic migration
k2h migrate ./my-kustomize-app ./helm-charts

# Custom chart name
k2h migrate ./my-app ./charts --chart-name production-app

# Multi-overlay migration
k2h migrate ./base ./helm-charts --base-dir ./base --overlays-dir ./overlays --chart-name my-app

# Dry run
k2h migrate ./my-app ./charts --dry-run

# Force overwrite
k2h migrate ./my-app ./charts --force

# JSON output
k2h migrate ./my-app ./charts --output-format json
```

### Multi-Overlay Migration

For Kustomize configurations with base + overlays structure:

```bash
k2h migrate [OPTIONS] KUSTOMIZE_DIR OUTPUT_DIR --base-dir BASE_DIR --overlays-dir OVERLAYS_DIR
```

**Multi-Overlay Arguments:**
- `KUSTOMIZE_DIR`: Path to base directory (used as fallback)
- `OUTPUT_DIR`: Directory where Helm chart will be created
- `--base-dir, -b`: Base directory path containing base kustomization.yaml
- `--overlays-dir, -o`: Overlays directory containing environment-specific overlays

**Multi-Overlay Examples:**
```bash
# Migrate base + overlays
k2h migrate ./base ./charts --base-dir ./base --overlays-dir ./overlays --chart-name webapp

# With verbose output
k2h migrate ./base ./charts --base-dir ./base --overlays-dir ./overlays --chart-name webapp --verbose

# Dry run for multi-overlay
k2h migrate ./base ./charts --base-dir ./base --overlays-dir ./overlays --chart-name webapp --dry-run
```

**Generated Output:**
```
charts/webapp/
├── Chart.yaml
├── values.yaml              # Base values
├── values-dev.yaml          # Development overlay values
├── values-prod.yaml         # Production overlay values
└── templates/
    ├── deployment.yaml
    ├── service.yaml
    └── configmap.yaml
```

### `k2h analyze`

Analyze Kustomize configuration without migration.

```bash
k2h analyze [OPTIONS] KUSTOMIZE_DIR
```

**Arguments:**
- `KUSTOMIZE_DIR`: Path to directory containing kustomization.yaml

**Options:**
- `--output-format, -f [json|yaml|text]`: Output format (default: text)
- `--output-file, -o PATH`: Save analysis to file

**Examples:**
```bash
# Basic analysis
k2h analyze ./my-kustomize-app

# Save to file
k2h analyze ./my-app --output-file analysis.json --output-format json

# YAML output
k2h analyze ./my-app --output-format yaml
```

### `k2h validate`

Validate a Helm chart for common issues.

```bash
k2h validate [OPTIONS] CHART_DIR
```

**Arguments:**
- `CHART_DIR`: Path to Helm chart directory

**Options:**
- `--strict`: Enable strict validation

**Examples:**
```bash
# Basic validation
k2h validate ./my-helm-chart

# Strict validation
k2h validate ./my-helm-chart --strict
```

### `k2h init`

Initialize a new Helm chart template.

```bash
k2h init [OPTIONS]
```

**Options:**
- `--chart-name, -n TEXT`: Name for the new Helm chart (required)
- `--output-dir, -o PATH`: Output directory (default: current directory)
- `--description, -d TEXT`: Chart description
- `--version TEXT`: Chart version (default: 0.1.0)
- `--app-version TEXT`: Application version (default: 1.0.0)

**Examples:**
```bash
# Initialize new chart
k2h init --chart-name my-new-app

# With custom settings
k2h init --chart-name my-app --description "My application" --version 1.0.0
```

## Python API

### Basic Usage

```python
from kustomize_to_helm import KustomizeToHelmMigrator

# Initialize migrator
migrator = KustomizeToHelmMigrator(
    kustomize_dir="/path/to/kustomize",
    output_dir="/path/to/output",
    chart_name="my-app"
)

# Perform migration
report = migrator.migrate()
print(f"Status: {report['status']}")

# Or just analyze
analysis = migrator.analyze_only()
print(f"Complexity: {analysis['migration_complexity']}")
```

### Advanced Configuration

```python
from kustomize_to_helm import KustomizeToHelmMigrator

migrator = KustomizeToHelmMigrator(
    kustomize_dir="./kustomize-app",
    output_dir="./helm-charts",
    chart_name="production-app",
    dry_run=False
)

# Customize chart metadata
migrator.generator.chart_metadata.update({
    'description': 'Production application',
    'version': '2.0.0',
    'appVersion': '1.5.0',
    'maintainers': [
        {'name': 'DevOps Team', 'email': 'devops@company.com'}
    ]
})

# Customize values
migrator.generator.values.update({
    'replicaCount': 3,
    'image': {
        'repository': 'my-registry/my-app',
        'tag': '1.5.0'
    },
    'service': {
        'type': 'LoadBalancer',
        'port': 8080
    }
})

# Perform migration
report = migrator.migrate()
```

## Migration Patterns

### Pattern 1: Simple Application

**Kustomize Structure:**
```
my-app/
├── kustomization.yaml
├── deployment.yaml
├── service.yaml
└── configmap.yaml
```

**Migration:**
```bash
k2h migrate my-app ./charts --chart-name my-app
```

**Result:** Standard Helm chart with deployment, service, and configmap templates.

### Pattern 2: Multi-Environment

**Kustomize Structure:**
```
my-app/
├── base/
│   ├── kustomization.yaml
│   ├── deployment.yaml
│   └── service.yaml
├── overlays/
│   ├── staging/
│   │   └── kustomization.yaml
│   └── production/
│       └── kustomization.yaml
```

**Migration:**
```bash
# Migrate base
k2h migrate my-app/base ./charts --chart-name my-app-base

# Analyze overlays
k2h analyze my-app/overlays/staging
k2h analyze my-app/overlays/production

# Create environment-specific values files manually based on analysis
```

### Pattern 3: Complex Application with Patches

**Kustomize Structure:**
```
complex-app/
├── kustomization.yaml
├── base/
│   ├── deployment.yaml
│   └── service.yaml
├── patches/
│   ├── deployment-patch.yaml
│   └── service-patch.yaml
└── configs/
    └── app.properties
```

**Migration:**
```bash
# First analyze
k2h analyze complex-app

# Then migrate
k2h migrate complex-app ./charts --chart-name complex-app

# Review generated chart and manually integrate patch logic
```

## Best Practices

### Before Migration

1. **Analyze First**: Always run `k2h analyze` before migration
2. **Review Structure**: Understand your Kustomize structure
3. **Check Dependencies**: Ensure all referenced files exist
4. **Backup**: Keep your original Kustomize configuration

### During Migration

1. **Use Dry Run**: Test with `--dry-run` first
2. **Custom Names**: Use meaningful chart names
3. **Review Warnings**: Pay attention to migration warnings
4. **Validate Output**: Use `k2h validate` on generated charts

### After Migration

1. **Review Templates**: Check generated Helm templates
2. **Test Installation**: Use `helm install --dry-run` to test
3. **Customize Values**: Adjust `values.yaml` as needed
4. **Add Documentation**: Update chart documentation

## Troubleshooting

### Common Issues

**Issue: "No kustomization file found"**
```
Solution: Ensure kustomization.yaml exists in the specified directory
```

**Issue: "Resource file not found"**
```
Solution: Check that all resources listed in kustomization.yaml exist
```

**Issue: "Complex patches require manual conversion"**
```
Solution: Review generated chart and manually convert patch logic to Helm templates
```

**Issue: "Validation failed"**
```
Solution: Use k2h validate to identify specific issues, then fix manually
```

### Debug Mode

Enable verbose logging:
```bash
k2h --verbose migrate my-app ./charts
```

### Getting Help

```bash
# General help
k2h --help

# Command-specific help
k2h migrate --help
k2h analyze --help
k2h validate --help
```

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: Migrate Kustomize to Helm
on:
  push:
    paths:
      - 'kustomize/**'

jobs:
  migrate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Setup Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.9
          
      - name: Install migration tool
        run: |
          pip install -r requirements.txt
          pip install -e .
          
      - name: Migrate to Helm
        run: |
          k2h migrate ./kustomize ./helm-charts --chart-name my-app
          
      - name: Validate Helm chart
        run: |
          k2h validate ./helm-charts/my-app
```

### Jenkins Pipeline Example

```groovy
pipeline {
    agent any
    
    stages {
        stage('Migrate Kustomize') {
            steps {
                sh '''
                    pip install -r requirements.txt
                    pip install -e .
                    k2h migrate ./kustomize ./helm-charts --chart-name my-app
                    k2h validate ./helm-charts/my-app
                '''
            }
        }
    }
}
```

## Advanced Topics

### Custom Template Conversion

Extend the framework for custom resource types:

```python
from kustomize_to_helm.template_converter import TemplateConverter

class MyTemplateConverter(TemplateConverter):
    def convert_resource(self, resource, extracted_values):
        # Custom conversion logic
        if resource.get('kind') == 'MyCustomResource':
            # Handle custom resource
            pass
        
        return super().convert_resource(resource, extracted_values)

# Use custom converter
migrator.converter = MyTemplateConverter(migrator.chart_name)
```

### Custom Value Extraction

```python
def extract_custom_values(resources):
    custom_values = {}
    for resource in resources:
        if resource.get('kind') == 'MyResource':
            custom_values['myConfig'] = resource.get('spec', {})
    return custom_values

# Apply custom extraction
migrator.converter.extract_parameterizable_values = extract_custom_values
```

## Examples

Check the `examples/` directory for:
- Sample Kustomize configurations
- Generated Helm charts
- Python API usage examples
- CLI usage examples

Run the examples:
```bash
cd examples
python usage_examples.py
```

## Support and Resources

- **GitHub Issues**: Report bugs and feature requests
- **Documentation**: Complete API documentation
- **Examples**: Real-world migration examples
- **Community**: Join discussions and share experiences
