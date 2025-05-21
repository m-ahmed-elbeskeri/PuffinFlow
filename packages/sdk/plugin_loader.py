# sdk/plugin_loader.py

"""Plugin loader module for FlowForge plugins with improved namespace isolation."""

import os
import sys
import yaml
import json
import importlib.util
import traceback
from pathlib import Path
from typing import Dict, Any, List, Optional

class PluginLoadError(Exception):
    """Exception raised when a plugin cannot be loaded."""
    pass

def load_plugins(path: str = "./integrations", auto_install_deps: bool = False) -> Dict[str, Any]:
    """
    Load all plugins from the specified directory with namespace isolation.
    
    Args:
        path: Path to the plugins directory
        auto_install_deps: Whether to automatically install missing dependencies
        
    Returns:
        Dictionary of loaded plugins
    """
    plugins_dir = Path(path).resolve()
    if not plugins_dir.exists():
        print(f"WARNING: Plugins directory not found: {plugins_dir}")
        return {}
    
    plugin_registry = {}
    errors = []
    missing_deps = set()

    # ─────────────────────────────────────────────────────────────────────────────
    # Set-up a dedicated namespace package to isolate all plugins
    # ─────────────────────────────────────────────────────────────────────────────
    PARENT_NS = "flowforge_integrations"
    if PARENT_NS not in sys.modules:
        import types
        ns_pkg = types.ModuleType(PARENT_NS)
        ns_pkg.__path__ = []            # PEP-420 namespace pkg
        sys.modules[PARENT_NS] = ns_pkg
    
    # Scan all subdirectories in the plugins folder
    for plugin_dir in plugins_dir.iterdir():
        if not plugin_dir.is_dir():
            continue
            
        plugin_name = plugin_dir.name
        
        # Check for requirements.txt and install if requested
        req_file = plugin_dir / "requirements.txt"
        if auto_install_deps and req_file.exists():
            try:
                print(f"Installing dependencies for plugin '{plugin_name}'...")
                import subprocess
                subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(req_file)])
                print(f"Dependencies installed successfully for '{plugin_name}'")
            except Exception as e:
                print(f"Warning: Failed to install dependencies for plugin '{plugin_name}': {e}")
                missing_deps.add(plugin_name)
        
        # Ensure plugin directory itself is on sys.path **after** our namespace
        if str(plugin_dir) not in sys.path:
            sys.path.append(str(plugin_dir))
                
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
                try:
                    with open(schema_path, 'r') as f:
                        schema = json.load(f)
                except Exception as e:
                    print(f"Warning: Could not load schema for plugin '{plugin_name}': {e}")
            
            # Find main module (main.py or specified in manifest)
            main_module_path = plugin_dir / "main.py"
            if not main_module_path.exists():
                # If main.py doesn't exist, try using a module named after the plugin
                main_module_path = plugin_dir / f"{plugin_name}.py"
                if not main_module_path.exists():
                    # If that doesn't exist either, try to find first module from manifest
                    modules = manifest.get('modules', [])
                    if modules and len(modules) > 0:
                        main_module_path = plugin_dir / f"{modules[0]}.py"
                        if not main_module_path.exists():
                            errors.append(f"Error loading plugin '{plugin_name}': Could not find valid module file in {plugin_dir}")
                            continue
                    else:
                        errors.append(f"Error loading plugin '{plugin_name}': No main.py or {plugin_name}.py found in {plugin_dir}")
                        continue
            
            # Load the main module with better error handling
            try:
                # Load the plugin as flowforge_integrations.<plugin_name>
                module_name = f"{PARENT_NS}.{plugin_name}"
                spec = importlib.util.spec_from_file_location(
                    module_name,
                    main_module_path,
                    submodule_search_locations=[str(plugin_dir)]  # makes it a package
                )
                
                if spec is None or spec.loader is None:
                    errors.append(f"Error loading plugin '{plugin_name}': Could not create valid spec for {main_module_path}")
                    continue
                    
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)
            except Exception as e:
                errors.append(f"Error loading plugin '{plugin_name}': Module loading failed: {str(e)}")
                continue
            
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
            action_count = 0
            for action_name, action_def in manifest.get('actions', {}).items():
                implementation = action_def.get('implementation')
                
                if not implementation:
                    print(f"Warning: Action '{action_name}' in plugin '{plugin_name}' has no implementation specified")
                    continue
                
                try:
                    # Parse implementation
                    if '.' in implementation:
                        module_name, func_name = implementation.split('.', 1)
                    else:
                        module_name = implementation
                        func_name = action_name
                    
                    # Import the implementation module if needed
                    impl_module = None
                    if module_name != 'main':
                        impl_module_path = plugin_dir / f"{module_name}.py"
                        if not impl_module_path.exists():
                            print(f"Warning: Implementation module '{module_name}' for action '{action_name}' not found in plugin '{plugin_name}'")
                            continue
                            
                        impl_spec = None
                        try:
                            # Use proper namespaced module name
                            impl_module_fullname = f"{PARENT_NS}.{plugin_name}.{module_name}"
                            impl_spec = importlib.util.spec_from_file_location(
                                impl_module_fullname, 
                                impl_module_path
                            )
                        except Exception as e:
                            print(f"Warning: Failed to create spec for module '{module_name}' in plugin '{plugin_name}': {e}")
                            continue
                            
                        if not impl_spec or not impl_spec.loader:
                            print(f"Warning: Invalid spec or missing loader for module '{module_name}' in plugin '{plugin_name}'")
                            continue
                            
                        try:
                            impl_module = importlib.util.module_from_spec(impl_spec)
                            sys.modules[impl_spec.name] = impl_module
                            impl_spec.loader.exec_module(impl_module)
                        except Exception as e:
                            print(f"Warning: Failed to load module '{module_name}' in plugin '{plugin_name}': {e}")
                            continue
                    else:
                        # Use main module (top-level package already loaded above)
                        impl_module = module
                    
                    # Register the function
                    if impl_module and hasattr(impl_module, func_name):
                        plugin_info['actions'][action_name] = {
                            'definition': action_def,
                            'module': impl_module,
                            'function': getattr(impl_module, func_name)
                        }
                        action_count += 1
                    else:
                        print(f"Warning: Function '{func_name}' not found in module '{module_name}' for plugin '{plugin_name}'")
                except Exception as e:
                    print(f"Warning: Failed to register action '{action_name}' in plugin '{plugin_name}': {e}")
            
            # Add plugin to registry if at least one action was loaded
            if action_count > 0 or len(manifest.get('actions', {})) == 0:
                plugin_registry[plugin_name] = plugin_info
                print(f"Loaded plugin: {plugin_name} v{plugin_info['version']} with {action_count} actions")
            else:
                errors.append(f"Plugin '{plugin_name}' has no valid actions")
            
        except Exception as e:
            errors.append(f"Error loading plugin '{plugin_name}': {str(e)}")
            if auto_install_deps:  # Only show traceback when in debug mode or auto-installing deps
                traceback.print_exc()
    
    if errors:
        print(f"Encountered {len(errors)} errors while loading plugins:")
        for error in errors:
            print(f"  - {error}")
    
    if missing_deps and not auto_install_deps:
        print("\nMissing dependencies detected:")
        for plugin in missing_deps:
            print(f"  - {plugin}")
    
    return plugin_registry