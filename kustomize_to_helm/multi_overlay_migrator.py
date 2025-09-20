"""
Multi-Overlay Migrator Module

Handles migration of Kustomize base + overlays to Helm charts with parameterized values files.
"""

import os
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Union

from .kustomize_parser import KustomizeParser
from .helm_generator import HelmChartGenerator
from .template_converter import TemplateConverter
from .overlay_analyzer import OverlayAnalyzer

logger = logging.getLogger(__name__)


class MultiOverlayMigrator:
    """Migrates Kustomize base + overlays to Helm charts with parameterized values."""
    
    def __init__(self, 
                 base_dir: Union[str, Path],
                 overlays_dir: Union[str, Path], 
                 output_dir: Union[str, Path],
                 chart_name: Optional[str] = None,
                 dry_run: bool = False):
        """
        Initialize the multi-overlay migrator.
        
        Args:
            base_dir: Path to base Kustomize directory
            overlays_dir: Path to overlays directory containing overlay subdirectories
            output_dir: Directory where Helm chart will be created
            chart_name: Name for the Helm chart (defaults to base directory name)
            dry_run: If True, only analyze without creating files
        """
        self.base_dir = Path(base_dir)
        self.overlays_dir = Path(overlays_dir)
        self.output_dir = Path(output_dir)
        self.chart_name = chart_name or self.base_dir.name
        self.dry_run = dry_run
        
        # Initialize components
        self.base_parser = KustomizeParser(self.base_dir)
        self.overlay_parsers = {}
        self.overlay_analyzer = OverlayAnalyzer()
        self.generator = HelmChartGenerator(self.chart_name, self.output_dir)
        self.converter = TemplateConverter(self.chart_name)
        
        # Migration results
        self.base_data = {}
        self.overlay_data = {}
        self.overlay_names = []
        self.parameterized_values = {}
        self.migration_report = {
            'source_base_directory': str(self.base_dir),
            'source_overlays_directory': str(self.overlays_dir),
            'target_directory': str(self.output_dir / self.chart_name),
            'chart_name': self.chart_name,
            'overlays_processed': 0,
            'resources_migrated': 0,
            'values_files_generated': 0,
            'parameters_extracted': 0,
            'warnings': [],
            'errors': []
        }
    
    def migrate(self) -> Dict[str, Any]:
        """
        Perform the complete multi-overlay migration.
        
        Returns:
            Migration report with details about the conversion
        """
        logger.info(f"Starting multi-overlay migration for chart '{self.chart_name}'")
        
        try:
            # Step 1: Parse base configuration
            self._parse_base()
            
            # Step 2: Discover and parse overlays
            self._discover_and_parse_overlays()
            
            # Step 3: Analyze differences between overlays
            self._analyze_overlay_differences()
            
            # Step 4: Extract parameterized values
            self._extract_parameterized_values()
            
            # Step 5: Generate base Helm chart (if not dry run)
            if not self.dry_run:
                self._generate_base_helm_chart()
                
                # Step 6: Generate overlay-specific values files
                self._generate_overlay_values_files()
                
                logger.info(f"Multi-overlay migration completed successfully. Chart created at: {self.output_dir / self.chart_name}")
            else:
                logger.info("Dry run completed. No files were created.")
            
            self.migration_report['status'] = 'success'
            
        except Exception as e:
            logger.error(f"Multi-overlay migration failed: {e}")
            self.migration_report['status'] = 'failed'
            self.migration_report['errors'].append(str(e))
            raise
        
        return self.migration_report
    
    def _parse_base(self) -> None:
        """Parse the base Kustomize configuration."""
        logger.info("Parsing base Kustomize configuration...")
        
        try:
            self.base_data = self.base_parser.parse()
            self.migration_report['resources_migrated'] = len(self.base_data.get('resources', []))
            logger.info(f"Parsed base with {self.migration_report['resources_migrated']} resources")
            
        except Exception as e:
            error_msg = f"Failed to parse base configuration: {e}"
            logger.error(error_msg)
            self.migration_report['errors'].append(error_msg)
            raise
    
    def _discover_and_parse_overlays(self) -> None:
        """Discover overlay directories and parse each overlay."""
        logger.info("Discovering and parsing overlays...")
        
        # Find all overlay directories
        overlay_dirs = [d for d in self.overlays_dir.iterdir() 
                       if d.is_dir() and not d.name.startswith('.')]
        
        if not overlay_dirs:
            warning = f"No overlay directories found in {self.overlays_dir}"
            logger.warning(warning)
            self.migration_report['warnings'].append(warning)
            return
        
        self.overlay_names = [d.name for d in overlay_dirs]
        logger.info(f"Found overlays: {self.overlay_names}")
        
        # Parse each overlay
        for overlay_dir in overlay_dirs:
            overlay_name = overlay_dir.name
            
            try:
                # Create parser for this overlay
                overlay_parser = KustomizeParser(overlay_dir)
                self.overlay_parsers[overlay_name] = overlay_parser
                
                # Parse overlay data
                overlay_data = overlay_parser.parse()
                self.overlay_data[overlay_name] = overlay_data
                
                logger.info(f"Parsed overlay '{overlay_name}' with {len(overlay_data.get('resources', []))} resources")
                
            except Exception as e:
                error_msg = f"Failed to parse overlay '{overlay_name}': {e}"
                logger.error(error_msg)
                self.migration_report['errors'].append(error_msg)
        
        self.migration_report['overlays_processed'] = len(self.overlay_data)
    
    def _analyze_overlay_differences(self) -> None:
        """Analyze differences between overlays to identify parameters."""
        logger.info("Analyzing overlay differences...")
        
        # Get all resources from base and overlays
        all_resources = {
            'base': self.base_parser.get_all_resources()
        }
        
        for overlay_name in self.overlay_names:
            if overlay_name in self.overlay_data:
                parser = self.overlay_parsers[overlay_name]
                all_resources[overlay_name] = parser.get_all_resources()
        
        # Analyze differences
        self.overlay_analyzer.analyze_differences(all_resources)
        
        logger.info("Overlay analysis completed")
    
    def _extract_parameterized_values(self) -> None:
        """Extract parameterized values based on overlay differences."""
        logger.info("Extracting parameterized values...")
        
        # Start with base values
        base_values = self.converter.extract_parameterizable_values(
            self.base_parser.get_all_resources()
        )
        
        # Add base kustomization values
        base_kustomization = self.base_data.get('kustomization', {})
        base_values.update({
            'namePrefix': base_kustomization.get('namePrefix', ''),
            'nameSuffix': base_kustomization.get('nameSuffix', ''),
            'namespace': base_kustomization.get('namespace', ''),
            'commonLabels': base_kustomization.get('commonLabels', {}),
            'commonAnnotations': base_kustomization.get('commonAnnotations', {})
        })
        
        # Get differences from analyzer
        differences = self.overlay_analyzer.get_parameterizable_differences()
        
        # Create parameterized values for each overlay
        self.parameterized_values = {
            'base': base_values
        }
        
        for overlay_name in self.overlay_names:
            if overlay_name not in self.overlay_data:
                continue
                
            # Start with base values
            overlay_values = base_values.copy()
            
            # Apply overlay-specific kustomization values
            overlay_kustomization = self.overlay_data[overlay_name].get('kustomization', {})
            overlay_values.update({
                'namePrefix': overlay_kustomization.get('namePrefix', base_values.get('namePrefix', '')),
                'nameSuffix': overlay_kustomization.get('nameSuffix', base_values.get('nameSuffix', '')),
                'namespace': overlay_kustomization.get('namespace', base_values.get('namespace', '')),
                'commonLabels': {**base_values.get('commonLabels', {}), **overlay_kustomization.get('commonLabels', {})},
                'commonAnnotations': {**base_values.get('commonAnnotations', {}), **overlay_kustomization.get('commonAnnotations', {})}
            })
            
            # Apply differences identified by analyzer
            if overlay_name in differences:
                overlay_diffs = differences[overlay_name]
                self._apply_overlay_differences(overlay_values, overlay_diffs)
            
            # Extract values from overlay-specific resources
            overlay_resources = self.overlay_parsers[overlay_name].get_all_resources()
            overlay_specific_values = self.converter.extract_parameterizable_values(overlay_resources)
            
            # Merge overlay-specific values
            self._deep_merge_values(overlay_values, overlay_specific_values)
            
            self.parameterized_values[overlay_name] = overlay_values
        
        # Count total parameters
        all_params = set()
        for values in self.parameterized_values.values():
            all_params.update(self._flatten_dict_keys(values))
        
        self.migration_report['parameters_extracted'] = len(all_params)
        logger.info(f"Extracted {self.migration_report['parameters_extracted']} parameters")
    
    def _apply_overlay_differences(self, overlay_values: Dict[str, Any], differences: Dict[str, Any]) -> None:
        """Apply differences to overlay values."""
        for path, value in differences.items():
            self._set_nested_value(overlay_values, path, value)
    
    def _set_nested_value(self, obj: Dict[str, Any], path: str, value: Any) -> None:
        """Set a nested value in a dictionary using dot notation."""
        keys = path.split('.')
        current = obj
        
        # Navigate to the parent
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        # Set the value
        current[keys[-1]] = value
    
    def _deep_merge_values(self, base: Dict[str, Any], overlay: Dict[str, Any]) -> None:
        """Deep merge overlay values into base values."""
        for key, value in overlay.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge_values(base[key], value)
            else:
                base[key] = value
    
    def _flatten_dict_keys(self, d: Dict[str, Any], prefix: str = '') -> List[str]:
        """Flatten dictionary keys with dot notation."""
        keys = []
        for k, v in d.items():
            if prefix:
                key = f"{prefix}.{k}"
            else:
                key = k
            
            if isinstance(v, dict):
                keys.extend(self._flatten_dict_keys(v, key))
            else:
                keys.append(key)
        
        return keys
    
    def _generate_base_helm_chart(self) -> None:
        """Generate the base Helm chart using base configuration."""
        logger.info("Generating base Helm chart...")
        
        # Use base values as the default
        base_values = self.parameterized_values.get('base', {})
        self.generator.values = base_values
        
        # Generate chart using base data
        self.generator.generate_chart(self.base_data)
        
        logger.info("Base Helm chart generated")
    
    def _generate_overlay_values_files(self) -> None:
        """Generate values files for each overlay."""
        logger.info("Generating overlay-specific values files...")
        
        for overlay_name in self.overlay_names:
            if overlay_name not in self.parameterized_values:
                continue
            
            # Generate values file for this overlay
            values_file_name = f"values-{overlay_name}.yaml"
            values_file_path = self.generator.chart_dir / values_file_name
            
            overlay_values = self.parameterized_values[overlay_name]
            
            # Write values file with proper YAML formatting
            self._write_overlay_values_file(values_file_path, overlay_values, overlay_name)
            
            logger.info(f"Generated values file: {values_file_name}")
        
        self.migration_report['values_files_generated'] = len(self.overlay_names) + 1  # +1 for base values.yaml
    
    def _write_overlay_values_file(self, file_path: Path, values: Dict[str, Any], overlay_name: str) -> None:
        """Write overlay values file with proper formatting."""
        import yaml
        
        # Add header comment
        header_comment = f"""# Values file for overlay: {overlay_name}
# Generated by Kustomize to Helm migration framework
# 
# Usage:
#   helm install my-release ./chart -f values-{overlay_name}.yaml
#
"""
        
        # Process values to handle multiline strings properly
        processed_values = self._process_values_for_yaml(values)
        
        with open(file_path, 'w') as f:
            f.write(header_comment)
            yaml.dump(processed_values, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    
    def _process_values_for_yaml(self, values: Dict[str, Any]) -> Dict[str, Any]:
        """Process values to ensure proper YAML formatting for multi-line strings."""
        processed = {}
        
        for key, value in values.items():
            if isinstance(value, dict):
                processed[key] = self._process_values_for_yaml(value)
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
    
    def _write_yaml_with_literal_blocks(self, file_obj, data, indent=0):
        """Write YAML with proper literal block formatting for ConfigMap data."""
        # This method is deprecated - we now use yaml.dump directly in _write_overlay_values_file
        import yaml
        yaml.dump(data, file_obj, default_flow_style=False, allow_unicode=True, sort_keys=False)
