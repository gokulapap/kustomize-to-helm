"""
Main Migrator Module

Orchestrates the migration process from Kustomize to Helm.
"""

import os
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Union

from .kustomize_parser import KustomizeParser
from .helm_generator import HelmChartGenerator
from .template_converter import TemplateConverter

logger = logging.getLogger(__name__)


class KustomizeToHelmMigrator:
    """Main class for migrating Kustomize configurations to Helm charts."""
    
    def __init__(self, 
                 kustomize_dir: Union[str, Path],
                 output_dir: Union[str, Path],
                 chart_name: Optional[str] = None,
                 dry_run: bool = False):
        """
        Initialize the migrator.
        
        Args:
            kustomize_dir: Path to directory containing kustomization.yaml
            output_dir: Directory where Helm chart will be created
            chart_name: Name for the Helm chart (defaults to kustomize directory name)
            dry_run: If True, only analyze without creating files
        """
        self.kustomize_dir = Path(kustomize_dir)
        self.output_dir = Path(output_dir)
        self.chart_name = chart_name or self.kustomize_dir.name
        self.dry_run = dry_run
        
        # Initialize components
        self.parser = KustomizeParser(self.kustomize_dir)
        self.generator = HelmChartGenerator(self.chart_name, self.output_dir)
        self.converter = TemplateConverter(self.chart_name)
        
        # Migration results
        self.kustomize_data = {}
        self.migration_report = {
            'source_directory': str(self.kustomize_dir),
            'target_directory': str(self.output_dir / self.chart_name),
            'chart_name': self.chart_name,
            'resources_migrated': 0,
            'patches_converted': 0,
            'config_maps_generated': 0,
            'secrets_generated': 0,
            'warnings': [],
            'errors': []
        }
    
    def migrate(self) -> Dict[str, Any]:
        """
        Perform the complete migration from Kustomize to Helm.
        
        Returns:
            Migration report with details about the conversion
        """
        logger.info(f"Starting migration from {self.kustomize_dir} to Helm chart '{self.chart_name}'")
        
        try:
            # Step 1: Parse Kustomize configuration
            self._parse_kustomize()
            
            # Step 2: Analyze and validate
            self._analyze_configuration()
            
            # Step 3: Extract values
            self._extract_values()
            
            # Step 4: Convert templates
            self._convert_templates()
            
            # Step 5: Generate Helm chart (if not dry run)
            if not self.dry_run:
                self._generate_helm_chart()
                logger.info(f"Migration completed successfully. Chart created at: {self.output_dir / self.chart_name}")
            else:
                logger.info("Dry run completed. No files were created.")
            
            self.migration_report['status'] = 'success'
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            self.migration_report['status'] = 'failed'
            self.migration_report['errors'].append(str(e))
            raise
        
        return self.migration_report
    
    def _parse_kustomize(self) -> None:
        """Parse the Kustomize configuration."""
        logger.info("Parsing Kustomize configuration...")
        
        try:
            self.kustomize_data = self.parser.parse()
            
            # Update migration report
            self.migration_report['resources_migrated'] = len(self.kustomize_data.get('resources', []))
            self.migration_report['patches_converted'] = len(self.kustomize_data.get('patches', []))
            self.migration_report['config_maps_generated'] = len(self.kustomize_data.get('configMaps', []))
            self.migration_report['secrets_generated'] = len(self.kustomize_data.get('secrets', []))
            
            logger.info(f"Parsed {self.migration_report['resources_migrated']} resources")
            
        except Exception as e:
            error_msg = f"Failed to parse Kustomize configuration: {e}"
            logger.error(error_msg)
            self.migration_report['errors'].append(error_msg)
            raise
    
    def _analyze_configuration(self) -> None:
        """Analyze the configuration for potential issues."""
        logger.info("Analyzing configuration...")
        
        # Check for unsupported features
        self._check_unsupported_features()
        
        # Validate resource references
        self._validate_resource_references()
        
        # Check for complex patches
        self._analyze_patches()
        
        # Check for naming conflicts
        self._check_naming_conflicts()
    
    def _check_unsupported_features(self) -> None:
        """Check for Kustomize features that may not translate well to Helm."""
        kustomization = self.kustomize_data.get('kustomization', {})
        
        # Check for potentially problematic features
        problematic_features = [
            'bases',  # Deprecated in favor of resources
            'crds',   # Custom Resource Definitions
            'openapi', # OpenAPI schema
            'inventory', # Inventory object
        ]
        
        for feature in problematic_features:
            if feature in kustomization:
                warning = f"Feature '{feature}' may require manual handling in Helm"
                self.migration_report['warnings'].append(warning)
                logger.warning(warning)
        
        # Check for complex transformers
        transformers = [
            'transformers',
            'generators',
            'validators'
        ]
        
        for transformer in transformers:
            if transformer in kustomization:
                warning = f"Transformer '{transformer}' will need manual conversion"
                self.migration_report['warnings'].append(warning)
                logger.warning(warning)
    
    def _validate_resource_references(self) -> None:
        """Validate that all referenced resources exist."""
        resources = self.kustomize_data.get('resources', [])
        
        for resource in resources:
            source_file = resource.get('_source_file')
            if source_file:
                full_path = self.kustomize_dir / source_file
                if not full_path.exists():
                    warning = f"Resource file not found: {source_file}"
                    self.migration_report['warnings'].append(warning)
                    logger.warning(warning)
    
    def _analyze_patches(self) -> None:
        """Analyze patches for complexity."""
        patches = self.kustomize_data.get('patches', [])
        
        for patch in patches:
            patch_type = patch.get('type', 'unknown')
            
            if patch_type == 'json6902':
                warning = "JSON6902 patches require manual conversion to Helm templates"
                self.migration_report['warnings'].append(warning)
                logger.warning(warning)
            elif patch_type == 'strategic-merge':
                # Strategic merge patches might be convertible
                if not patch.get('inline', False):
                    info = f"Strategic merge patch from file: {patch.get('path', 'unknown')}"
                    logger.info(info)
    
    def _check_naming_conflicts(self) -> None:
        """Check for potential naming conflicts in the generated chart."""
        resources = self.kustomize_data.get('resources', [])
        resource_names = {}
        
        for resource in resources:
            kind = resource.get('kind', 'Unknown')
            name = resource.get('metadata', {}).get('name', 'unnamed')
            
            if kind not in resource_names:
                resource_names[kind] = []
            
            if name in resource_names[kind]:
                warning = f"Duplicate {kind} resource name: {name}"
                self.migration_report['warnings'].append(warning)
                logger.warning(warning)
            else:
                resource_names[kind].append(name)
    
    def _extract_values(self) -> None:
        """Extract values for the Helm chart."""
        logger.info("Extracting values...")
        
        # Get all resources including generated ones
        all_resources = self.parser.get_all_resources()
        
        # Extract parameterizable values
        extracted_values = self.converter.extract_parameterizable_values(all_resources)
        
        # Merge with kustomization-level values
        kustomization = self.kustomize_data.get('kustomization', {})
        
        # Add global values from kustomization
        global_values = {
            'namePrefix': kustomization.get('namePrefix', ''),
            'nameSuffix': kustomization.get('nameSuffix', ''),
            'namespace': kustomization.get('namespace', ''),
            'commonLabels': kustomization.get('commonLabels', {}),
            'commonAnnotations': kustomization.get('commonAnnotations', {})
        }
        
        # Update generator values
        self.generator.values.update(global_values)
        self.generator.values.update(extracted_values)
        
        # Handle image transformations
        self._apply_image_transformations()
        
        # Handle replica transformations
        self._apply_replica_transformations()
        
        logger.info("Values extraction completed")
    
    def _apply_image_transformations(self) -> None:
        """Apply image transformations from Kustomize to Helm values."""
        kustomization = self.kustomize_data.get('kustomization', {})
        images = kustomization.get('images', [])
        
        for image_transform in images:
            if 'name' in image_transform:
                # Update image repository
                if 'newName' in image_transform:
                    self.generator.values['image']['repository'] = image_transform['newName']
                
                # Update image tag
                if 'newTag' in image_transform:
                    self.generator.values['image']['tag'] = image_transform['newTag']
                
                # Handle digest
                if 'digest' in image_transform:
                    self.generator.values['image']['digest'] = image_transform['digest']
                    # Remove tag when digest is present
                    if 'tag' in self.generator.values['image']:
                        del self.generator.values['image']['tag']
    
    def _apply_replica_transformations(self) -> None:
        """Apply replica transformations from Kustomize to Helm values."""
        kustomization = self.kustomize_data.get('kustomization', {})
        replicas = kustomization.get('replicas', [])
        
        for replica_transform in replicas:
            if 'count' in replica_transform:
                self.generator.values['replicaCount'] = replica_transform['count']
    
    def _convert_templates(self) -> None:
        """Convert Kubernetes manifests to Helm templates."""
        logger.info("Converting templates...")
        
        # Get all resources
        all_resources = self.parser.get_all_resources()
        
        # Convert each resource
        converted_resources = []
        for resource in all_resources:
            try:
                converted = self.converter.convert_resource(resource, self.generator.values)
                converted_resources.append(converted)
            except Exception as e:
                error_msg = f"Failed to convert resource {resource.get('kind', 'Unknown')}: {e}"
                logger.error(error_msg)
                self.migration_report['errors'].append(error_msg)
        
        # Store converted resources for chart generation
        self.kustomize_data['converted_resources'] = converted_resources
        
        logger.info(f"Converted {len(converted_resources)} resources to Helm templates")
    
    def _generate_helm_chart(self) -> None:
        """Generate the final Helm chart."""
        logger.info("Generating Helm chart...")
        
        # Use the enhanced generator with converted resources
        self.generator.generate_chart(self.kustomize_data)
        
        # Generate additional files if needed
        self._generate_notes_template()
        self._generate_tests()
    
    def _generate_notes_template(self) -> None:
        """Generate NOTES.txt template for the Helm chart."""
        notes_content = f'''1. Get the application URL by running these commands:
{{{{- if .Values.ingress.enabled }}}}
{{{{- range $host := .Values.ingress.hosts }}}}
  {{{{- range .paths }}}}
  http{{{{ if $.Values.ingress.tls }}}}s{{{{ end }}}}://{{{{ $host.host }}}}{{{{ .path }}}}
  {{{{- end }}}}
{{{{- end }}}}
{{{{- else if contains "NodePort" .Values.service.type }}}}
  export NODE_PORT=$(kubectl get --namespace {{{{ .Release.Namespace }}}} -o jsonpath="{{.spec.ports[0].nodePort}}" services {{{{ include "{self.chart_name}.fullname" . }}}})
  export NODE_IP=$(kubectl get nodes --namespace {{{{ .Release.Namespace }}}} -o jsonpath="{{.items[0].status.addresses[0].address}}")
  echo http://$NODE_IP:$NODE_PORT
{{{{- else if contains "LoadBalancer" .Values.service.type }}}}
     NOTE: It may take a few minutes for the LoadBalancer IP to be available.
           You can watch the status of by running 'kubectl get --namespace {{{{ .Release.Namespace }}}} svc -w {{{{ include "{self.chart_name}.fullname" . }}}}'
  export SERVICE_IP=$(kubectl get svc --namespace {{{{ .Release.Namespace }}}} {{{{ include "{self.chart_name}.fullname" . }}}} --template "{{{{ range (index .status.loadBalancer.ingress 0) }}}}{{{{.}}}}{{{{ end }}}}")
  echo http://$SERVICE_IP:{{{{ .Values.service.port }}}}
{{{{- else if contains "ClusterIP" .Values.service.type }}}}
  export POD_NAME=$(kubectl get pods --namespace {{{{ .Release.Namespace }}}} -l "app.kubernetes.io/name={{{{ include "{self.chart_name}.name" . }}}},app.kubernetes.io/instance={{{{ .Release.Name }}}}" -o jsonpath="{{.items[0].metadata.name}}")
  export CONTAINER_PORT=$(kubectl get pod --namespace {{{{ .Release.Namespace }}}} $POD_NAME -o jsonpath="{{.spec.containers[0].ports[0].containerPort}}")
  echo "Visit http://127.0.0.1:8080 to use your application"
  kubectl --namespace {{{{ .Release.Namespace }}}} port-forward $POD_NAME 8080:$CONTAINER_PORT
{{{{- end }}}}
'''
        
        notes_path = self.generator.templates_dir / "NOTES.txt"
        with open(notes_path, 'w') as f:
            f.write(notes_content)
        
        logger.info("Generated NOTES.txt")
    
    def _generate_tests(self) -> None:
        """Generate basic tests for the Helm chart."""
        tests_dir = self.generator.templates_dir / "tests"
        tests_dir.mkdir(exist_ok=True)
        
        test_content = f'''apiVersion: v1
kind: Pod
metadata:
  name: "{{{{ include "{self.chart_name}.fullname" . }}}}-test"
  labels:
    {{{{- include "{self.chart_name}.labels" . | nindent 4 }}}}
  annotations:
    "helm.sh/hook": test
spec:
  restartPolicy: Never
  containers:
    - name: wget
      image: busybox
      command: ['wget']
      args: ['{{{{ include "{self.chart_name}.fullname" . }}}}:{{{{ .Values.service.port }}}}']
'''
        
        test_path = tests_dir / "test-connection.yaml"
        with open(test_path, 'w') as f:
            f.write(test_content)
        
        logger.info("Generated test templates")
    
    def analyze_only(self) -> Dict[str, Any]:
        """
        Analyze the Kustomize configuration without performing migration.
        
        Returns:
            Analysis report
        """
        logger.info("Performing analysis only...")
        
        try:
            # Parse configuration
            self._parse_kustomize()
            
            # Analyze
            self._analyze_configuration()
            
            # Create analysis report
            analysis_report = {
                'source_directory': str(self.kustomize_dir),
                'chart_name': self.chart_name,
                'resources_found': len(self.kustomize_data.get('resources', [])),
                'patches_found': len(self.kustomize_data.get('patches', [])),
                'config_maps_found': len(self.kustomize_data.get('configMaps', [])),
                'secrets_found': len(self.kustomize_data.get('secrets', [])),
                'warnings': self.migration_report['warnings'],
                'errors': self.migration_report['errors'],
                'kustomization_features': list(self.kustomize_data.get('kustomization', {}).keys()),
                'resource_types': self._get_resource_types(),
                'migration_complexity': self._assess_migration_complexity()
            }
            
            return analysis_report
            
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            raise
    
    def _get_resource_types(self) -> Dict[str, int]:
        """Get count of each resource type."""
        resources = self.kustomize_data.get('resources', [])
        resource_types = {}
        
        for resource in resources:
            kind = resource.get('kind', 'Unknown')
            resource_types[kind] = resource_types.get(kind, 0) + 1
        
        return resource_types
    
    def _assess_migration_complexity(self) -> str:
        """Assess the complexity of the migration."""
        complexity_score = 0
        
        # Base complexity for each resource
        complexity_score += len(self.kustomize_data.get('resources', []))
        
        # Add complexity for patches
        patches = self.kustomize_data.get('patches', [])
        for patch in patches:
            if patch.get('type') == 'json6902':
                complexity_score += 3  # JSON patches are complex
            else:
                complexity_score += 1
        
        # Add complexity for generators
        complexity_score += len(self.kustomize_data.get('configMaps', [])) * 0.5
        complexity_score += len(self.kustomize_data.get('secrets', [])) * 0.5
        
        # Add complexity for transformations
        kustomization = self.kustomize_data.get('kustomization', {})
        if kustomization.get('images'):
            complexity_score += 1
        if kustomization.get('replicas'):
            complexity_score += 1
        if kustomization.get('transformers'):
            complexity_score += 5  # Custom transformers are very complex
        
        # Determine complexity level
        if complexity_score < 5:
            return 'Low'
        elif complexity_score < 15:
            return 'Medium'
        else:
            return 'High'
