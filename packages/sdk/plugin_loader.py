# sdk/plugin_loader.py

"""Plugin loader module for FlowForge plugins."""

import os
import sys
import yaml
import json
import importlib.util
from pathlib import Path
from typing import Dict, Any, List, Optional

class PluginLoadError(Exception):
    """Exception raised when a plugin cannot be loaded."""
    pass

def load_plugins(path: str = "./integrations") -> Dict[str, Any]:
    """Load all plugins from the specified directory."""
    plugins_dir = Path(path).resolve()
    if not plugins_dir.exists():
        raise PluginLoadError(f"Plugins directory not found: {plugins_dir}")
    
    plugin_registry = {}
    errors = []
    
    # Scan all subdirectories in the plugins folder
    for plugin_dir in plugins_dir.iterdir():
        if not plugin_dir.is_dir():
            continue
            
        plugin_name = plugin_dir.name
        
        try:
            # Look for manifest.yaml
            manifest_path = plugin_dir / "manifest.yaml"
            if not manifest_path.exists():
                errors.append(f"Plugin '{plugin_name}' missing manifest.yaml")
                continue
                
            # Load manifest
            with open(manifest_path, 'r') as f:
                manifest = yaml.safe_load(f)
            
            # Check required fields
            if 'name' not in manifest:
                errors.append(f"Plugin '{plugin_name}' manifest missing 'name' field")
                continue
            
            # Load schema.json if exists
            schema_path = plugin_dir / "schema.json"
            schema = None
            if schema_path.exists():
                with open(schema_path, 'r') as f:
                    schema = json.load(f)
            
            # Find main module (main.py or specified in manifest)
            main_module_path = None
            if os.path.exists(plugin_dir / "main.py"):
                main_module_path = plugin_dir / "main.py"
            
            # Load the main module
            spec = importlib.util.spec_from_file_location(
                f"flowforge_plugins.{plugin_name}", 
                main_module_path
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            
            # Create plugin registry entry
            plugin_info = {
                'name': manifest['name'],
                'version': manifest.get('version', '0.1.0'),
                'description': manifest.get('description', ''),
                'manifest': manifest,
                'schema': schema,
                'module': module,
                'path': plugin_dir,
                'actions': {}
            }
            
            # Register actions from manifest
            for action_name, action_def in manifest.get('actions', {}).items():
                implementation = action_def.get('implementation')
                
                if implementation and '.' in implementation:
                    module_name, func_name = implementation.split('.', 1)
                    
                    # Import the implementation module if needed
                    if module_name != 'main':
                        impl_module_path = plugin_dir / f"{module_name}.py"
                        if impl_module_path.exists():
                            impl_spec = importlib.util.spec_from_file_location(
                                f"flowforge_plugins.{plugin_name}.{module_name}", 
                                impl_module_path
                            )
                            impl_module = importlib.util.module_from_spec(impl_spec)
                            sys.modules[impl_spec.name] = impl_module
                            impl_spec.loader.exec_module(impl_module)
                            
                            # Register the function
                            if hasattr(impl_module, func_name):
                                plugin_info['actions'][action_name] = {
                                    'definition': action_def,
                                    'module': impl_module,
                                    'function': getattr(impl_module, func_name)
                                }
                    else:
                        # Check main module
                        if hasattr(module, func_name):
                            plugin_info['actions'][action_name] = {
                                'definition': action_def,
                                'module': module,
                                'function': getattr(module, func_name)
                            }
                
                elif hasattr(module, action_name):
                    # Default to function with same name as the action
                    plugin_info['actions'][action_name] = {
                        'definition': action_def,
                        'module': module,
                        'function': getattr(module, action_name)
                    }
            
            # Add plugin to registry
            plugin_registry[plugin_name] = plugin_info
            print(f"Loaded plugin: {plugin_name} v{plugin_info['version']}")
            
        except Exception as e:
            errors.append(f"Error loading plugin '{plugin_name}': {str(e)}")
    
    if errors:
        print(f"Encountered {len(errors)} errors while loading plugins:")
        for error in errors:
            print(f"  - {error}")
    
    return plugin_registry