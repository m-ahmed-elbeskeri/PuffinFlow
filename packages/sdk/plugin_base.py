# sdk/plugin_base.py

"""Base classes for FlowForge plugins."""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

class PluginAction(ABC):
    """Base class for plugin actions."""
    
    @abstractmethod
    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the action with the given parameters."""
        pass

class Plugin(ABC):
    """Base class for FlowForge plugins."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Get the plugin name."""
        pass
    
    @property
    @abstractmethod
    def version(self) -> str:
        """Get the plugin version."""
        pass
    
    @abstractmethod
    def get_actions(self) -> Dict[str, PluginAction]:
        """Get all actions provided by this plugin."""
        pass
    
    @abstractmethod
    def execute_action(self, action_name: str, **kwargs) -> Dict[str, Any]:
        """Execute a specific action."""
        pass