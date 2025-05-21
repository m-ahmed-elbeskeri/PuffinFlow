"""Registry module for loading and managing integrations and actions."""

import os
import yaml
import re
import importlib.util
import sys
from pathlib import Path

class Registry:
    """
    Registry class for loading and managing integration definitions.
    """
    
    def __init__(self):
        self.integrations = {}
        self.modules = {}
        self.action_implementations = {}  # Maps action_name to (module, function)
        
        # Add explicit mapping for special cases to handle Python keywords
        self._initialize_special_mappings()
    
    def _initialize_special_mappings(self):
        """Initialize special mappings for Python keywords and other edge cases."""
        # Handle Python keywords that can't be used as function names
        self.action_implementations.update({
            "control.if": ("control", "if_node"),
            "control.while": ("control", "while_loop"),
            "control.try": ("control", "try_catch")
        })
        
        # Add any other special cases here
    
    def load_integrations(self, integrations_dir="integrations"):
        """
        Scan the integrations directory and load all manifest.yaml files.
        
        Args:
            integrations_dir: Path to the integrations directory
        """
        base_path = Path(integrations_dir)
        
        # Check if directory exists
        if not base_path.exists():
            print(f"Warning: Integrations directory '{integrations_dir}' not found")
            return
        
        # Scan all subdirectories in the integrations folder
        for integration_dir in base_path.iterdir():
            if integration_dir.is_dir():
                manifest_path = integration_dir / "manifest.yaml"
                
                if manifest_path.exists():
                    try:
                        with open(manifest_path, 'r') as f:
                            manifest = yaml.safe_load(f)
                            
                        # Store the integration by name
                        integration_name = manifest.get('name')
                        if integration_name:
                            # Load module information
                            modules_list = manifest.get('modules', [])
                            
                            # Add the modules list if not present
                            if not modules_list:
                                modules_list = self._discover_modules(integration_dir)
                                manifest['modules'] = modules_list
                            
                            # Load the modules
                            self._load_modules(integration_dir, integration_name, modules_list)
                            
                            # Register action implementations
                            self._register_action_implementations(integration_name, manifest)
                            
                            # Store the manifest
                            self.integrations[integration_name] = manifest
                            print(f"Loaded integration: {integration_name}")
                    except Exception as e:
                        print(f"Error loading integration from {manifest_path}: {str(e)}")
    
    def _discover_modules(self, integration_dir):
        """
        Discover Python modules in an integration directory.
        
        Args:
            integration_dir: Path to the integration directory
            
        Returns:
            List of module names (without .py extension)
        """
        modules = []
        for py_file in integration_dir.glob("*.py"):
            modules.append(py_file.stem)
        return modules
    
    def _load_modules(self, integration_dir, integration_name, modules_list=None):
        """
        Load Python modules for an integration.
        
        Args:
            integration_dir: Path to the integration directory
            integration_name: Name of the integration
            modules_list: Optional list of module names to load
        """
        # Look for Python files
        loaded_modules = []
        
        # If no modules list is provided, load all .py files
        if not modules_list:
            py_files = list(integration_dir.glob("*.py"))
        else:
            # Load only the specified modules
            py_files = [integration_dir / f"{module}.py" for module in modules_list]
            py_files = [f for f in py_files if f.exists()]
        
        for py_file in py_files:
            module_name = py_file.stem
            
            try:
                # Load the module
                spec = importlib.util.spec_from_file_location(
                    f"integrations.{integration_name}.{module_name}", 
                    py_file
                )
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)
                
                # Store the module reference
                if integration_name not in self.modules:
                    self.modules[integration_name] = {}
                
                self.modules[integration_name][module_name] = module
                loaded_modules.append(module_name)
                print(f"Loaded module: {integration_name}.{module_name}")
                
            except Exception as e:
                print(f"Error loading module {module_name}: {str(e)}")
        
        return loaded_modules
    
    def _register_action_implementations(self, integration_name, manifest):
        """
        Register the implementation mapping for each action.
        
        Args:
            integration_name: Name of the integration
            manifest: Integration manifest
        """
        actions = manifest.get('actions', {})
        
        for action_name, action_def in actions.items():
            full_action_name = f"{integration_name}.{action_name}"
            
            # Skip if we already have a special mapping for this action
            if full_action_name in self.action_implementations:
                continue
                
            # Check if implementation is specified in the manifest
            implementation = action_def.get('implementation')
            if implementation:
                # Parse implementation string (e.g., "add.add" -> module "add", function "add")
                if '.' in implementation:
                    module_name, function_name = implementation.split('.', 1)
                else:
                    # Default to same name for both
                    module_name = implementation
                    function_name = action_name
                
                # Store the implementation mapping
                self.action_implementations[full_action_name] = (module_name, function_name)
            else:
                # Use heuristics to find implementation
                if integration_name in self.modules:
                    # Try to find a module with the same name as the action
                    if action_name in self.modules[integration_name]:
                        module_name = action_name
                        function_name = action_name
                    # Try to find a module that has a function with this name
                    else:
                        found = False
                        for module_name, module in self.modules[integration_name].items():
                            if hasattr(module, action_name):
                                function_name = action_name
                                found = True
                                break
                        
                        if not found:
                            # Default to using the integration name as module
                            module_name = integration_name
                            function_name = action_name
                    
                    # Store the implementation mapping
                    self.action_implementations[full_action_name] = (module_name, function_name)
    
    def get_action(self, action_name):
        """
        Get an action definition by its fully qualified name.
        
        Args:
            action_name: Fully qualified action name (integration.action)
            
        Returns:
            Tuple of (action_def, integration_name, action_short_name) or (None, None, None)
        """
        if '.' in action_name:
            integration_name, action_short_name = action_name.split('.', 1)
            
            if integration_name in self.integrations:
                actions = self.integrations[integration_name].get('actions', {})
                action_def = actions.get(action_short_name)
                if action_def:
                    return action_def, integration_name, action_short_name
                
                # Special case for actions that are aliased
                # Check special mappings for Python keywords
                if action_name in self.action_implementations:
                    # For if/while/try, check the actual function name
                    if action_short_name in ['if', 'while', 'try']:
                        real_action = None
                        if action_short_name == 'if':
                            real_action = 'if_node'
                        elif action_short_name == 'while':
                            real_action = 'while_loop'
                        elif action_short_name == 'try':
                            real_action = 'try_catch'
                        
                        if real_action:
                            action_def = actions.get(real_action)
                            if action_def:
                                return action_def, integration_name, real_action
        
        # Special case for __prompt__.ask which might be in prompts integration
        if action_name == "__prompt__.ask" and "prompts" in self.integrations:
            actions = self.integrations["prompts"].get('actions', {})
            action_def = actions.get("ask")
            if action_def:
                return action_def, "prompts", "ask"
        
        return None, None, None
    
    def get_module_for_action(self, action_name):
        """
        Get the module name that contains the implementation for an action.
        
        Args:
            action_name: Fully qualified action name (integration.action)
            
        Returns:
            Tuple of (integration_name, module_name) or (None, None) if not found
        """
        # First, check the implementation mapping
        if action_name in self.action_implementations:
            module_name, _ = self.action_implementations[action_name]
            if '.' in action_name:
                integration_name, _ = action_name.split('.', 1)
                return integration_name, module_name
        
        # If not in mapping, use traditional approach
        if '.' not in action_name:
            return None, None
            
        integration_name, action_short_name = action_name.split('.', 1)
            
        # Special case for __prompt__.ask
        if integration_name == "__prompt__":
            return "prompts", "ask"
            
        # If we don't have action definition, try to find the module directly
        if integration_name in self.modules:
            # Try to find the module that has the function
            for module_name, module in self.modules[integration_name].items():
                if hasattr(module, action_short_name):
                    return integration_name, module_name
                    
        # If the action doesn't match a loaded module, guess based on naming conventions
        if '_' in action_short_name:
            # Try to guess module name from action prefix (e.g., "math_add" -> "math" module)
            potential_module = action_short_name.split('_')[0]
            if (integration_name in self.modules and 
                potential_module in self.modules[integration_name]):
                return integration_name, potential_module
                
        # Last resort: check if we have the integration and return its primary module
        if integration_name in self.integrations and 'primary_module' in self.integrations[integration_name]:
            return integration_name, self.integrations[integration_name]['primary_module']
            
        # Control is a special case with known module name
        if integration_name == 'control':
            return 'control', 'control'
            
        # We don't have enough information
        return integration_name, integration_name
    
    def execute_action(self, action_name, **kwargs):
        """
        Execute an action by its fully qualified name.
        
        Args:
            action_name: Fully qualified action name (integration.action)
            **kwargs: Arguments to pass to the action
            
        Returns:
            Result of the action execution
        
        Raises:
            ValueError: If the action cannot be found or executed
        """
        # Check if we have a direct implementation mapping
        if action_name in self.action_implementations:
            module_name, function_name = self.action_implementations[action_name]
            integration_name = action_name.split('.', 1)[0]
            
            if integration_name in self.modules and module_name in self.modules[integration_name]:
                module = self.modules[integration_name][module_name]
                if hasattr(module, function_name):
                    function = getattr(module, function_name)
                    
                    # Process template variables in kwargs if needed
                    processed_kwargs = self._process_template_vars(kwargs)
                    
                    # Execute the function
                    return function(**processed_kwargs)
        
        # Fallback to traditional approach
        action_def, integration_name, action_short_name = self.get_action(action_name)
        
        if not integration_name or not action_short_name:
            raise ValueError(f"Action '{action_name}' not found in registry")
        
        # Get the module
        if integration_name not in self.modules:
            raise ValueError(f"No modules loaded for integration '{integration_name}'")
        
        # Process template variables in kwargs if needed
        processed_kwargs = self._process_template_vars(kwargs)
        
        # Find the function
        for module_name, module in self.modules[integration_name].items():
            if hasattr(module, action_short_name):
                function = getattr(module, action_short_name)
                # Execute the function
                return function(**processed_kwargs)
        
        raise ValueError(f"Function '{action_short_name}' not found in integration '{integration_name}'")
    
    def _process_template_vars(self, kwargs):
        """
        Process template variables in kwargs.
        Handles both {{var}} and {var} formats in strings.
        
        Args:
            kwargs: Original kwargs dictionary
            
        Returns:
            Processed kwargs with template variables normalized
        """
        processed = {}
        
        for key, value in kwargs.items():
            if isinstance(value, str):
                # Convert double braces to single braces if present
                if '{{' in value:
                    value = value.replace('{{', '{').replace('}}', '}')
                processed[key] = value
            else:
                processed[key] = value
                
        return processed
    
    def get_all_actions(self):
        """
        Get all actions from all integrations.
        
        Returns:
            Dictionary of all actions with fully qualified names
        """
        all_actions = {}
        
        for integration_name, integration_data in self.integrations.items():
            actions = integration_data.get('actions', {})
            
            for action_name, action_data in actions.items():
                # Use fully qualified name
                qualified_name = f"{integration_name}.{action_name}"
                all_actions[qualified_name] = action_data
        
        return all_actions
    
    def to_json(self):
        """
        Convert the registry to a JSON-serializable object.
        """
        return self.integrations