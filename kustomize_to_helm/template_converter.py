"""
Template Converter Module

Handles advanced conversion of Kubernetes manifests to Helm templates.
"""

import re
import yaml
from typing import Dict, List, Any, Optional, Union
from jinja2 import Environment, BaseLoader, Template
import logging

logger = logging.getLogger(__name__)


class TemplateConverter:
    """Converts Kubernetes manifests to Helm templates with advanced templating."""
    
    def __init__(self, chart_name: str):
        """
        Initialize the template converter.
        
        Args:
            chart_name: Name of the Helm chart
        """
        self.chart_name = chart_name
        self.jinja_env = Environment(loader=BaseLoader())
        
        # Value extraction patterns
        self.value_patterns = {
            'image': re.compile(r'([a-zA-Z0-9\-\.]+/)?([a-zA-Z0-9\-\.]+):([a-zA-Z0-9\-\.]+)'),
            'port': re.compile(r'\b\d{2,5}\b'),
            'replica': re.compile(r'\breplicas:\s*(\d+)'),
            'cpu': re.compile(r'\d+m|\d+(\.\d+)?'),
            'memory': re.compile(r'\d+[KMGT]i?'),
        }
        
        # Common Kubernetes resource field mappings
        self.field_mappings = {
            'Deployment': {
                'spec.replicas': '.Values.replicaCount',
                'spec.template.spec.containers[0].image': '{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}',
                'spec.template.spec.containers[0].imagePullPolicy': '.Values.image.pullPolicy',
                'spec.template.spec.containers[0].resources': '.Values.resources',
                'spec.template.spec.nodeSelector': '.Values.nodeSelector',
                'spec.template.spec.tolerations': '.Values.tolerations',
                'spec.template.spec.affinity': '.Values.affinity',
                'spec.template.spec.securityContext': '.Values.podSecurityContext',
                'spec.template.spec.containers[0].securityContext': '.Values.securityContext',
            },
            'Service': {
                'spec.type': '.Values.service.type',
                'spec.ports[0].port': '.Values.service.port',
                'spec.ports[0].targetPort': '.Values.service.targetPort',
            },
            'Ingress': {
                'metadata.annotations': '.Values.ingress.annotations',
                'spec.ingressClassName': '.Values.ingress.className',
                'spec.rules': '.Values.ingress.hosts',
                'spec.tls': '.Values.ingress.tls',
            },
            'ConfigMap': {
                'data': '.Values.configMap.data',
            },
            'Secret': {
                'data': '.Values.secret.data',
                'type': '.Values.secret.type',
            },
            'ServiceAccount': {
                'metadata.annotations': '.Values.serviceAccount.annotations',
            }
        }
    
    def convert_resource(self, resource: Dict[str, Any], extracted_values: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert a Kubernetes resource to a Helm template.
        
        Args:
            resource: Original Kubernetes resource
            extracted_values: Values extracted from kustomize configuration
            
        Returns:
            Templated resource
        """
        # Create a deep copy
        templated_resource = yaml.safe_load(yaml.dump(resource))
        
        # Remove internal metadata
        if '_source_file' in templated_resource:
            del templated_resource['_source_file']
        
        # Apply standard templating
        self._apply_metadata_templating(templated_resource)
        self._apply_field_templating(templated_resource, extracted_values)
        self._apply_conditional_templating(templated_resource)
        self._apply_advanced_templating(templated_resource)
        
        return templated_resource
    
    def _apply_metadata_templating(self, resource: Dict[str, Any]) -> None:
        """Apply templating to metadata fields."""
        metadata = resource.get('metadata', {})
        
        # Name templating
        if 'name' in metadata:
            original_name = metadata['name']
            metadata['name'] = f"{{{{ include \"{self.chart_name}.fullname\" . }}}}"
            
            # Store original name for reference
            if 'annotations' not in metadata:
                metadata['annotations'] = {}
            metadata['annotations']['helm.sh/original-name'] = original_name
        
        # Namespace templating
        if 'namespace' in metadata:
            metadata['namespace'] = "{{ .Release.Namespace }}"
        
        # Labels templating
        if 'labels' not in metadata:
            metadata['labels'] = {}
        
        # Add standard Helm labels template
        helm_labels = f"{{{{- include \"{self.chart_name}.labels\" . | nindent 4 }}}}"
        metadata['labels']['{{HELM_LABELS}}'] = helm_labels
        
        # Common labels from values
        metadata['labels']['{{- with .Values.commonLabels }}'] = None
        metadata['labels']['{{- toYaml . | nindent 4 }}'] = None
        metadata['labels']['{{- end }}'] = None
        
        # Annotations templating
        if 'annotations' not in metadata:
            metadata['annotations'] = {}
        
        # Common annotations from values
        metadata['annotations']['{{- with .Values.commonAnnotations }}'] = None
        metadata['annotations']['{{- toYaml . | nindent 4 }}'] = None
        metadata['annotations']['{{- end }}'] = None
    
    def _apply_field_templating(self, resource: Dict[str, Any], extracted_values: Dict[str, Any]) -> None:
        """Apply field-specific templating based on resource kind."""
        kind = resource.get('kind', '')
        
        if kind in self.field_mappings:
            mappings = self.field_mappings[kind]
            
            for field_path, template_value in mappings.items():
                self._set_nested_field(resource, field_path, template_value, extracted_values)
    
    def _apply_conditional_templating(self, resource: Dict[str, Any]) -> None:
        """Apply conditional templating for optional resources."""
        kind = resource.get('kind', '')
        
        # Add conditional blocks for optional resources
        if kind == 'Ingress':
            # Wrap entire resource in conditional
            resource['{{- if .Values.ingress.enabled }}'] = None
            resource['{{- end }}'] = None
        
        elif kind == 'ServiceAccount':
            resource['{{- if .Values.serviceAccount.create }}'] = None
            resource['{{- end }}'] = None
        
        elif kind == 'HorizontalPodAutoscaler':
            resource['{{- if .Values.autoscaling.enabled }}'] = None
            resource['{{- end }}'] = None
    
    def _apply_advanced_templating(self, resource: Dict[str, Any]) -> None:
        """Apply advanced templating patterns."""
        kind = resource.get('kind', '')
        
        if kind == 'Deployment':
            self._template_deployment_advanced(resource)
        elif kind == 'Service':
            self._template_service_advanced(resource)
        elif kind == 'Ingress':
            self._template_ingress_advanced(resource)
    
    def _template_deployment_advanced(self, deployment: Dict[str, Any]) -> None:
        """Apply advanced templating to Deployment resources."""
        spec = deployment.get('spec', {})
        template = spec.get('template', {})
        pod_spec = template.get('spec', {})
        
        # Template selector labels
        if 'selector' in spec and 'matchLabels' in spec['selector']:
            spec['selector']['matchLabels'] = f"{{{{- include \"{self.chart_name}.selectorLabels\" . | nindent 6 }}}}"
        
        # Template pod labels
        pod_metadata = template.get('metadata', {})
        if 'labels' not in pod_metadata:
            pod_metadata['labels'] = {}
        pod_metadata['labels'] = f"{{{{- include \"{self.chart_name}.selectorLabels\" . | nindent 8 }}}}"
        
        # Template containers with loops for multiple containers
        containers = pod_spec.get('containers', [])
        if len(containers) > 1:
            # Use range for multiple containers
            pod_spec['containers'] = [
                {
                    '{{- range .Values.containers }}': None,
                    'name': '{{ .name }}',
                    'image': '{{ .image.repository }}:{{ .image.tag | default $.Chart.AppVersion }}',
                    'imagePullPolicy': '{{ .image.pullPolicy | default "IfNotPresent" }}',
                    '{{- with .resources }}': None,
                    'resources': '{{- toYaml . | nindent 10 }}',
                    '{{- end }}': None,
                    '{{- end }}': None
                }
            ]
        
        # Template environment variables
        for container in containers:
            if 'env' in container:
                self._template_environment_variables(container)
        
        # Template volume mounts and volumes
        if 'volumes' in pod_spec:
            self._template_volumes(pod_spec)
    
    def _template_service_advanced(self, service: Dict[str, Any]) -> None:
        """Apply advanced templating to Service resources."""
        spec = service.get('spec', {})
        
        # Template selector
        if 'selector' in spec:
            spec['selector'] = f"{{{{- include \"{self.chart_name}.selectorLabels\" . | nindent 4 }}}}"
        
        # Template ports with potential for multiple ports
        ports = spec.get('ports', [])
        if len(ports) > 1:
            spec['ports'] = [
                {
                    '{{- range .Values.service.ports }}': None,
                    'port': '{{ .port }}',
                    'targetPort': '{{ .targetPort | default .port }}',
                    'protocol': '{{ .protocol | default "TCP" }}',
                    'name': '{{ .name | default "http" }}',
                    '{{- end }}': None
                }
            ]
    
    def _template_ingress_advanced(self, ingress: Dict[str, Any]) -> None:
        """Apply advanced templating to Ingress resources."""
        spec = ingress.get('spec', {})
        
        # Template rules with range
        if 'rules' in spec:
            spec['rules'] = [
                {
                    '{{- range .Values.ingress.hosts }}': None,
                    'host': '{{ .host | quote }}',
                    'http': {
                        'paths': [
                            {
                                '{{- range .paths }}': None,
                                'path': '{{ .path }}',
                                'pathType': '{{ .pathType }}',
                                'backend': {
                                    'service': {
                                        'name': f"{{{{ include \"{self.chart_name}.fullname\" $ }}}}",
                                        'port': {
                                            'number': '{{ $.Values.service.port }}'
                                        }
                                    }
                                },
                                '{{- end }}': None
                            }
                        ]
                    },
                    '{{- end }}': None
                }
            ]
        
        # Template TLS
        if 'tls' in spec:
            spec['tls'] = [
                {
                    '{{- range .Values.ingress.tls }}': None,
                    'hosts': [
                        {
                            '{{- range .hosts }}': None,
                            '- {{ . | quote }}': None,
                            '{{- end }}': None
                        }
                    ],
                    'secretName': '{{ .secretName }}',
                    '{{- end }}': None
                }
            ]
    
    def _template_environment_variables(self, container: Dict[str, Any]) -> None:
        """Template environment variables with configMap and secret references."""
        env = container.get('env', [])
        
        for env_var in env:
            if 'valueFrom' in env_var:
                value_from = env_var['valueFrom']
                
                # Template configMapKeyRef
                if 'configMapKeyRef' in value_from:
                    config_map_ref = value_from['configMapKeyRef']
                    if 'name' in config_map_ref:
                        config_map_ref['name'] = f"{{{{ include \"{self.chart_name}.fullname\" . }}}}"
                
                # Template secretKeyRef
                if 'secretKeyRef' in value_from:
                    secret_ref = value_from['secretKeyRef']
                    if 'name' in secret_ref:
                        secret_ref['name'] = f"{{{{ include \"{self.chart_name}.fullname\" . }}}}"
    
    def _template_volumes(self, pod_spec: Dict[str, Any]) -> None:
        """Template volumes and volume mounts."""
        volumes = pod_spec.get('volumes', [])
        
        for volume in volumes:
            # Template configMap volumes
            if 'configMap' in volume:
                config_map = volume['configMap']
                if 'name' in config_map:
                    config_map['name'] = f"{{{{ include \"{self.chart_name}.fullname\" . }}}}"
            
            # Template secret volumes
            if 'secret' in volume:
                secret = volume['secret']
                if 'secretName' in secret:
                    secret['secretName'] = f"{{{{ include \"{self.chart_name}.fullname\" . }}}}"
    
    def _set_nested_field(self, obj: Dict[str, Any], path: str, value: str, context: Dict[str, Any]) -> None:
        """Set a nested field in a dictionary using dot notation."""
        keys = path.split('.')
        current = obj
        
        try:
            # Navigate to the parent of the target field
            for key in keys[:-1]:
                # Handle array notation like containers[0]
                if '[' in key and ']' in key:
                    base_key = key.split('[')[0]
                    index = int(key.split('[')[1].split(']')[0])
                    
                    if base_key not in current:
                        current[base_key] = []
                    
                    # Ensure array is long enough
                    while len(current[base_key]) <= index:
                        current[base_key].append({})
                    
                    current = current[base_key][index]
                else:
                    if key not in current:
                        current[key] = {}
                    current = current[key]
            
            # Set the final value
            final_key = keys[-1]
            if '[' in final_key and ']' in final_key:
                base_key = final_key.split('[')[0]
                index = int(final_key.split('[')[1].split(']')[0])
                
                if base_key not in current:
                    current[base_key] = []
                
                while len(current[base_key]) <= index:
                    current[base_key].append(None)
                
                current[base_key][index] = value
            else:
                current[final_key] = value
                
        except (KeyError, IndexError, ValueError) as e:
            logger.warning(f"Could not set field {path}: {e}")
    
    def extract_parameterizable_values(self, resources: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract values that should be parameterized from resources.
        
        Args:
            resources: List of Kubernetes resources
            
        Returns:
            Dictionary of extracted values
        """
        extracted = {}
        
        for resource in resources:
            kind = resource.get('kind', '')
            
            if kind == 'Deployment':
                extracted.update(self._extract_deployment_params(resource))
            elif kind == 'Service':
                extracted.update(self._extract_service_params(resource))
            elif kind == 'Ingress':
                extracted.update(self._extract_ingress_params(resource))
            elif kind == 'ConfigMap':
                extracted.update(self._extract_configmap_params(resource))
            elif kind == 'Secret':
                extracted.update(self._extract_secret_params(resource))
        
        return extracted
    
    def _extract_deployment_params(self, deployment: Dict[str, Any]) -> Dict[str, Any]:
        """Extract parameterizable values from Deployment."""
        params = {}
        spec = deployment.get('spec', {})
        template = spec.get('template', {})
        pod_spec = template.get('spec', {})
        
        # Replica count
        if 'replicas' in spec:
            params['replicaCount'] = spec['replicas']
        
        # Container image and configuration
        containers = pod_spec.get('containers', [])
        if containers:
            container = containers[0]
            
            if 'image' in container:
                image_parts = container['image'].split(':')
                if len(image_parts) == 2:
                    params['image'] = {
                        'repository': image_parts[0],
                        'tag': image_parts[1]
                    }
                else:
                    params['image'] = {'repository': container['image']}
            
            if 'imagePullPolicy' in container:
                if 'image' not in params:
                    params['image'] = {}
                params['image']['pullPolicy'] = container['imagePullPolicy']
            
            if 'resources' in container:
                params['resources'] = container['resources']
        
        # Pod configuration
        if 'nodeSelector' in pod_spec:
            params['nodeSelector'] = pod_spec['nodeSelector']
        
        if 'tolerations' in pod_spec:
            params['tolerations'] = pod_spec['tolerations']
        
        if 'affinity' in pod_spec:
            params['affinity'] = pod_spec['affinity']
        
        return params
    
    def _extract_service_params(self, service: Dict[str, Any]) -> Dict[str, Any]:
        """Extract parameterizable values from Service."""
        params = {}
        spec = service.get('spec', {})
        
        service_config = {}
        
        if 'type' in spec:
            service_config['type'] = spec['type']
        
        ports = spec.get('ports', [])
        if ports:
            port = ports[0]
            if 'port' in port:
                service_config['port'] = port['port']
            if 'targetPort' in port:
                service_config['targetPort'] = port['targetPort']
        
        if service_config:
            params['service'] = service_config
        
        return params
    
    def _extract_ingress_params(self, ingress: Dict[str, Any]) -> Dict[str, Any]:
        """Extract parameterizable values from Ingress."""
        params = {
            'ingress': {
                'enabled': True,
                'className': '',
                'annotations': {},
                'hosts': [],
                'tls': []
            }
        }
        
        metadata = ingress.get('metadata', {})
        spec = ingress.get('spec', {})
        
        # Annotations
        annotations = metadata.get('annotations', {})
        if annotations:
            params['ingress']['annotations'] = annotations
        
        # Ingress class
        if 'ingressClassName' in spec:
            params['ingress']['className'] = spec['ingressClassName']
        
        # Rules
        rules = spec.get('rules', [])
        hosts = []
        for rule in rules:
            if 'host' in rule:
                host_config = {'host': rule['host']}
                
                # Extract paths
                http = rule.get('http', {})
                paths = http.get('paths', [])
                if paths:
                    host_config['paths'] = [
                        {
                            'path': path.get('path', '/'),
                            'pathType': path.get('pathType', 'Prefix')
                        }
                        for path in paths
                    ]
                
                hosts.append(host_config)
        
        params['ingress']['hosts'] = hosts
        
        # TLS
        if 'tls' in spec:
            params['ingress']['tls'] = spec['tls']
        
        return params
    
    def _extract_configmap_params(self, configmap: Dict[str, Any]) -> Dict[str, Any]:
        """Extract parameterizable values from ConfigMap."""
        data = configmap.get('data', {})
        
        if data:
            return {
                'configMap': {
                    'data': data
                }
            }
        
        return {}
    
    def _extract_secret_params(self, secret: Dict[str, Any]) -> Dict[str, Any]:
        """Extract parameterizable values from Secret."""
        data = secret.get('data', {})
        secret_type = secret.get('type', 'Opaque')
        
        params = {
            'secret': {
                'type': secret_type
            }
        }
        
        if data:
            params['secret']['data'] = data
        
        return params
