# Kustomize to Helm Migration Framework

A comprehensive Python framework for migrating Kustomize configurations to Helm charts. This tool automates the conversion process while preserving the functionality and structure of your Kubernetes deployments.

## Features

- 🔄 **Complete Migration**: Converts Kustomize configurations to fully functional Helm charts
- 🌐 **Multi-Overlay Support**: Migrate base + overlays configurations with environment-specific values
- 📊 **Analysis Mode**: Analyze Kustomize configurations before migration
- 🎛️ **Template Conversion**: Advanced templating with proper Helm patterns
- 🔧 **Value Extraction**: Automatic extraction of configurable values
- 📦 **Resource Support**: Handles Deployments, Services, Ingress, ConfigMaps, Secrets, and more
- 🔍 **Patch Processing**: Converts Kustomize patches to Helm templates
- 🛡️ **Validation**: Built-in validation for generated Helm charts
- 🖥️ **CLI Interface**: Easy-to-use command-line interface
- ✨ **Production Ready**: Generates clean, valid YAML with proper Helm templating

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

### Multi-Overlay Migration

```bash
# Migrate base + overlays configuration
k2h migrate /path/to/base /path/to/output --base-dir /path/to/base --overlays-dir /path/to/overlays --chart-name my-app

# Example: Migrate with dev and prod overlays
k2h migrate ./base ./helm-charts --base-dir ./base --overlays-dir ./overlays --chart-name webapp
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

### Example 3: Multi-Overlay Migration

Given a Kustomize directory structure:
```
my-app/
├── base/
│   ├── kustomization.yaml
│   ├── deployment.yaml
│   └── service.yaml
└── overlays/
    ├── dev/
    │   ├── kustomization.yaml
    │   └── deployment-patch.yaml
    └── prod/
        ├── kustomization.yaml
        ├── deployment-patch.yaml
        └── ingress.yaml
```

Multi-overlay migration:
```bash
# Migrate with all overlays
k2h migrate ./base ./charts --base-dir ./base --overlays-dir ./overlays --chart-name my-app
```

Generated Helm chart:
```
charts/my-app/
├── Chart.yaml
├── values.yaml              # Base values
├── values-dev.yaml          # Development values
├── values-prod.yaml         # Production values
└── templates/
    ├── deployment.yaml
    ├── service.yaml
    └── ingress.yaml
```

Deploy with environment-specific values:
```bash
# Deploy to development
helm install my-app-dev ./charts/my-app -f ./charts/my-app/values-dev.yaml

# Deploy to production
helm install my-app-prod ./charts/my-app -f ./charts/my-app/values-prod.yaml
```

### Example 4: Using the Python API

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
| `--base-dir` | Base directory path (for multi-overlay setups) | None |
| `--overlays-dir` | Overlays directory path (for multi-overlay setups) | None |
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

3. **Multi-overlay migration issues**
   ```
   Error: No such option: --base-dir
   ```
   Solution: Ensure you're using the latest version. Multi-overlay support requires version 1.0.0+.

4. **Invalid YAML in generated files**
   ```
   Error: parse error at (webapp/templates/service.yaml:6): unexpected {{end}}
   ```
   Solution: This has been fixed in version 1.0.0+. Update to the latest version.

5. **Complex patches**
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
- **Multi-overlay support** with `--base-dir` and `--overlays-dir` options
- **Environment-specific values files** generation
- **Fixed YAML generation** - removed invalid `...` syntax
- **Fixed template generation** - removed invalid `{{- end }}: null` syntax
- **Production-ready output** with clean, valid Helm templates
- **Comprehensive testing** with real-world multi-overlay scenarios
