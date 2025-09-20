"""
Helm Chart Generator Module

Generates Helm charts from parsed Kustomize configurations.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from jinja2 import Environment, BaseLoader
import logging

logger = logging.getLogger(__name__)


class HelmChartGenerator:
    """Generator for Helm charts from Kustomize configurations."""
    
    def __init__(self, chart_name: str, output_dir: Union[str, Path]):
        """
        Initialize the Helm chart generator.
        
        Args:
            chart_name: Name of the Helm chart
            output_dir: Directory where the Helm chart will be created
        """
        self.chart_name = chart_name
        self.output_dir = Path(output_dir)
        self.chart_dir = self.output_dir / chart_name
        self.templates_dir = self.chart_dir / "templates"
        
        # Initialize chart metadata
        self.chart_metadata = {
            'apiVersion': 'v2',
            'name': chart_name,
            'description': f'Helm chart for {chart_name} (migrated from Kustomize)',
            'type': 'application',
            'version': '0.1.0',
            'appVersion': '1.0.0'
        }
        
        # Initialize values
        self.values = {
            'replicaCount': 1,
            'image': {
                'repository': 'nginx',
                'pullPolicy': 'IfNotPresent',
                'tag': 'latest'
            },
            'nameOverride': '',
            'fullnameOverride': '',
            'serviceAccount': {
                'create': True,
                'annotations': {},
                'name': ''
            },
            'podAnnotations': {},
            'podSecurityContext': {},
            'securityContext': {},
            'service': {
                'type': 'ClusterIP',
                'port': 80
            },
            'ingress': {
                'enabled': False,
                'className': '',
                'annotations': {},
                'hosts': [],
                'tls': []
            },
            'resources': {},
            'autoscaling': {
                'enabled': False,
                'minReplicas': 1,
                'maxReplicas': 100,
                'targetCPUUtilizationPercentage': 80
            },
            'nodeSelector': {},
            'tolerations': [],
            'affinity': {}
        }
        
        # Template environment
        self.jinja_env = Environment(loader=BaseLoader())
    
    def generate_chart(self, kustomize_data: Dict[str, Any]) -> None:
        """
        Generate a complete Helm chart from Kustomize data.
        
        Args:
            kustomize_data: Parsed Kustomize configuration data
        """
        logger.info(f"Generating Helm chart: {self.chart_name}")
        
        # Create chart directory structure
        self._create_chart_structure()
        
        # Update chart metadata from kustomize data
        self._update_chart_metadata(kustomize_data)
        
        # Extract values from kustomize configuration
        self._extract_values(kustomize_data)
        
        # Generate templates
        self._generate_templates(kustomize_data)
        
        # Write Chart.yaml
        self._write_chart_yaml()
        
        # Write values.yaml
        self._write_values_yaml()
        
        # Write helper templates
        self._write_helpers_template()
        
        logger.info(f"Helm chart generated successfully at: {self.chart_dir}")
    
    def _create_chart_structure(self) -> None:
        """Create the basic Helm chart directory structure."""
        directories = [
            self.chart_dir,
            self.templates_dir,
            self.chart_dir / "charts"
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    def _update_chart_metadata(self, kustomize_data: Dict[str, Any]) -> None:
        """Update chart metadata based on kustomize configuration."""
        kustomization = kustomize_data.get('kustomization', {})
        
        # Try to extract app version from images
        images = kustomization.get('images', [])
        if images and 'newTag' in images[0]:
            self.chart_metadata['appVersion'] = images[0]['newTag']
        elif images and 'digest' in images[0]:
            # Use a portion of the digest as version
            digest = images[0]['digest'].split(':')[-1][:12]
            self.chart_metadata['appVersion'] = f"sha-{digest}"
    
    def _extract_values(self, kustomize_data: Dict[str, Any]) -> None:
        """Extract values from kustomize configuration."""
        kustomization = kustomize_data.get('kustomization', {})
        resources = kustomize_data.get('resources', [])
        
        # Extract from kustomization transformations
        if 'namespace' in kustomization:
            self.values['namespace'] = kustomization['namespace']
        
        if 'namePrefix' in kustomization:
            self.values['namePrefix'] = kustomization['namePrefix']
        
        if 'nameSuffix' in kustomization:
            self.values['nameSuffix'] = kustomization['nameSuffix']
        
        if 'commonLabels' in kustomization:
            self.values['commonLabels'] = kustomization['commonLabels']
        
        if 'commonAnnotations' in kustomization:
            self.values['commonAnnotations'] = kustomization['commonAnnotations']
        
        # Extract from images
        images = kustomization.get('images', [])
        if images:
            image_config = images[0]  # Use first image as primary
            if 'name' in image_config:
                parts = image_config['name'].split('/')
                self.values['image']['repository'] = '/'.join(parts[:-1]) if len(parts) > 1 else image_config['name']
            
            if 'newTag' in image_config:
                self.values['image']['tag'] = image_config['newTag']
            elif 'digest' in image_config:
                self.values['image']['digest'] = image_config['digest']
        
        # Extract from replicas
        replicas = kustomization.get('replicas', [])
        if replicas:
            replica_config = replicas[0]  # Use first replica config
            if 'count' in replica_config:
                self.values['replicaCount'] = replica_config['count']
        
        # Extract values from resources
        self._extract_values_from_resources(resources)
    
    def _extract_values_from_resources(self, resources: List[Dict[str, Any]]) -> None:
        """Extract values from Kubernetes resources."""
        for resource in resources:
            kind = resource.get('kind', '')
            
            if kind == 'Deployment':
                self._extract_deployment_values(resource)
            elif kind == 'Service':
                self._extract_service_values(resource)
            elif kind == 'Ingress':
                self._extract_ingress_values(resource)
            elif kind == 'ServiceAccount':
                self._extract_service_account_values(resource)
    
    def _extract_deployment_values(self, deployment: Dict[str, Any]) -> None:
        """Extract values from Deployment resource."""
        spec = deployment.get('spec', {})
        template = spec.get('template', {})
        pod_spec = template.get('spec', {})
        
        # Replica count
        if 'replicas' in spec:
            self.values['replicaCount'] = spec['replicas']
        
        # Container configuration
        containers = pod_spec.get('containers', [])
        if containers:
            container = containers[0]  # Use first container
            
            # Image
            if 'image' in container:
                image_parts = container['image'].split(':')
                if len(image_parts) == 2:
                    self.values['image']['repository'] = image_parts[0]
                    self.values['image']['tag'] = image_parts[1]
                else:
                    self.values['image']['repository'] = container['image']
            
            # Image pull policy
            if 'imagePullPolicy' in container:
                self.values['image']['pullPolicy'] = container['imagePullPolicy']
            
            # Resources
            if 'resources' in container:
                self.values['resources'] = container['resources']
            
            # Security context
            if 'securityContext' in container:
                self.values['securityContext'] = container['securityContext']
        
        # Pod annotations
        pod_annotations = template.get('metadata', {}).get('annotations', {})
        if pod_annotations:
            self.values['podAnnotations'].update(pod_annotations)
        
        # Pod security context
        if 'securityContext' in pod_spec:
            self.values['podSecurityContext'] = pod_spec['securityContext']
        
        # Node selector
        if 'nodeSelector' in pod_spec:
            self.values['nodeSelector'] = pod_spec['nodeSelector']
        
        # Tolerations
        if 'tolerations' in pod_spec:
            self.values['tolerations'] = pod_spec['tolerations']
        
        # Affinity
        if 'affinity' in pod_spec:
            self.values['affinity'] = pod_spec['affinity']
    
    def _extract_service_values(self, service: Dict[str, Any]) -> None:
        """Extract values from Service resource."""
        spec = service.get('spec', {})
        
        if 'type' in spec:
            self.values['service']['type'] = spec['type']
        
        ports = spec.get('ports', [])
        if ports:
            port = ports[0]  # Use first port
            if 'port' in port:
                self.values['service']['port'] = port['port']
    
    def _extract_ingress_values(self, ingress: Dict[str, Any]) -> None:
        """Extract values from Ingress resource."""
        self.values['ingress']['enabled'] = True
        
        metadata = ingress.get('metadata', {})
        annotations = metadata.get('annotations', {})
        if annotations:
            self.values['ingress']['annotations'] = annotations
        
        spec = ingress.get('spec', {})
        if 'ingressClassName' in spec:
            self.values['ingress']['className'] = spec['ingressClassName']
        
        rules = spec.get('rules', [])
        if rules:
            hosts = []
            for rule in rules:
                if 'host' in rule:
                    hosts.append({'host': rule['host'], 'paths': []})
            self.values['ingress']['hosts'] = hosts
        
        if 'tls' in spec:
            self.values['ingress']['tls'] = spec['tls']
    
    def _extract_service_account_values(self, service_account: Dict[str, Any]) -> None:
        """Extract values from ServiceAccount resource."""
        self.values['serviceAccount']['create'] = True
        
        metadata = service_account.get('metadata', {})
        if 'name' in metadata:
            self.values['serviceAccount']['name'] = metadata['name']
        
        annotations = metadata.get('annotations', {})
        if annotations:
            self.values['serviceAccount']['annotations'] = annotations
    
    def _generate_templates(self, kustomize_data: Dict[str, Any]) -> None:
        """Generate Helm templates from Kustomize resources."""
        resources = kustomize_data.get('resources', [])
        
        # Group resources by kind
        resource_groups = {}
        for resource in resources:
            kind = resource.get('kind', 'Unknown')
            if kind not in resource_groups:
                resource_groups[kind] = []
            resource_groups[kind].append(resource)
        
        # Generate template for each resource type
        for kind, resource_list in resource_groups.items():
            self._generate_resource_template(kind, resource_list)
    
    def _generate_resource_template(self, kind: str, resources: List[Dict[str, Any]]) -> None:
        """Generate a Helm template for a specific resource kind."""
        template_name = f"{kind.lower()}.yaml"
        template_path = self.templates_dir / template_name
        
        template_content = []
        
        for i, resource in enumerate(resources):
            if i > 0:
                template_content.append("---")
            
            # Convert resource to Helm template
            helm_resource = self._convert_resource_to_template(resource)
            # Post-process to add proper Helm templating
            processed_yaml = self._post_process_template_yaml(helm_resource)
            template_content.append(processed_yaml)
        
        # Write template file
        with open(template_path, 'w') as f:
            f.write('\n'.join(template_content))
        
        logger.info(f"Generated template: {template_name}")
    
    def _convert_resource_to_template(self, resource: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a Kubernetes resource to a Helm template."""
        # Create a copy of the resource
        template_resource = yaml.safe_load(yaml.dump(resource))
        
        # Remove source file metadata
        if '_source_file' in template_resource:
            del template_resource['_source_file']
        
        # Apply templating transformations
        self._apply_name_templating(template_resource)
        self._apply_namespace_templating(template_resource)
        self._apply_image_templating(template_resource)
        self._apply_replica_templating(template_resource)
        self._apply_label_templating(template_resource)
        self._apply_annotation_templating(template_resource)
        
        return template_resource
    
    def _apply_name_templating(self, resource: Dict[str, Any]) -> None:
        """Apply name templating to resource."""
        metadata = resource.get('metadata', {})
        if 'name' in metadata:
            original_name = metadata['name']
            # Use Helm naming convention
            metadata['name'] = f"{{{{ include \"{self.chart_name}.fullname\" . }}}}"
            
            # Store original name as a comment or annotation for reference
            if 'annotations' not in metadata:
                metadata['annotations'] = {}
            metadata['annotations']['helm.sh/original-name'] = original_name
    
    def _apply_namespace_templating(self, resource: Dict[str, Any]) -> None:
        """Apply namespace templating to resource."""
        metadata = resource.get('metadata', {})
        if 'namespace' in metadata:
            metadata['namespace'] = "{{ .Values.namespace | default .Release.Namespace }}"
    
    def _apply_image_templating(self, resource: Dict[str, Any]) -> None:
        """Apply image templating to resource."""
        if resource.get('kind') == 'Deployment':
            spec = resource.get('spec', {})
            template = spec.get('template', {})
            pod_spec = template.get('spec', {})
            containers = pod_spec.get('containers', [])
            
            for container in containers:
                if 'image' in container:
                    container['image'] = "{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}"
                
                if 'imagePullPolicy' in container:
                    container['imagePullPolicy'] = "{{ .Values.image.pullPolicy }}"
    
    def _apply_replica_templating(self, resource: Dict[str, Any]) -> None:
        """Apply replica templating to resource."""
        if resource.get('kind') == 'Deployment':
            spec = resource.get('spec', {})
            if 'replicas' in spec:
                spec['replicas'] = "{{ .Values.replicaCount }}"
    
    def _apply_label_templating(self, resource: Dict[str, Any]) -> None:
        """Apply label templating to resource."""
        metadata = resource.get('metadata', {})
        
        # Add standard Helm labels
        if 'labels' not in metadata:
            metadata['labels'] = {}
        
        standard_labels = {
            'helm.sh/chart': f"{{{{ include \"{self.chart_name}.chart\" . }}}}",
            'app.kubernetes.io/name': f"{{{{ include \"{self.chart_name}.name\" . }}}}",
            'app.kubernetes.io/instance': "{{ .Release.Name }}",
            'app.kubernetes.io/version': "{{ .Chart.AppVersion | quote }}",
            'app.kubernetes.io/managed-by': "{{ .Release.Service }}"
        }
        
        metadata['labels'].update(standard_labels)
        
        # Add common labels if they exist
        metadata['labels']['{{- with .Values.commonLabels }}'] = None
        metadata['labels']['{{- toYaml . | nindent 4 }}'] = None
        metadata['labels']['{{- end }}'] = None
    
    def _apply_annotation_templating(self, resource: Dict[str, Any]) -> None:
        """Apply annotation templating to resource."""
        metadata = resource.get('metadata', {})
        
        if 'annotations' not in metadata:
            metadata['annotations'] = {}
        
        # Add common annotations if they exist - handle this in post-processing
        if hasattr(self, 'common_annotations') and self.common_annotations:
            metadata['annotations'].update(self.common_annotations)
    
    def _write_chart_yaml(self) -> None:
        """Write the Chart.yaml file."""
        chart_yaml_path = self.chart_dir / "Chart.yaml"
        
        with open(chart_yaml_path, 'w') as f:
            yaml.dump(self.chart_metadata, f, default_flow_style=False)
        
        logger.info("Generated Chart.yaml")
    
    def _write_values_yaml(self) -> None:
        """Write the values.yaml file."""
        values_yaml_path = self.chart_dir / "values.yaml"
        
        # Configure YAML dumper for multi-line strings
        self._write_values_file(values_yaml_path, self.values)
        
        logger.info("Generated values.yaml")
    
    def _write_values_file(self, file_path: Path, values: Dict[str, Any]) -> None:
        """Write values file with proper YAML formatting for multi-line strings."""
        # Create a custom YAML dumper class
        class MultiLineDumper(yaml.SafeDumper):
            pass
        
        # Custom YAML representer for multi-line strings
        def represent_multiline_str(dumper, data):
            # Force literal block style for any string with newlines
            # This handles ConfigMap data properly
            if '\n' in data and len(data.split('\n')) > 2:
                return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|-')
            return dumper.represent_scalar('tag:yaml.org,2002:str', data)
        
        MultiLineDumper.add_representer(str, represent_multiline_str)
        
        # Process values to ensure proper formatting
        processed_values = self._process_values_for_multiline(values)
        
        with open(file_path, 'w') as f:
            yaml.dump(processed_values, f, default_flow_style=False, allow_unicode=True, Dumper=MultiLineDumper)
    
    def _process_values_for_multiline(self, values: Dict[str, Any]) -> Dict[str, Any]:
        """Process values to ensure proper multi-line string formatting."""
        processed = {}
        
        for key, value in values.items():
            if isinstance(value, dict):
                processed[key] = self._process_values_for_multiline(value)
            elif isinstance(value, str):
                # Handle escaped newlines in strings (common in ConfigMap data)
                if '\\n' in value:
                    # Convert escaped newlines to actual newlines
                    processed[key] = value.replace('\\n', '\n').strip()
                elif '\n' in value:
                    # Already has newlines, just strip
                    processed[key] = value.strip()
                else:
                    processed[key] = value
            else:
                processed[key] = value
        
        return processed
    
    def _write_helpers_template(self) -> None:
        """Write the _helpers.tpl file with common template functions."""
        helpers_content = f'''{{/*
Expand the name of the chart.
*/}}
{{{{- define "{self.chart_name}.name" -}}}}
{{{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}}}
{{{{- end }}}}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{{{- define "{self.chart_name}.fullname" -}}}}
{{{{- if .Values.fullnameOverride }}}}
{{{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}}}
{{{{- else }}}}
{{{{- $name := default .Chart.Name .Values.nameOverride }}}}
{{{{- if contains $name .Release.Name }}}}
{{{{- .Release.Name | trunc 63 | trimSuffix "-" }}}}
{{{{- else }}}}
{{{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}}}
{{{{- end }}}}
{{{{- end }}}}
{{{{- end }}}}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{{{- define "{self.chart_name}.chart" -}}}}
{{{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}}}
{{{{- end }}}}

{{/*
Common labels
*/}}
{{{{- define "{self.chart_name}.labels" -}}}}
helm.sh/chart: {{{{ include "{self.chart_name}.chart" . }}}}
{{{{ include "{self.chart_name}.selectorLabels" . }}}}
{{{{- if .Chart.AppVersion }}}}
app.kubernetes.io/version: {{{{ .Chart.AppVersion | quote }}}}
{{{{- end }}}}
app.kubernetes.io/managed-by: {{{{ .Release.Service }}}}
{{{{- end }}}}

{{/*
Selector labels
*/}}
{{{{- define "{self.chart_name}.selectorLabels" -}}}}
app.kubernetes.io/name: {{{{ include "{self.chart_name}.name" . }}}}
app.kubernetes.io/instance: {{{{ .Release.Name }}}}
{{{{- end }}}}

{{/*
Create the name of the service account to use
*/}}
{{{{- define "{self.chart_name}.serviceAccountName" -}}}}
{{{{- if .Values.serviceAccount.create }}}}
{{{{- default (include "{self.chart_name}.fullname" .) .Values.serviceAccount.name }}}}
{{{{- else }}}}
{{{{- default "default" .Values.serviceAccount.name }}}}
{{{{- end }}}}
{{{{- end }}}}
'''
        
        helpers_path = self.templates_dir / "_helpers.tpl"
        with open(helpers_path, 'w') as f:
            f.write(helpers_content)
        
        logger.info("Generated _helpers.tpl")
    
    def _post_process_template_yaml(self, resource: Dict[str, Any]) -> str:
        """Post-process template YAML to add proper Helm templating."""
        # First, generate the base YAML
        yaml_content = yaml.dump(resource, default_flow_style=False)
        
        # Add common annotations and labels templating
        if 'metadata' in resource and 'annotations' in resource['metadata']:
            # Add Helm templating for common annotations
            annotation_template = """{{- with .Values.commonAnnotations }}
    {{- toYaml . | nindent 4 }}
    {{- end }}"""
            
            # Insert the template after existing annotations
            lines = yaml_content.split('\n')
            in_annotations = False
            annotation_indent = 0
            insert_index = -1
            
            for i, line in enumerate(lines):
                if 'annotations:' in line and 'metadata:' in lines[max(0, i-5):i]:
                    in_annotations = True
                    annotation_indent = len(line) - len(line.lstrip())
                elif in_annotations and line.strip() and not line.startswith(' ' * (annotation_indent + 2)):
                    # We've left the annotations section
                    insert_index = i
                    break
                elif in_annotations and i == len(lines) - 1:
                    # End of file
                    insert_index = i + 1
                    break
            
            if insert_index > 0:
                # Insert the template
                template_lines = annotation_template.split('\n')
                formatted_template = []
                for template_line in template_lines:
                    if template_line.strip():
                        formatted_template.append(' ' * (annotation_indent + 2) + template_line.strip())
                    else:
                        formatted_template.append('')
                
                lines[insert_index:insert_index] = formatted_template
                yaml_content = '\n'.join(lines)
        
        return yaml_content
