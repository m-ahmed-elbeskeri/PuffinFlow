"""Plugin SDK for FlowForge integrations."""

from typing import Dict, Any, List, Optional, Callable, Type
import os
import importlib.util
import sys
import yaml
import json
from pathlib import Path

class Plugin:
    """Base class for FlowForge plugins."""
    
    def __init__(self, name: str, path: str):
        self.name = name
        self.path = Path(path)
        self.manifest = {}
        self.schema = {}
        self.actions = {}
        
        # Load manifest and schema
        self._load_manifest()
        self._load_schema()
        
    def _load_manifest(self):
        """Load plugin manifest from manifest.yaml file."""
        manifest_path = self.path / "manifest.yaml"
        if manifest_path.exists():
            try:
                with open(manifest_path) as f:
                    self.manifest = yaml.safe_load(f)
            except Exception as e:
                print(f"Error loading manifest for plugin {self.name}: {e}")
                self.manifest = {}
                
    def _load_schema(self):
        """Load plugin schema from schema.json file."""
        schema_path = self.path / "schema.json"
        if schema_path.exists():
            try:
                with open(schema_path) as f:
                    self.schema = json.load(f)
            except Exception as e:
                print(f"Error loading schema for plugin {self.name}: {e}")
                self.schema = {}
    
    def load_actions(self):
        """Load actions from the plugin."""
        # Get actions from manifest
        actions = self.manifest.get("actions", {})
        
        # Load each action
        for action_id, action_info in actions.items():
            # Get implementation details
            implementation = action_info.get("implementation")
            if not implementation:
                continue
                
            # Parse module and function
            if "." in implementation:
                module_name, function_name = implementation.split(".", 1)
            else:
                module_name = implementation
                function_name = action_id
                
            # Import module
            try:
                module_path = self.path / f"{module_name}.py"
                spec = importlib.util.spec_from_file_location(
                    f"flowforge.integrations.{self.name}.{module_name}",
                    module_path
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[spec.name] = module
                    spec.loader.exec_module(module)
                    
                    # Get function
                    if hasattr(module, function_name):
                        self.actions[action_id] = {
                            "function": getattr(module, function_name),
                            "info": action_info
                        }
            except Exception as e:
                print(f"Error loading action {action_id} from plugin {self.name}: {e}")
    
    def execute_action(self, action_id: str, **kwargs):
        """Execute an action from the plugin."""
        if action_id not in self.actions:
            raise ValueError(f"Action {action_id} not found in plugin {self.name}")
            
        action = self.actions[action_id]
        return action["function"](**kwargs)