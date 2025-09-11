# Kustomize to Helm Migration Framework

A comprehensive Python framework for migrating Kustomize configurations to Helm charts. This tool automates the conversion process while preserving the functionality and structure of your Kubernetes deployments.

## Features

- 🔄 **Complete Migration**: Converts Kustomize configurations to fully functional Helm charts
- 📊 **Analysis Mode**: Analyze Kustomize configurations before migration
- 🎛️ **Template Conversion**: Advanced templating with proper Helm patterns
- 🔧 **Value Extraction**: Automatic extraction of configurable values
- 📦 **Resource Support**: Handles Deployments, Services, Ingress, ConfigMaps, Secrets, and more
- 🔍 **Patch Processing**: Converts Kustomize patches to Helm templates
- 🛡️ **Validation**: Built-in validation for generated Helm charts
- 🖥️ **CLI Interface**: Easy-to-use command-line interface

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd kustomize-to-helm

# Install dependencies
pip install -r requirements.txt

# Install the package
pip install -e .
```

## Quick Start

### Basic Migration

```bash
# Migrate a Kustomize configuration to a Helm chart
k2h migrate /path/to/kustomize/dir /path/to/output/dir

# Migrate with custom chart name
k2h migrate /path/to/kustomize/dir /path/to/output/dir --chart-name my-app

# Dry run (analyze without creating files)
k2h migrate /path/to/kustomize/dir /path/to/output/dir --dry-run
```

### Analysis

```bash
# Analyze Kustomize configuration
k2h analyze /path/to/kustomize/dir

# Save analysis to file
k2h analyze /path/to/kustomize/dir --output-file analysis.json --output-format json
```

### Chart Validation

```bash
# Validate generated Helm chart
k2h validate /path/to/helm/chart

# Strict validation
k2h validate /path/to/helm/chart --strict
```

## Usage Examples

### Example 1: Simple Application Migration

Given a Kustomize directory structure:
```
my-app/
├── kustomization.yaml
├── deployment.yaml
├── service.yaml
└── configmap.yaml
```

Migration command:
```bash
k2h migrate my-app ./charts --chart-name my-app
```

Generated Helm chart:
```
charts/my-app/
├── Chart.yaml
├── values.yaml
├── templates/
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── configmap.yaml
│   ├── _helpers.tpl
│   └── NOTES.txt
└── charts/
```

### Example 2: Complex Migration with Patches

Kustomize configuration with patches:
```yaml
# kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - base/deployment.yaml
  - base/service.yaml

patchesStrategicMerge:
  - patches/deployment-patch.yaml

images:
  - name: nginx
    newTag: 1.20
    
namespace: production
namePrefix: prod-
commonLabels:
  environment: production
```

Migration with analysis:
```bash
# First analyze the configuration
k2h analyze ./my-app-kustomize

# Then migrate
k2h migrate ./my-app-kustomize ./charts --chart-name my-production-app
```

### Example 3: Using the Python API

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
print(f"Migration status: {report['status']}")
print(f"Resources migrated: {report['resources_migrated']}")

# Or just analyze
analysis = migrator.analyze_only()
print(f"Migration complexity: {analysis['migration_complexity']}")
```

## Supported Kustomize Features

### ✅ Fully Supported
- Resources (YAML files and directories)
- Strategic merge patches
- Namespace transformation
- Name prefix/suffix
- Common labels and annotations
- Image transformations (name, tag, digest)
- Replica transformations
- ConfigMap generators
- Secret generators

### ⚠️ Partially Supported
- JSON6902 patches (converted to comments/manual review needed)
- Complex transformers (require manual handling)

### ❌ Not Supported
- Custom plugins
- Remote resources (URLs)
- Helm charts as resources

## Generated Helm Chart Structure

The migration tool generates a complete Helm chart with the following structure:

```
chart-name/
├── Chart.yaml              # Chart metadata
├── values.yaml             # Default configuration values
├── templates/
│   ├── deployment.yaml     # Deployment template
│   ├── service.yaml        # Service template
│   ├── ingress.yaml        # Ingress template (if present)
│   ├── configmap.yaml      # ConfigMap template
│   ├── secret.yaml         # Secret template
│   ├── serviceaccount.yaml # ServiceAccount template
│   ├── _helpers.tpl        # Template helpers
│   ├── NOTES.txt          # Installation notes
│   └── tests/
│       └── test-connection.yaml
└── charts/                 # Dependencies (empty)
```

### Values.yaml Structure

The generated `values.yaml` includes:

```yaml
# Replica configuration
replicaCount: 1

# Image configuration
image:
  repository: nginx
  pullPolicy: IfNotPresent
  tag: "1.20"

# Service configuration
service:
  type: ClusterIP
  port: 80

# Ingress configuration
ingress:
  enabled: false
  className: ""
  annotations: {}
  hosts: []
  tls: []

# Resource limits
resources: {}

# Node selection
nodeSelector: {}
tolerations: []
affinity: {}

# Common labels and annotations
commonLabels: {}
commonAnnotations: {}
```

## Configuration Options

### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--chart-name` | Name for the Helm chart | Directory name |
| `--dry-run` | Analyze without creating files | False |
| `--force` | Overwrite existing chart directory | False |
| `--output-format` | Output format (json/yaml/text) | text |
| `--verbose` | Enable verbose logging | False |

### Migration Options

The migration process can be customized by modifying the migrator configuration:

```python
migrator = KustomizeToHelmMigrator(
    kustomize_dir="/path/to/kustomize",
    output_dir="/path/to/output",
    chart_name="my-app",
    dry_run=False  # Set to True for analysis only
)

# Customize chart metadata
migrator.generator.chart_metadata.update({
    'description': 'My custom application',
    'version': '1.0.0',
    'appVersion': '2.0.0'
})

# Customize values
migrator.generator.values.update({
    'replicaCount': 3,
    'image': {
        'repository': 'my-registry/my-app',
        'tag': 'v2.0.0'
    }
})

# Perform migration
report = migrator.migrate()
```

## Advanced Features

### Custom Template Conversion

Extend the template converter for custom resource types:

```python
from kustomize_to_helm.template_converter import TemplateConverter

class CustomTemplateConverter(TemplateConverter):
    def _apply_custom_templating(self, resource):
        # Add custom templating logic
        if resource.get('kind') == 'CustomResource':
            # Handle custom resource templating
            pass

# Use custom converter
migrator = KustomizeToHelmMigrator(...)
migrator.converter = CustomTemplateConverter(migrator.chart_name)
```

### Value Extraction Customization

Customize value extraction for specific patterns:

```python
# Override value extraction
def custom_extract_values(self, resources):
    extracted = super().extract_parameterizable_values(resources)
    
    # Add custom value extraction logic
    for resource in resources:
        if resource.get('kind') == 'MyCustomResource':
            extracted['myCustomConfig'] = resource.get('spec', {}).get('config', {})
    
    return extracted

# Apply to migrator
migrator.converter.extract_parameterizable_values = custom_extract_values
```

## Troubleshooting

### Common Issues

1. **Missing kustomization.yaml**
   ```
   Error: No kustomization file found in /path/to/dir
   ```
   Solution: Ensure the directory contains a valid `kustomization.yaml`, `kustomization.yml`, or `Kustomization` file.

2. **Resource files not found**
   ```
   Warning: Resource file not found: deployment.yaml
   ```
   Solution: Check that all resources listed in `kustomization.yaml` exist and paths are correct.

3. **Complex patches**
   ```
   Warning: JSON6902 patches require manual conversion to Helm templates
   ```
   Solution: Review generated chart and manually convert complex patches to Helm template logic.

### Debug Mode

Enable verbose logging for detailed information:

```bash
k2h --verbose migrate /path/to/kustomize /path/to/output
```

### Validation Errors

If the generated chart has validation errors:

```bash
# Validate the chart
k2h validate /path/to/generated/chart

# Check Helm lint
helm lint /path/to/generated/chart

# Test installation (dry-run)
helm install --dry-run --debug my-release /path/to/generated/chart
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues and questions:
- Create an issue on GitHub
- Check existing documentation
- Review the examples directory

## Changelog

### v1.0.0
- Initial release
- Complete Kustomize to Helm migration
- CLI interface
- Analysis and validation tools
- Support for major Kubernetes resource types
