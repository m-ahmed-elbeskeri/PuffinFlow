"""Registry module for loading and managing integrations and actions."""

import os
import yaml
import re
import importlib.util
import sys
from pathlib import Path

from packages.sdk.plugin_loader import load_plugins  # Plugin system loader


class Registry:
    """
    Registry class for loading and managing integration definitions.
    """

    def __init__(self):
        self.integrations = {}
        self.modules = {}
        self.action_implementations = {}  # Maps action_name to (module_tag, function/callable)

        self._initialize_special_mappings()
        self._load_plugins_into_registry()

    def _initialize_special_mappings(self):
        """Initialize special mappings for Python keywords and other edge cases."""
        self.action_implementations.update({
            "control.if": ("control", "if_node"),
            "control.while": ("control", "while_loop"),
            "control.try": ("control", "try_catch")
        })

    def _load_plugins_into_registry(self, plugin_dir="integrations"):
        """
        Load all plugins and integrate them into the registry system.
        """
        try:
            plugins = load_plugins(plugin_dir)
        except Exception as e:
            print(f"Failed to load plugins: {e}")
            return

        for plugin_name, plugin_info in plugins.items():
            self.integrations[plugin_name] = {
                "actions": {
                    name: entry["definition"]
                    for name, entry in plugin_info["actions"].items()
                },
                "manifest": plugin_info["manifest"],
                "version": plugin_info["version"],
                "description": plugin_info["description"],
                "schema": plugin_info.get("schema")
            }

            for action_name, entry in plugin_info["actions"].items():
                fq_action = f"{plugin_name}.{action_name}"
                self.action_implementations[fq_action] = ("__plugin__", entry["function"])
            print(f"Registered plugin actions for: {plugin_name}")

    def load_integrations(self, integrations_dir="integrations"):
        base_path = Path(integrations_dir)
        if not base_path.exists():
            print(f"Warning: Integrations directory '{integrations_dir}' not found")
            return

        for integration_dir in base_path.iterdir():
            if integration_dir.is_dir():
                manifest_path = integration_dir / "manifest.yaml"
                if manifest_path.exists():
                    try:
                        with open(manifest_path, 'r') as f:
                            manifest = yaml.safe_load(f)

                        integration_name = manifest.get('name')
                        if integration_name:
                            modules_list = manifest.get('modules', [])
                            if not modules_list:
                                modules_list = self._discover_modules(integration_dir)
                                manifest['modules'] = modules_list

                            self._load_modules(integration_dir, integration_name, modules_list)
                            self._register_action_implementations(integration_name, manifest)

                            self.integrations[integration_name] = manifest
                            print(f"Loaded integration: {integration_name}")
                    except Exception as e:
                        print(f"Error loading integration from {manifest_path}: {str(e)}")

    def _discover_modules(self, integration_dir):
        modules = []
        for py_file in integration_dir.glob("*.py"):
            modules.append(py_file.stem)
        return modules

    def _load_modules(self, integration_dir, integration_name, modules_list=None):
        loaded_modules = []

        if not modules_list:
            py_files = list(integration_dir.glob("*.py"))
        else:
            py_files = [integration_dir / f"{module}.py" for module in modules_list]
            py_files = [f for f in py_files if f.exists()]

        for py_file in py_files:
            module_name = py_file.stem
            try:
                spec = importlib.util.spec_from_file_location(
                    f"integrations.{integration_name}.{module_name}",
                    py_file
                )
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)

                if integration_name not in self.modules:
                    self.modules[integration_name] = {}

                self.modules[integration_name][module_name] = module
                loaded_modules.append(module_name)
                print(f"Loaded module: {integration_name}.{module_name}")
            except Exception as e:
                print(f"Error loading module {module_name}: {str(e)}")

        return loaded_modules

    def _register_action_implementations(self, integration_name, manifest):
        actions = manifest.get('actions', {})

        for action_name, action_def in actions.items():
            full_action_name = f"{integration_name}.{action_name}"
            if full_action_name in self.action_implementations:
                continue

            implementation = action_def.get('implementation')
            if implementation:
                if '.' in implementation:
                    module_name, function_name = implementation.split('.', 1)
                else:
                    module_name = implementation
                    function_name = action_name
                self.action_implementations[full_action_name] = (module_name, function_name)
            else:
                if integration_name in self.modules:
                    if action_name in self.modules[integration_name]:
                        module_name = action_name
                        function_name = action_name
                    else:
                        found = False
                        for module_name, module in self.modules[integration_name].items():
                            if hasattr(module, action_name):
                                function_name = action_name
                                found = True
                                break
                        if not found:
                            module_name = integration_name
                            function_name = action_name

                    self.action_implementations[full_action_name] = (module_name, function_name)

    def get_action(self, action_name):
        if '.' in action_name:
            integration_name, action_short_name = action_name.split('.', 1)
            if integration_name in self.integrations:
                actions = self.integrations[integration_name].get('actions', {})
                action_def = actions.get(action_short_name)
                if action_def:
                    return action_def, integration_name, action_short_name

                if action_name in self.action_implementations:
                    if action_short_name == 'if':
                        action_def = actions.get('if_node')
                        if action_def:
                            return action_def, integration_name, 'if_node'
                    elif action_short_name == 'while':
                        action_def = actions.get('while_loop')
                        if action_def:
                            return action_def, integration_name, 'while_loop'
                    elif action_short_name == 'try':
                        action_def = actions.get('try_catch')
                        if action_def:
                            return action_def, integration_name, 'try_catch'

        if action_name == "__prompt__.ask" and "prompts" in self.integrations:
            actions = self.integrations["prompts"].get('actions', {})
            action_def = actions.get("ask")
            if action_def:
                return action_def, "prompts", "ask"

        return None, None, None

    def get_module_for_action(self, action_name):
        if action_name in self.action_implementations:
            module_name, _ = self.action_implementations[action_name]
            if module_name == "__plugin__":
                integration_name = action_name.split('.', 1)[0]
                return integration_name, "__plugin__"
            if '.' in action_name:
                integration_name, _ = action_name.split('.', 1)
                return integration_name, module_name

        if '.' not in action_name:
            return None, None

        integration_name, action_short_name = action_name.split('.', 1)
        if integration_name == "__prompt__":
            return "prompts", "ask"

        if integration_name in self.modules:
            for module_name, module in self.modules[integration_name].items():
                if hasattr(module, action_short_name):
                    return integration_name, module_name

        if '_' in action_short_name:
            potential_module = action_short_name.split('_')[0]
            if integration_name in self.modules and potential_module in self.modules[integration_name]:
                return integration_name, potential_module

        if integration_name in self.integrations and 'primary_module' in self.integrations[integration_name]:
            return integration_name, self.integrations[integration_name]['primary_module']

        if integration_name == 'control':
            return 'control', 'control'

        return integration_name, integration_name

    def execute_action(self, action_name, **kwargs):
        if action_name in self.action_implementations:
            module_tag, function_or_callable = self.action_implementations[action_name]
            integration_name = action_name.split('.', 1)[0]

            processed_kwargs = self._process_template_vars(kwargs)

            if module_tag == "__plugin__" and callable(function_or_callable):
                return function_or_callable(**processed_kwargs)

            if integration_name in self.modules and module_tag in self.modules[integration_name]:
                module = self.modules[integration_name][module_tag]
                if hasattr(module, function_or_callable):
                    return getattr(module, function_or_callable)(**processed_kwargs)

        action_def, integration_name, action_short_name = self.get_action(action_name)
        if not integration_name or not action_short_name:
            raise ValueError(f"Action '{action_name}' not found in registry")

        if integration_name not in self.modules:
            raise ValueError(f"No modules loaded for integration '{integration_name}'")

        processed_kwargs = self._process_template_vars(kwargs)

        for module_name, module in self.modules[integration_name].items():
            if hasattr(module, action_short_name):
                return getattr(module, action_short_name)(**processed_kwargs)

        raise ValueError(f"Function '{action_short_name}' not found in integration '{integration_name}'")

    def _process_template_vars(self, kwargs):
        processed = {}
        for key, value in kwargs.items():
            if isinstance(value, str):
                if '{{' in value:
                    value = value.replace('{{', '{').replace('}}', '}')
            processed[key] = value
        return processed

    def get_all_actions(self):
        all_actions = {}
        for integration_name, integration_data in self.integrations.items():
            actions = integration_data.get('actions', {})
            for action_name, action_data in actions.items():
                qualified_name = f"{integration_name}.{action_name}"
                all_actions[qualified_name] = action_data
        return all_actions

    def to_json(self):
        return self.integrations
