"""
Kustomize Parser Module

Handles parsing and analysis of kustomization.yaml files and associated resources.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
import logging

logger = logging.getLogger(__name__)


class KustomizeParser:
    """Parser for Kustomize configuration files and resources."""
    
    def __init__(self, kustomize_dir: Union[str, Path]):
        """
        Initialize the Kustomize parser.
        
        Args:
            kustomize_dir: Path to directory containing kustomization.yaml
        """
        self.kustomize_dir = Path(kustomize_dir)
        self.kustomization_file = None
        self.kustomization_data = {}
        self.resources = []
        self.patches = []
        self.config_maps = []
        self.secrets = []
        
        # Find kustomization file
        for filename in ['kustomization.yaml', 'kustomization.yml', 'Kustomization']:
            potential_file = self.kustomize_dir / filename
            if potential_file.exists():
                self.kustomization_file = potential_file
                break
        
        if not self.kustomization_file:
            raise FileNotFoundError(f"No kustomization file found in {kustomize_dir}")
    
    def parse(self) -> Dict[str, Any]:
        """
        Parse the kustomization file and all associated resources.
        
        Returns:
            Dictionary containing parsed kustomization data and resources
        """
        logger.info(f"Parsing kustomization file: {self.kustomization_file}")
        
        # Parse main kustomization file
        with open(self.kustomization_file, 'r') as f:
            self.kustomization_data = yaml.safe_load(f)
        
        # Parse resources
        self._parse_resources()
        
        # Parse patches
        self._parse_patches()
        
        # Parse config generators
        self._parse_config_generators()
        
        return {
            'kustomization': self.kustomization_data,
            'resources': self.resources,
            'patches': self.patches,
            'configMaps': self.config_maps,
            'secrets': self.secrets,
            'namespace': self.kustomization_data.get('namespace'),
            'namePrefix': self.kustomization_data.get('namePrefix', ''),
            'nameSuffix': self.kustomization_data.get('nameSuffix', ''),
            'commonLabels': self.kustomization_data.get('commonLabels', {}),
            'commonAnnotations': self.kustomization_data.get('commonAnnotations', {}),
            'images': self.kustomization_data.get('images', []),
            'replicas': self.kustomization_data.get('replicas', [])
        }
    
    def _parse_resources(self):
        """Parse resource files referenced in kustomization."""
        resources = self.kustomization_data.get('resources', [])
        
        for resource_path in resources:
            full_path = self.kustomize_dir / resource_path
            
            if full_path.is_dir():
                # If resource is a directory, look for kustomization inside
                try:
                    sub_parser = KustomizeParser(full_path)
                    sub_data = sub_parser.parse()
                    self.resources.extend(sub_data['resources'])
                except FileNotFoundError:
                    logger.warning(f"No kustomization found in directory: {full_path}")
            elif full_path.exists():
                # Parse YAML file
                try:
                    with open(full_path, 'r') as f:
                        # Handle multi-document YAML files
                        docs = list(yaml.safe_load_all(f))
                        for doc in docs:
                            if doc:  # Skip empty documents
                                doc['_source_file'] = str(resource_path)
                                self.resources.append(doc)
                except Exception as e:
                    logger.error(f"Error parsing resource {resource_path}: {e}")
            else:
                logger.warning(f"Resource file not found: {full_path}")
    
    def _parse_patches(self):
        """Parse patch files and inline patches."""
        # Strategic merge patches
        patches_strategic_merge = self.kustomization_data.get('patchesStrategicMerge', [])
        for patch_path in patches_strategic_merge:
            self._load_patch_file(patch_path, 'strategic-merge')
        
        # JSON6902 patches
        patches_json6902 = self.kustomization_data.get('patchesJson6902', [])
        for patch_config in patches_json6902:
            if 'path' in patch_config:
                self._load_patch_file(patch_config['path'], 'json6902', patch_config)
            else:
                # Inline patch
                self.patches.append({
                    'type': 'json6902',
                    'target': patch_config.get('target', {}),
                    'patch': patch_config.get('patch', []),
                    'inline': True
                })
        
        # Generic patches (newer format)
        patches = self.kustomization_data.get('patches', [])
        for patch_config in patches:
            if 'path' in patch_config:
                self._load_patch_file(patch_config['path'], 'generic', patch_config)
            else:
                # Inline patch
                self.patches.append({
                    'type': 'generic',
                    'target': patch_config.get('target', {}),
                    'patch': patch_config.get('patch', ''),
                    'inline': True
                })
    
    def _load_patch_file(self, patch_path: str, patch_type: str, config: Optional[Dict] = None):
        """Load a patch file from disk."""
        full_path = self.kustomize_dir / patch_path
        
        if full_path.exists():
            try:
                with open(full_path, 'r') as f:
                    if patch_type == 'json6902':
                        patch_content = yaml.safe_load(f)
                    else:
                        patch_content = f.read()
                
                patch_data = {
                    'type': patch_type,
                    'path': patch_path,
                    'content': patch_content,
                    'inline': False
                }
                
                if config:
                    patch_data.update(config)
                
                self.patches.append(patch_data)
            except Exception as e:
                logger.error(f"Error loading patch file {patch_path}: {e}")
        else:
            logger.warning(f"Patch file not found: {full_path}")
    
    def _parse_config_generators(self):
        """Parse ConfigMap and Secret generators."""
        # ConfigMap generators
        config_map_generator = self.kustomization_data.get('configMapGenerator', [])
        for cm_config in config_map_generator:
            cm_data = {
                'name': cm_config.get('name'),
                'type': 'configMap',
                'files': cm_config.get('files', []),
                'literals': cm_config.get('literals', []),
                'envs': cm_config.get('envs', []),
                'options': cm_config.get('options', {})
            }
            
            # Load file contents
            for file_spec in cm_data['files']:
                if '=' in file_spec:
                    key, file_path = file_spec.split('=', 1)
                else:
                    key = os.path.basename(file_spec)
                    file_path = file_spec
                
                full_path = self.kustomize_dir / file_path
                if full_path.exists():
                    try:
                        with open(full_path, 'r') as f:
                            cm_data[f'file_{key}'] = f.read()
                    except Exception as e:
                        logger.error(f"Error reading file {file_path}: {e}")
            
            self.config_maps.append(cm_data)
        
        # Secret generators
        secret_generator = self.kustomization_data.get('secretGenerator', [])
        for secret_config in secret_generator:
            secret_data = {
                'name': secret_config.get('name'),
                'type': 'secret',
                'files': secret_config.get('files', []),
                'literals': secret_config.get('literals', []),
                'envs': secret_config.get('envs', []),
                'options': secret_config.get('options', {}),
                'secretType': secret_config.get('type', 'Opaque')
            }
            
            # Load file contents (similar to ConfigMap)
            for file_spec in secret_data['files']:
                if '=' in file_spec:
                    key, file_path = file_spec.split('=', 1)
                else:
                    key = os.path.basename(file_spec)
                    file_path = file_spec
                
                full_path = self.kustomize_dir / file_path
                if full_path.exists():
                    try:
                        with open(full_path, 'r') as f:
                            secret_data[f'file_{key}'] = f.read()
                    except Exception as e:
                        logger.error(f"Error reading file {file_path}: {e}")
            
            self.secrets.append(secret_data)
    
    def get_all_resources(self) -> List[Dict[str, Any]]:
        """Get all resources including generated ConfigMaps and Secrets."""
        all_resources = self.resources.copy()
        
        # Add generated ConfigMaps
        for cm in self.config_maps:
            all_resources.append(self._generate_config_map_resource(cm))
        
        # Add generated Secrets
        for secret in self.secrets:
            all_resources.append(self._generate_secret_resource(secret))
        
        return all_resources
    
    def _generate_config_map_resource(self, cm_config: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a ConfigMap resource from generator config."""
        cm_resource = {
            'apiVersion': 'v1',
            'kind': 'ConfigMap',
            'metadata': {
                'name': cm_config['name']
            },
            'data': {}
        }
        
        # Add literal data
        for literal in cm_config.get('literals', []):
            if '=' in literal:
                key, value = literal.split('=', 1)
                cm_resource['data'][key] = value
        
        # Add file data
        for key, value in cm_config.items():
            if key.startswith('file_'):
                data_key = key[5:]  # Remove 'file_' prefix
                cm_resource['data'][data_key] = value
        
        return cm_resource
    
    def _generate_secret_resource(self, secret_config: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a Secret resource from generator config."""
        secret_resource = {
            'apiVersion': 'v1',
            'kind': 'Secret',
            'metadata': {
                'name': secret_config['name']
            },
            'type': secret_config.get('secretType', 'Opaque'),
            'data': {}
        }
        
        # Add literal data
        for literal in secret_config.get('literals', []):
            if '=' in literal:
                key, value = literal.split('=', 1)
                # Note: In real implementation, you'd want to base64 encode these
                secret_resource['data'][key] = value
        
        # Add file data
        for key, value in secret_config.items():
            if key.startswith('file_'):
                data_key = key[5:]  # Remove 'file_' prefix
                secret_resource['data'][data_key] = value
        
        return secret_resource
