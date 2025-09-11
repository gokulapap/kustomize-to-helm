# Multi-Overlay Kustomize to Helm Migration Features

## Overview

This document describes the enhanced multi-overlay support added to the Kustomize to Helm migration framework. These features address the common Kustomize pattern of having a base configuration with multiple overlays for different environments.

## Key Features Implemented

### 1. Multi-Overlay CLI Support

New CLI options for handling base + overlays structure:

```bash
# Multi-overlay migration
k2h migrate ./dummy ./output \
  --base-dir ./app/base \
  --overlays-dir ./app/overlays \
  --chart-name my-app

# Example with real paths
k2h migrate ./base ./charts \
  --base-dir ./kustomize-app/base \
  --overlays-dir ./kustomize-app/overlays \
  --chart-name production-app
```

### 2. Automatic Overlay Discovery

The framework automatically discovers all overlay directories within the specified overlays directory:

```
overlays/
├── development/
├── staging/
├── production/
└── testing/
```

All subdirectories are automatically processed as overlays.

### 3. Parameterized Values Files

Generates separate values files for each overlay:

- `values.yaml` - Base values from the base configuration
- `values-development.yaml` - Development-specific values
- `values-staging.yaml` - Staging-specific values  
- `values-production.yaml` - Production-specific values

### 4. Intelligent Difference Analysis

The `OverlayAnalyzer` component:

- Compares base resources with overlay resources
- Identifies differences between overlays
- Extracts parameterizable values that vary across environments
- Handles Kustomize transformations (namePrefix, nameSuffix, namespace, etc.)

### 5. Enhanced YAML Formatting

Improved multi-line string handling:

- ConfigMap data uses proper YAML literal block scalars (`|-`)
- Multi-line configuration files are properly formatted
- No escaped newlines in the output

**Before:**
```yaml
configMap:
  data:
    app.conf: "# Config\nserver {\n    listen 80;\n}"
```

**After:**
```yaml
configMap:
  data:
    app.conf: |-
      # Config
      server {
          listen 80;
      }
```

### 6. Overlay-Specific Parameterization

Each overlay values file contains:

- Environment-specific labels and annotations
- Different resource configurations (CPU, memory, replicas)
- Overlay-specific service types and ports
- Environment-specific ConfigMap and Secret data
- Proper namespace, namePrefix, and nameSuffix values

## Usage Examples

### Example 1: Basic Multi-Overlay Migration

```bash
# Directory structure
my-app/
├── base/
│   ├── kustomization.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   └── configmap.yaml
└── overlays/
    ├── dev/
    │   ├── kustomization.yaml
    │   └── patches/
    ├── staging/
    │   ├── kustomization.yaml
    │   └── patches/
    └── prod/
        ├── kustomization.yaml
        └── patches/

# Migration command
k2h migrate ./my-app/base ./helm-charts \
  --base-dir ./my-app/base \
  --overlays-dir ./my-app/overlays \
  --chart-name my-app
```

### Example 2: Generated Chart Usage

```bash
# Base deployment
helm install my-app ./helm-charts/my-app

# Development deployment  
helm install my-app-dev ./helm-charts/my-app \
  -f ./helm-charts/my-app/values-dev.yaml

# Staging deployment
helm install my-app-staging ./helm-charts/my-app \
  -f ./helm-charts/my-app/values-staging.yaml

# Production deployment
helm install my-app-prod ./helm-charts/my-app \
  -f ./helm-charts/my-app/values-prod.yaml
```

### Example 3: Python API Usage

```python
from kustomize_to_helm import MultiOverlayMigrator

# Initialize migrator
migrator = MultiOverlayMigrator(
    base_dir="./kustomize-app/base",
    overlays_dir="./kustomize-app/overlays", 
    output_dir="./helm-charts",
    chart_name="my-app"
)

# Perform migration
report = migrator.migrate()

print(f"Overlays processed: {report['overlays_processed']}")
print(f"Parameters extracted: {report['parameters_extracted']}")  
print(f"Values files generated: {report['values_files_generated']}")
```

## Generated Chart Structure

```
my-app/
├── Chart.yaml                 # Base chart metadata
├── values.yaml                # Base values
├── values-development.yaml    # Development overlay values
├── values-staging.yaml        # Staging overlay values  
├── values-production.yaml     # Production overlay values
├── templates/
│   ├── deployment.yaml        # Templated deployment
│   ├── service.yaml          # Templated service
│   ├── configmap.yaml        # Templated configmap
│   ├── _helpers.tpl          # Helper templates
│   └── NOTES.txt             # Usage instructions
└── charts/                   # Dependencies (empty)
```

## Values File Structure

Each overlay values file contains environment-specific configurations:

```yaml
# values-production.yaml
commonLabels:
  app: my-app
  environment: production
  tier: backend

commonAnnotations:
  deployment.environment: production

namespace: production
namePrefix: prod-
replicaCount: 5

image:
  repository: my-registry/my-app
  tag: "1.21"

service:
  type: LoadBalancer
  port: 443

resources:
  requests:
    memory: "256Mi"
    cpu: "1000m"
  limits:
    memory: "512Mi" 
    cpu: "2000m"

configMap:
  data:
    app.conf: |-
      # Production Configuration
      server {
          listen 80;
          server_name app.example.com;
      }
```

## Key Components

### 1. MultiOverlayMigrator
- Main orchestrator for multi-overlay migrations
- Coordinates parsing, analysis, and generation
- Handles overlay discovery and processing

### 2. OverlayAnalyzer  
- Compares base and overlay resources
- Identifies parameterizable differences
- Extracts environment-specific values

### 3. Enhanced HelmChartGenerator
- Generates base chart from base configuration
- Creates overlay-specific values files
- Handles proper YAML formatting for multi-line strings

### 4. Updated CLI
- New `--base-dir` and `--overlays-dir` options
- Backward compatible with single-directory migrations
- Enhanced reporting for multi-overlay scenarios

## Migration Report

The migration provides detailed reporting:

```
📊 Migration Report
==================================================
Base: /path/to/base
Overlays: /path/to/overlays  
Target: /path/to/output/chart
Chart Name: my-app
Status: SUCCESS

📦 Resources Processed:
  • Resources migrated: 3
  • Overlays processed: 3
  • Parameters extracted: 22
  • Values files generated: 4
```

## Benefits

1. **Environment Consistency**: Single chart with environment-specific values
2. **Reduced Duplication**: Common templates with parameterized differences
3. **Easy Deployment**: Simple Helm commands for any environment
4. **Maintainability**: Clear separation of base and environment-specific configs
5. **GitOps Ready**: Values files can be managed in separate repositories

## Supported Kustomize Features

- ✅ Base + overlay structure
- ✅ Strategic merge patches
- ✅ Namespace transformations
- ✅ Name prefix/suffix transformations
- ✅ Common labels and annotations
- ✅ Image transformations
- ✅ Replica transformations
- ✅ ConfigMap and Secret generators
- ⚠️ JSON6902 patches (manual conversion needed)

## Best Practices

1. **Review Generated Values**: Always review and customize generated values files
2. **Test Deployments**: Test each overlay values file before production use
3. **Environment Separation**: Keep environment-specific secrets separate
4. **Chart Versioning**: Use semantic versioning for your Helm charts
5. **Documentation**: Document environment-specific configurations

This multi-overlay support makes the migration framework significantly more powerful for real-world Kustomize to Helm migrations, handling the most common pattern of base + overlays configurations.
