"""
Overlay Analyzer Module

Analyzes differences between Kustomize base and overlays to identify parameterizable values.
"""

import logging
from typing import Dict, List, Any, Set, Optional
from collections import defaultdict
import json

logger = logging.getLogger(__name__)


class OverlayAnalyzer:
    """Analyzes overlay differences to identify parameterizable values."""
    
    def __init__(self):
        """Initialize the overlay analyzer."""
        self.resources_by_overlay = {}
        self.differences = {}
        self.parameterizable_paths = set()
        
    def analyze_differences(self, overlay_resources: Dict[str, List[Dict[str, Any]]]) -> None:
        """
        Analyze differences between base and overlay resources.
        
        Args:
            overlay_resources: Dict mapping overlay names to their resources
                             (including 'base' as a key for base resources)
        """
        logger.info("Analyzing differences between base and overlays...")
        
        self.resources_by_overlay = overlay_resources
        
        if 'base' not in overlay_resources:
            logger.warning("No base resources provided for comparison")
            return
        
        base_resources = overlay_resources['base']
        
        # Create lookup for base resources by kind and name
        base_lookup = self._create_resource_lookup(base_resources)
        
        # Compare each overlay with base
        for overlay_name, overlay_resources_list in overlay_resources.items():
            if overlay_name == 'base':
                continue
                
            logger.info(f"Analyzing overlay: {overlay_name}")
            
            overlay_lookup = self._create_resource_lookup(overlay_resources_list)
            overlay_diffs = self._compare_resources(base_lookup, overlay_lookup, overlay_name)
            
            if overlay_diffs:
                self.differences[overlay_name] = overlay_diffs
                logger.info(f"Found {len(overlay_diffs)} differences in overlay '{overlay_name}'")
        
        # Identify parameterizable paths across all overlays
        self._identify_parameterizable_paths()
        
        logger.info(f"Analysis complete. Found {len(self.parameterizable_paths)} parameterizable paths")
    
    def _create_resource_lookup(self, resources: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Create a lookup dictionary for resources by kind and name."""
        lookup = {}
        
        for resource in resources:
            kind = resource.get('kind', '')
            name = resource.get('metadata', {}).get('name', '')
            
            if kind and name:
                key = f"{kind}/{name}"
                lookup[key] = resource
        
        return lookup
    
    def _compare_resources(self, base_lookup: Dict[str, Dict[str, Any]], 
                          overlay_lookup: Dict[str, Dict[str, Any]], 
                          overlay_name: str) -> Dict[str, Any]:
        """Compare overlay resources with base resources."""
        differences = {}
        
        # Compare existing resources
        for resource_key, base_resource in base_lookup.items():
            if resource_key in overlay_lookup:
                overlay_resource = overlay_lookup[resource_key]
                resource_diffs = self._compare_resource_content(base_resource, overlay_resource, resource_key)
                
                if resource_diffs:
                    differences.update(resource_diffs)
        
        # Check for new resources in overlay
        for resource_key, overlay_resource in overlay_lookup.items():
            if resource_key not in base_lookup:
                logger.info(f"New resource in overlay '{overlay_name}': {resource_key}")
                # For new resources, extract all parameterizable values
                new_resource_params = self._extract_resource_parameters(overlay_resource, resource_key)
                differences.update(new_resource_params)
        
        return differences
    
    def _compare_resource_content(self, base_resource: Dict[str, Any], 
                                 overlay_resource: Dict[str, Any], 
                                 resource_key: str) -> Dict[str, Any]:
        """Compare the content of two resources and identify differences."""
        differences = {}
        
        # Compare specific fields that are commonly parameterized
        parameterizable_fields = [
            'spec.replicas',
            'spec.template.spec.containers[0].image',
            'spec.template.spec.containers[0].resources',
            'spec.type',  # Service type
            'spec.ports',  # Service ports
            'metadata.namespace',
            'metadata.labels',
            'metadata.annotations',
            'data',  # ConfigMap/Secret data
        ]
        
        for field_path in parameterizable_fields:
            base_value = self._get_nested_value(base_resource, field_path)
            overlay_value = self._get_nested_value(overlay_resource, field_path)
            
            if base_value != overlay_value and overlay_value is not None:
                param_key = f"{resource_key}.{field_path}"
                differences[param_key] = overlay_value
                self.parameterizable_paths.add(field_path)
        
        # Deep comparison for complex differences
        deep_diffs = self._deep_compare(base_resource, overlay_resource, resource_key)
        differences.update(deep_diffs)
        
        return differences
    
    def _deep_compare(self, base: Any, overlay: Any, path: str = '') -> Dict[str, Any]:
        """Perform deep comparison between base and overlay values."""
        differences = {}
        
        if type(base) != type(overlay):
            differences[path] = overlay
            return differences
        
        if isinstance(base, dict):
            # Compare dictionaries
            all_keys = set(base.keys()) | set(overlay.keys())
            
            for key in all_keys:
                new_path = f"{path}.{key}" if path else key
                
                if key not in base:
                    differences[new_path] = overlay[key]
                elif key not in overlay:
                    # Key was removed in overlay - might be intentional
                    continue
                else:
                    # Recursively compare
                    nested_diffs = self._deep_compare(base[key], overlay[key], new_path)
                    differences.update(nested_diffs)
        
        elif isinstance(base, list):
            # Compare lists
            if len(base) != len(overlay):
                differences[path] = overlay
            else:
                for i, (base_item, overlay_item) in enumerate(zip(base, overlay)):
                    new_path = f"{path}[{i}]"
                    nested_diffs = self._deep_compare(base_item, overlay_item, new_path)
                    differences.update(nested_diffs)
        
        else:
            # Compare primitive values
            if base != overlay:
                differences[path] = overlay
        
        return differences
    
    def _get_nested_value(self, obj: Dict[str, Any], path: str) -> Any:
        """Get nested value from object using dot notation."""
        if not path:
            return obj
        
        keys = path.split('.')
        current = obj
        
        try:
            for key in keys:
                # Handle array notation like containers[0]
                if '[' in key and ']' in key:
                    base_key = key.split('[')[0]
                    index = int(key.split('[')[1].split(']')[0])
                    
                    if base_key not in current or not isinstance(current[base_key], list):
                        return None
                    
                    if index >= len(current[base_key]):
                        return None
                    
                    current = current[base_key][index]
                else:
                    if key not in current:
                        return None
                    current = current[key]
            
            return current
            
        except (KeyError, IndexError, ValueError, TypeError):
            return None
    
    def _extract_resource_parameters(self, resource: Dict[str, Any], resource_key: str) -> Dict[str, Any]:
        """Extract parameterizable values from a resource."""
        parameters = {}
        
        # Common parameterizable fields
        param_fields = {
            'metadata.namespace': 'namespace',
            'spec.replicas': 'replicaCount',
            'spec.template.spec.containers[0].image': 'image.repository',
            'spec.type': 'service.type',
            'spec.ports[0].port': 'service.port',
        }
        
        for field_path, param_name in param_fields.items():
            value = self._get_nested_value(resource, field_path)
            if value is not None:
                parameters[f"{resource_key}.{param_name}"] = value
        
        return parameters
    
    def _identify_parameterizable_paths(self) -> None:
        """Identify paths that vary across overlays and should be parameterized."""
        # Count how many overlays have differences for each path
        path_counts = defaultdict(int)
        path_values = defaultdict(set)
        
        for overlay_name, overlay_diffs in self.differences.items():
            for path, value in overlay_diffs.items():
                # Extract the field path (remove resource key prefix)
                if '.' in path:
                    field_path = '.'.join(path.split('.')[1:])  # Remove resource key
                    path_counts[field_path] += 1
                    path_values[field_path].add(str(value))  # Convert to string for set storage
        
        # Paths that vary in multiple overlays are good candidates for parameterization
        for field_path, count in path_counts.items():
            if count >= 2 or len(path_values[field_path]) >= 2:
                self.parameterizable_paths.add(field_path)
    
    def get_parameterizable_differences(self) -> Dict[str, Dict[str, Any]]:
        """Get differences that should be parameterized."""
        parameterized_diffs = {}
        
        for overlay_name, overlay_diffs in self.differences.items():
            overlay_params = {}
            
            for path, value in overlay_diffs.items():
                # Extract field path
                path_parts = path.split('.')
                if len(path_parts) > 1:
                    field_path = '.'.join(path_parts[1:])
                    
                    # Only include if it's a parameterizable path
                    if field_path in self.parameterizable_paths:
                        # Convert to values.yaml style path
                        param_path = self._convert_to_values_path(field_path, path_parts[0])
                        if param_path:
                            overlay_params[param_path] = value
            
            if overlay_params:
                parameterized_diffs[overlay_name] = overlay_params
        
        return parameterized_diffs
    
    def _convert_to_values_path(self, field_path: str, resource_key: str) -> Optional[str]:
        """Convert resource field path to values.yaml path."""
        # Mapping from resource field paths to values.yaml paths
        field_mappings = {
            'spec.replicas': 'replicaCount',
            'spec.template.spec.containers[0].image': 'image.repository',
            'spec.template.spec.containers[0].resources': 'resources',
            'spec.type': 'service.type',
            'spec.ports[0].port': 'service.port',
            'spec.ports[0].targetPort': 'service.targetPort',
            'metadata.namespace': 'namespace',
            'metadata.annotations': 'podAnnotations',
            'data': 'configMap.data' if 'ConfigMap' in resource_key else 'secret.data',
        }
        
        # Check for exact matches first
        if field_path in field_mappings:
            return field_mappings[field_path]
        
        # Handle partial matches for complex paths
        for pattern, values_path in field_mappings.items():
            if field_path.startswith(pattern.split('[')[0]):  # Handle array notation
                return values_path
        
        # For unmapped paths, create a generic path
        sanitized_path = field_path.replace('[0]', '').replace('.', '_')
        return f"custom.{sanitized_path}"
    
    def get_analysis_summary(self) -> Dict[str, Any]:
        """Get a summary of the analysis results."""
        return {
            'overlays_analyzed': len([k for k in self.resources_by_overlay.keys() if k != 'base']),
            'total_differences': sum(len(diffs) for diffs in self.differences.values()),
            'parameterizable_paths': list(self.parameterizable_paths),
            'differences_by_overlay': {
                overlay: len(diffs) for overlay, diffs in self.differences.items()
            }
        }
