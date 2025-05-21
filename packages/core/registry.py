"""Registry module for loading and managing integrations and actions through plugins only."""

import os
from pathlib import Path
from typing import Dict, Any, Optional

from packages.sdk.plugin_loader import load_plugins

class Registry:
    """Registry class for loading and managing integration definitions through plugins."""

    def __init__(self, auto_install_deps=False):
        self.integrations = {}
        self.action_implementations = {}  # Maps action_name to callable
        self.auto_install_deps = auto_install_deps
        self.plugins = {}

        self._initialize_special_mappings()
        self._load_plugins_into_registry()

    def _initialize_special_mappings(self):
        """Initialize special mappings for Python keywords and other edge cases."""
        # These will be handled directly by the plugins now
        pass

    def _load_plugins_into_registry(self, plugin_dir="integrations"):
        """Load all plugins and integrate them into the registry system."""
        try:
            self.plugins = load_plugins(plugin_dir, auto_install_deps=self.auto_install_deps)
        except Exception as e:
            print(f"Failed to load plugins: {e}")
            return

        for plugin_name, plugin_info in self.plugins.items():
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
                self.action_implementations[fq_action] = entry["function"]
            print(f"Registered plugin actions for: {plugin_name}")

    def load_integrations(self, integrations_dir="integrations"):
        """
        This method is kept for backward compatibility but does nothing.
        All integrations are loaded via the plugin loader.
        """
        pass

    def get_action(self, action_name):
        if '.' in action_name:
            integration_name, action_short_name = action_name.split('.', 1)
            if integration_name in self.integrations:
                actions = self.integrations[integration_name].get('actions', {})
                action_def = actions.get(action_short_name)
                if action_def:
                    return action_def, integration_name, action_short_name

        if action_name == "__prompt__.ask" and "prompts" in self.integrations:
            actions = self.integrations["prompts"].get('actions', {})
            action_def = actions.get("ask")
            if action_def:
                return action_def, "prompts", "ask"

        return None, None, None

    def get_module_for_action(self, action_name):
        """Get the integration name for an action."""
        if action_name in self.action_implementations:
            if '.' in action_name:
                integration_name, _ = action_name.split('.', 1)
                return integration_name, "__plugin__"

        if '.' not in action_name:
            return None, None

        integration_name, _ = action_name.split('.', 1)
        return integration_name, "__plugin__"

    def get_implementation_for_action(self, action_name):
        """Get the implementation function for an action."""
        return self.action_implementations.get(action_name)

    def execute_action(self, action_name, **kwargs):
        """Execute an action from the registry."""
        if action_name in self.action_implementations:
            function = self.action_implementations[action_name]
            processed_kwargs = self._process_template_vars(kwargs)
            return function(**processed_kwargs)

        action_def, integration_name, action_short_name = self.get_action(action_name)
        if not integration_name or not action_short_name:
            raise ValueError(f"Action '{action_name}' not found in registry")

        raise ValueError(f"Implementation for action '{action_name}' not found in registry")

    def _process_template_vars(self, kwargs):
        """Process template variables in action inputs."""
        processed = {}
        for key, value in kwargs.items():
            if isinstance(value, str):
                if '{{' in value:
                    value = value.replace('{{', '{').replace('}}', '}')
            processed[key] = value
        return processed

    def get_all_actions(self):
        """Get all registered actions."""
        all_actions = {}
        for integration_name, integration_data in self.integrations.items():
            actions = integration_data.get('actions', {})
            for action_name, action_data in actions.items():
                qualified_name = f"{integration_name}.{action_name}"
                all_actions[qualified_name] = action_data
        return all_actions

    def to_json(self):
        """Convert registry to JSON-serializable format."""
        return self.integrations